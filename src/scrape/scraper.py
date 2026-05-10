"""Async HTTP scraper — optimized for research pipeline.

Improvements over v1:
- selectolax  : Rust-backed HTML parser (10-50× faster than HTMLParser)
- trafilatura : Boilerplate removal, article extraction, metadata
- Playwright  : Lazy — only for /docs, /developers, /api SPA pages
- protego     : Advisory robots.txt (logs warning, doesn't block)
- No truncation: full text passed to LLM, prompt handles context limits
- URL dedup   : across domain crawl and search scrape
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urljoin, urlparse

import httpx
import trafilatura
from playwright.async_api import async_playwright, Browser, BrowserContext
from protego import Protego
from selectolax.parser import HTMLParser
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ScrapedPage:
    """A single scraped web page."""
    url: str
    status_code: int
    text: str          # Clean article/body text via trafilatura
    raw_text: str      # Full visible text (preserves code blocks, tables)
    title: str
    links: list[str] = field(default_factory=list)
    metadata: dict     = field(default_factory=dict)
    rendered: bool     = False
    timestamp: float   = 0.0

    def __repr__(self) -> str:
        mode = "pw" if self.rendered else "http"
        return (
            f"ScrapedPage({self.url!r}, status={self.status_code}, "
            f"text={len(self.text)}, raw={len(self.raw_text)}, mode={mode})"
        )


# ---------------------------------------------------------------------------
# HTML helpers — selectolax + trafilatura (NO truncation)
# ---------------------------------------------------------------------------

def _parse_html(html: str, source_url: str) -> tuple[str, str, list[str], dict]:
    """Parse HTML → (title, clean_text, raw_text, absolute_links, metadata).

    No truncation — let the LLM prompt handle context window management
    per field group rather than hard-truncating in the scraper.
    """
    tree = HTMLParser(html)

    # Title
    title_node = tree.css_first("title")
    title = title_node.text(strip=True) if title_node else ""

    # Clean article text via trafilatura (no truncation)
    clean_text = trafilatura.extract(
        html,
        include_links=False,
        include_tables=True,
        no_fallback=False,
        favor_recall=True,
    ) or ""

    # Raw visible text via selectolax (preserves code blocks, tables)
    for tag in tree.css("script, style, noscript"):
        tag.decompose()
    raw_text = re.sub(r"\s+", " ", tree.body.text(strip=True) if tree.body else "").strip()

    # Metadata from trafilatura
    meta = trafilatura.extract_metadata(html, default_url=source_url)
    metadata: dict = {}
    if meta:
        metadata = {
            k: getattr(meta, k, None)
            for k in ("author", "date", "description", "language", "sitename", "categories", "tags")
            if getattr(meta, k, None)
        }

    # Links via selectolax
    base_node = tree.css_first("base[href]")
    base = (base_node.attrs.get("href") or source_url) if base_node else source_url
    absolute_links: list[str] = []
    for node in tree.css("a[href]"):
        href = node.attrs.get("href", "")
        if not href:
            continue
        absolute = urljoin(base, href)
        if absolute.startswith(("http://", "https://")):
            absolute_links.append(absolute)

    return title, clean_text, raw_text, absolute_links, metadata


# ---------------------------------------------------------------------------
# Retry predicate
# ---------------------------------------------------------------------------

def _is_server_error(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    if isinstance(exc, httpx.TimeoutException):
        return True
    return False


# ---------------------------------------------------------------------------
# Robots.txt — advisory (log warning, don't block)
# ---------------------------------------------------------------------------

class _RobotsCache:
    """Robots.txt checker using protego. Logs warnings but doesn't block.

    Many companies have overly broad Disallow: / that would block
    legitimate public research. We log but continue.
    """

    def __init__(self) -> None:
        self._cache: dict[str, Protego | None] = {}
        self._lock = asyncio.Lock()

    async def check(self, url: str, user_agent: str) -> bool:
        """Returns True if allowed, logs warning if not but still returns True."""
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        async with self._lock:
            if origin not in self._cache:
                self._cache[origin] = await self._fetch_robots(origin)
        robot = self._cache[origin]
        if robot is None:
            return True
        allowed = robot.can_fetch(url, user_agent)
        if not allowed:
            logger.warning("robots.txt disallows: %s (continuing anyway)", url)
        return True  # Always continue — advisory only

    async def crawl_delay(self, url: str, user_agent: str) -> float:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        robot = self._cache.get(origin)
        if robot is None:
            return 0.0
        delay = robot.crawl_delay(user_agent)
        return float(delay) if delay is not None else 0.0

    @staticmethod
    async def _fetch_robots(origin: str) -> Protego | None:
        try:
            async with httpx.AsyncClient(timeout=8, follow_redirects=True) as client:
                resp = await client.get(f"{origin}/robots.txt")
                if resp.status_code == 200:
                    return Protego.parse(resp.text)
        except Exception:
            pass
        return None


# ---------------------------------------------------------------------------
# Scraper
# ---------------------------------------------------------------------------

# Paths where Playwright is likely needed (SPA docs portals)
_PLAYWRIGHT_PATHS = {"/docs", "/documentation", "/api", "/developers", "/developer"}

class AsyncScraper:
    """Async HTTP scraper with lazy Playwright for SPA pages.

    Strategy:
    1. httpx for all pages (fast, covers ~90% of marketing sites)
    2. Playwright ONLY for /docs, /api, /developers paths that are likely SPAs
    3. No truncation — full text passed through, LLM handles context
    4. robots.txt is advisory (logs but doesn't block)
    5. URL dedup across domain crawl and search scrape
    """

    USER_AGENT = "TokenizedAssetsBot/1.0 (research)"
    _PLAYWRIGHT_UA = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )

    COMPANY_PATHS = [
        "/", "/about", "/about-us", "/team", "/company",
        "/docs", "/documentation", "/api", "/developers",
        "/products", "/solutions", "/services", "/platform",
        "/pricing", "/partners", "/partnerships",
        "/compliance", "/security", "/legal", "/regulatory",
        "/careers", "/jobs", "/blog", "/resources",
        "/case-studies", "/customers", "/contact",
        "/governance", "/token", "/whitepaper", "/faq",
    ]

    def __init__(
        self,
        timeout: int = 12,
        max_concurrent: int = 8,
        use_playwright: bool = True,
        playwright_timeout: int = 20_000,
    ) -> None:
        self.timeout = timeout
        self.max_concurrent = max_concurrent
        self.use_playwright = use_playwright
        self.playwright_timeout = playwright_timeout
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._robots = _RobotsCache()
        self._browser: Optional[Browser] = None
        self._pw_context: Optional[BrowserContext] = None
        self._pw_lock = asyncio.Lock()
        self._scraped_urls: set[str] = set()  # Global dedup set

    # ------------------------------------------------------------------
    # Playwright lifecycle (lazy)
    # ------------------------------------------------------------------

    async def _ensure_browser(self) -> Browser:
        async with self._pw_lock:
            if self._browser is None or not self._browser.is_connected():
                pw = await async_playwright().start()
                self._browser = await pw.chromium.launch(headless=True)
                self._pw_context = await self._browser.new_context(
                    user_agent=self._PLAYWRIGHT_UA,
                    java_script_enabled=True,
                    ignore_https_errors=True,
                )
        return self._browser

    async def close(self) -> None:
        if self._browser and self._browser.is_connected():
            await self._browser.close()

    # ------------------------------------------------------------------
    # httpx helpers
    # ------------------------------------------------------------------

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=self.timeout,
            headers={"User-Agent": self.USER_AGENT},
            follow_redirects=True,
            max_redirects=5,
        )

    @retry(
        retry=retry_if_exception(_is_server_error),
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=5),
        reraise=True,
    )
    async def _fetch_httpx(self, url: str) -> httpx.Response:
        async with self._semaphore:
            async with self._client() as client:
                response = await client.get(url)
                response.raise_for_status()
                return response

    # ------------------------------------------------------------------
    # Playwright fetch
    # ------------------------------------------------------------------

    async def _fetch_playwright(self, url: str) -> tuple[str, int]:
        await self._ensure_browser()
        async with self._semaphore:
            page = await self._pw_context.new_page()
            try:
                response = await page.goto(
                    url, timeout=self.playwright_timeout,
                    wait_until="networkidle",
                )
                status = response.status if response else 200
                await page.wait_for_timeout(800)
                html = await page.content()
                return html, status
            finally:
                await page.close()

    # ------------------------------------------------------------------
    # SPA detection — only trigger for docs/API paths
    # ------------------------------------------------------------------

    @staticmethod
    def _should_try_playwright(url: str, html: str) -> bool:
        """Only use Playwright for docs/API pages with SPA markers."""
        path = urlparse(url).path.rstrip("/")
        # Only attempt Playwright for known SPA-heavy paths
        if path not in _PLAYWRIGHT_PATHS:
            return False
        # And only if the content looks like an empty shell
        if len(html.strip()) < 500:
            return True
        spa_markers = ("__NEXT_DATA__", "window.__nuxt__", "ng-version",
                       '<div id="root"></div>', '<div id="app"></div>')
        return any(m in html for m in spa_markers)

    # ------------------------------------------------------------------
    # Core scrape logic
    # ------------------------------------------------------------------

    async def _scrape_one(self, url: str) -> Optional[ScrapedPage]:
        # URL dedup — skip if already scraped
        if url in self._scraped_urls:
            return None
        self._scraped_urls.add(url)

        # Advisory robots check (logs but doesn't block)
        await self._robots.check(url, self.USER_AGENT)

        # Respect crawl-delay if specified
        delay = await self._robots.crawl_delay(url, self.USER_AGENT)
        if delay > 0:
            await asyncio.sleep(min(delay, 2.0))  # Cap at 2s

        html: str = ""
        status_code: int = 0
        rendered: bool = False

        # Phase 1: httpx (fast)
        try:
            response = await self._fetch_httpx(url)
            status_code = response.status_code
            if status_code == 200:
                html = response.text
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code if exc.response else 0
        except (httpx.RequestError, Exception):
            pass

        # Phase 2: Playwright — only for docs/API SPA pages
        if (self.use_playwright and status_code == 200
                and self._should_try_playwright(url, html)):
            try:
                html, status_code = await self._fetch_playwright(url)
                rendered = True
            except Exception:
                pass

        if not html or status_code != 200:
            if status_code:
                return ScrapedPage(
                    url=url, status_code=status_code,
                    text="", raw_text="", title="", timestamp=time.time(),
                )
            return None

        title, clean_text, raw_text, links, metadata = _parse_html(html, url)

        return ScrapedPage(
            url=url, status_code=status_code,
            text=clean_text, raw_text=raw_text,
            title=title, links=links, metadata=metadata,
            rendered=rendered, timestamp=time.time(),
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def scrape_urls(self, urls: list[str]) -> dict[str, ScrapedPage]:
        """Scrape multiple URLs concurrently. Deduplicates automatically."""
        unique_urls = [u for u in dict.fromkeys(urls) if u not in self._scraped_urls]
        tasks = [self._scrape_one(url) for url in unique_urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        scraped: dict[str, ScrapedPage] = {}
        for url, result in zip(unique_urls, results):
            if isinstance(result, Exception):
                continue
            if result is not None and result.status_code == 200 and (result.text or result.raw_text):
                scraped[url] = result
        return scraped

    async def get_company_pages(self, domain: str) -> dict[str, ScrapedPage]:
        """Scrape company domain pages + discover internal links (up to 30)."""
        base = domain if domain.startswith("http") else f"https://{domain}"
        urls = [f"{base}{path}" for path in self.COMPANY_PATHS]
        scraped = await self.scrape_urls(urls)

        # Discover internal links
        parsed_base = urlparse(base)
        base_domain = parsed_base.netloc
        skip_patterns = (
            ".pdf", ".png", ".jpg", ".jpeg", ".svg", ".css", ".js",
            ".woff", ".woff2", ".ico", ".mp4", ".webp",
            "/feed", "/rss", "/wp-json", "/xmlrpc", "/sitemap",
        )
        seen = set(scraped.keys()) | self._scraped_urls
        discovered: list[str] = []

        for page in scraped.values():
            for link in page.links:
                if link in seen:
                    continue
                link_domain = urlparse(link).netloc
                if base_domain not in link_domain and link_domain not in base_domain:
                    continue
                if any(p in link.lower() for p in skip_patterns):
                    continue
                seen.add(link)
                discovered.append(link)

        if discovered:
            extra = await self.scrape_urls(discovered[:30])  # Increased from 20 → 30
            scraped.update(extra)

        return scraped

    async def scrape_search_urls(
        self,
        search_results: dict[str, list],
        max_per_query: int = 3,
        max_total: int = 20,
        exclude_domain: str = "",
    ) -> dict[str, ScrapedPage]:
        """Scrape top URLs from search results. Deduplicates against domain crawl."""
        urls: list[str] = []
        seen: set[str] = set()

        for _query, results in search_results.items():
            count = 0
            for r in results:
                url = r.get("url", "") if isinstance(r, dict) else getattr(r, "url", "")
                if not url or url in seen or url in self._scraped_urls:
                    continue
                if exclude_domain and exclude_domain in url:
                    continue
                seen.add(url)
                urls.append(url)
                count += 1
                if count >= max_per_query:
                    break
            if len(urls) >= max_total:
                break

        return await self.scrape_urls(urls[:max_total])
