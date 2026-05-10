"""Database saver — persists pipeline CompanyData into PostgreSQL.

Maps Pydantic CitedValue models to the schema.sql table structure.
Uses asyncpg for fast, lightweight inserts with upsert support.
"""

from __future__ import annotations

import os
import json
import logging
import datetime
from typing import Any

import asyncpg

from ..schema.models import (
    CompanyData, CompanyProfile, Product, AssetClass, Feature,
    Standard, Integration, FundingRound, GovernanceModel,
    ComplianceCertification, SlaCommitment, StabilityEntry,
    TechStackEntry, ApiCapability, Partnership, ExchangeListing,
    RegulatoryLicense, PlatformMetric, DealCaseStudy, CitedValue,
)

logger = logging.getLogger(__name__)


def _val(cv: CitedValue) -> Any:
    """Extract value from CitedValue. Returns str for string columns, raw for typed helpers."""
    if cv is None or not cv.is_filled():
        return None
    v = cv.value
    if v == "N/A" or v == "unknown" or v == "Unknown Company":
        return None
    # Reject confidence floats that leaked into value field
    if isinstance(v, float):
        if (0.0 <= v <= 1.0) or (99.0 <= v <= 100.0):
            return None
    # Lists pass through as-is (for JSON columns)
    if isinstance(v, list):
        return v
    # Booleans pass through (for bool helpers)
    if isinstance(v, bool):
        return v
    # Everything else → str (ensures ints don't hit VARCHAR columns)
    return str(v)


def _bool(cv: CitedValue) -> Any:
    """Extract a boolean value, rejecting non-boolean values."""
    v = _val(cv)
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        if v.lower() in ("true", "yes", "1"):
            return True
        if v.lower() in ("false", "no", "0"):
            return False
    return None


def _int(cv: CitedValue) -> Any:
    """Extract an integer value, rejecting non-numeric values."""
    v = _val(cv)
    if v is None:
        return None
    try:
        return int(v)
    except (ValueError, TypeError):
        return None


def _float(cv: CitedValue) -> Any:
    """Extract a float value, rejecting non-numeric values."""
    v = _val(cv)
    if v is None:
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _date(cv: CitedValue) -> Any:
    """Extract a date-compatible value. Converts strings/ints to date or None."""
    v = _val(cv)
    if v is None:
        return None
    if isinstance(v, (datetime.date, datetime.datetime)):
        return v
    if isinstance(v, str):
        try:
            return datetime.date.fromisoformat(v[:10])
        except (ValueError, TypeError):
            return None
    if isinstance(v, int):
        return None
    return None


def _cite_json(model: Any) -> str:
    """Build citations JSONB from a Pydantic model's CitedValue fields."""
    citations = {}
    for fn in model.__class__.model_fields:
        val = getattr(model, fn)
        if isinstance(val, CitedValue) and val.is_filled():
            citations[fn] = {
                "source_url": val.source_url,
                "confidence": val.confidence,
            }
    return json.dumps(citations, default=str)


class DatabaseSaver:
    """Saves pipeline output to PostgreSQL."""

    def __init__(self, dsn: str | None = None) -> None:
        self.dsn = dsn or os.getenv(
            "DATABASE_URL",
            "postgresql://fiftyone:fiftyone_secret@localhost:5432/fiftyone_insight",
        )
        self._pool: asyncpg.Pool | None = None

    async def _get_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(self.dsn, min_size=2, max_size=10)
        return self._pool

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None

    # ------------------------------------------------------------------
    # Main save entry point
    # ------------------------------------------------------------------

    async def save(
        self,
        company_name: str,
        domain: str,
        data: CompanyData,
        llm_provider: str = "",
        llm_model: str = "",
        fill_rate: float = 0.0,
        real_fill: float = 0.0,
        high_fill: float = 0.0,
        pages_scraped: int = 0,
        search_results: int = 0,
        duration_secs: float = 0.0,
        llm_call_logs: list[dict] | None = None,
    ) -> int:
        """Save a full CompanyData record. Returns the company_id."""
        pool = await self._get_pool()
        now = datetime.datetime.now(datetime.timezone.utc)

        async with pool.acquire() as conn:
            async with conn.transaction():
                # 1. Upsert company
                company_id = await self._upsert_company(
                    conn, company_name, domain, data.profile, now,
                )

                # 2. Delete existing child records (clean slate per run)
                tables = [
                    "products", "asset_classes", "features", "token_standards",
                    "integrations", "funding_rounds", "governance_model",
                    "compliance_certifications", "sla_commitments", "stability_table",
                    "tech_stack", "api_capabilities", "partnerships",
                    "exchange_listings", "regulatory_licenses",
                    "platform_metrics", "deal_case_studies",
                ]
                for t in tables:
                    await conn.execute(
                        f"DELETE FROM {t} WHERE company_id = $1", company_id,
                    )

                # 3. Insert child records
                await self._insert_products(conn, company_id, data.products, now)
                await self._insert_asset_classes(conn, company_id, data.asset_classes, now)
                await self._insert_features(conn, company_id, data.features, now)
                await self._insert_standards(conn, company_id, data.standards, now)
                await self._insert_integrations(conn, company_id, data.integrations, now)
                await self._insert_funding_rounds(conn, company_id, data.funding_rounds, now)
                await self._insert_governance(conn, company_id, data.governance_models, now)
                await self._insert_compliance(conn, company_id, data.compliance_certifications, now)
                await self._insert_sla(conn, company_id, data.sla_commitments, now)
                await self._insert_stability(conn, company_id, data.stability_entries, now)
                await self._insert_tech_stack(conn, company_id, data.tech_stack, now)
                await self._insert_api_capabilities(conn, company_id, data.api_capabilities, now)
                await self._insert_partnerships(conn, company_id, data.partnerships, now)
                await self._insert_exchange_listings(conn, company_id, data.exchange_listings, now)
                await self._insert_regulatory_licenses(conn, company_id, data.regulatory_licenses, now)
                await self._insert_platform_metrics(conn, company_id, data.platform_metrics, now)
                await self._insert_deal_case_studies(conn, company_id, data.deal_case_studies, now)

                # 4. Log pipeline run
                run_row = await conn.fetchrow("""
                    INSERT INTO pipeline_runs (
                        company_id, company_name, domain, started_at, completed_at,
                        status, llm_provider, llm_model, fill_rate, real_fill, high_fill,
                        pages_scraped, search_results, duration_secs, cost_usd
                    ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15)
                    RETURNING run_id
                """, company_id, company_name, domain, now, now,
                    "completed", llm_provider, llm_model,
                    fill_rate, real_fill, high_fill,
                    pages_scraped, search_results, duration_secs,
                    0.0,
                )
                run_id = run_row["run_id"]

                # 5. Save LLM call logs
                if llm_call_logs:
                    await self._insert_llm_call_logs(conn, run_id, company_name, llm_call_logs)

        logger.info("Saved %s (company_id=%d)", company_name, company_id)
        return company_id

    # ------------------------------------------------------------------
    # Company upsert
    # ------------------------------------------------------------------

    async def _upsert_company(
        self, conn: asyncpg.Connection,
        company_name: str, domain: str,
        p: CompanyProfile, now: datetime.datetime,
    ) -> int:
        row = await conn.fetchrow("""
            INSERT INTO companies (
                company_name, legal_name, hq_country, hq_city, founded_year,
                website, description, company_type, operational_status,
                employee_count_range, logo_url, is_active, platform, url,
                handle, follower_count, total_employees, founder_still_active,
                extracted_at, _citations
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20)
            ON CONFLICT (company_name) DO UPDATE SET
                legal_name = EXCLUDED.legal_name,
                hq_country = EXCLUDED.hq_country,
                hq_city = EXCLUDED.hq_city,
                founded_year = EXCLUDED.founded_year,
                website = EXCLUDED.website,
                description = EXCLUDED.description,
                company_type = EXCLUDED.company_type,
                operational_status = EXCLUDED.operational_status,
                employee_count_range = EXCLUDED.employee_count_range,
                logo_url = EXCLUDED.logo_url,
                is_active = EXCLUDED.is_active,
                platform = EXCLUDED.platform,
                url = EXCLUDED.url,
                handle = EXCLUDED.handle,
                follower_count = EXCLUDED.follower_count,
                total_employees = EXCLUDED.total_employees,
                founder_still_active = EXCLUDED.founder_still_active,
                extracted_at = EXCLUDED.extracted_at,
                _citations = EXCLUDED._citations
            RETURNING company_id
        """,
            company_name,
            _val(p.legal_name),
            _val(p.hq_country),
            _val(p.hq_city),
            _int(p.founded_year),
            _val(p.website) or f"https://{domain}",
            _val(p.description),
            _val(p.company_type),
            _val(p.operational_status),
            _val(p.employee_count_range),
            _val(p.logo_url),
            _bool(p.is_active) if _bool(p.is_active) is not None else True,
            _val(p.platform),
            _val(p.url),
            _val(p.handle),
            _int(p.follower_count),
            _int(p.total_employees),
            _val(p.founder_still_active),
            now,
            _cite_json(p),
        )
        return row["company_id"]

    # ------------------------------------------------------------------
    # Child table inserts
    # ------------------------------------------------------------------

    async def _insert_products(self, conn, cid, rows, now):
        for r in rows:
            if not _val(r.product_name):
                continue
            await conn.execute("""
                INSERT INTO products (company_id, product_name, product_type, description,
                    launch_date, status, pricing_model, pricing_notes, target_segment,
                    extracted_at, _citations)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
                ON CONFLICT (company_id, product_name) DO UPDATE SET
                    product_type=EXCLUDED.product_type, description=EXCLUDED.description,
                    status=EXCLUDED.status, pricing_model=EXCLUDED.pricing_model,
                    extracted_at=EXCLUDED.extracted_at
            """, cid, _val(r.product_name), _val(r.product_type), _val(r.description),
                _date(r.launch_date), _val(r.status), _val(r.pricing_model),
                _val(r.pricing_notes), _val(r.target_segment), now, _cite_json(r),
            )

    async def _insert_asset_classes(self, conn, cid, rows, now):
        for r in rows:
            if not _val(r.asset_class):
                continue
            await conn.execute("""
                INSERT INTO asset_classes (company_id, asset_class, is_primary,
                    maturity_level, notes, extracted_at, _citations)
                VALUES ($1,$2,$3,$4,$5,$6,$7)
                ON CONFLICT (company_id, asset_class) DO UPDATE SET
                    is_primary=EXCLUDED.is_primary, maturity_level=EXCLUDED.maturity_level
            """, cid, _val(r.asset_class), _bool(r.is_primary), _val(r.maturity_level),
                _val(r.notes), now, _cite_json(r),
            )

    async def _insert_features(self, conn, cid, rows, now):
        for r in rows:
            if not _val(r.feature_name):
                continue
            await conn.execute("""
                INSERT INTO features (company_id, feature_category, feature_name,
                    feature_tier, description, extracted_at, _citations)
                VALUES ($1,$2,$3,$4,$5,$6,$7)
                ON CONFLICT (company_id, feature_name) DO UPDATE SET
                    feature_category=EXCLUDED.feature_category, feature_tier=EXCLUDED.feature_tier
            """, cid, _val(r.feature_category), _val(r.feature_name),
                _val(r.feature_tier), _val(r.description), now, _cite_json(r),
            )

    async def _insert_standards(self, conn, cid, rows, now):
        for r in rows:
            if not _val(r.standard_name):
                continue
            await conn.execute("""
                INSERT INTO token_standards (company_id, standard_name, is_native_support,
                    compliance_built_in, notes, extracted_at, _citations)
                VALUES ($1,$2,$3,$4,$5,$6,$7)
                ON CONFLICT (company_id, standard_name) DO UPDATE SET
                    is_native_support=EXCLUDED.is_native_support
            """, cid, _val(r.standard_name), _bool(r.is_native_support),
                _bool(r.compliance_built_in), None, now, _cite_json(r),
            )

    async def _insert_integrations(self, conn, cid, rows, now):
        for r in rows:
            if not _val(r.partner_name):
                continue
            await conn.execute("""
                INSERT INTO integrations (company_id, partner_name, integration_type,
                    integration_depth, status, description, extracted_at, _citations)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                ON CONFLICT (company_id, partner_name, integration_type) DO UPDATE SET
                    integration_depth=EXCLUDED.integration_depth, status=EXCLUDED.status
            """, cid, _val(r.partner_name), _val(r.integration_type),
                _val(r.integration_depth), _val(r.status), _val(r.description),
                now, _cite_json(r),
            )

    async def _insert_funding_rounds(self, conn, cid, rows, now):
        for r in rows:
            if not _val(r.round_type):
                continue
            await conn.execute("""
                INSERT INTO funding_rounds (company_id, round_type, amount_usd, date,
                    lead_investor, other_investors, valuation_usd, source_url, notes,
                    extracted_at, _citations)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
                ON CONFLICT (company_id, round_type, date) DO UPDATE SET
                    amount_usd=EXCLUDED.amount_usd, lead_investor=EXCLUDED.lead_investor
            """, cid, _val(r.round_type), _float(r.amount_usd), _date(r.date),
                _val(r.lead_investor), _val(r.other_investors),
                _float(r.valuation_usd), _val(r.source_url), _val(r.notes),
                now, _cite_json(r),
            )

    async def _insert_governance(self, conn, cid, rows, now):
        for r in rows:
            await conn.execute("""
                INSERT INTO governance_model (company_id, governance_type, has_token,
                    token_symbol, token_distribution_notes, treasury_runway_months,
                    total_funding_usd, revenue_status, last_assessed_at, extracted_at, _citations)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
                ON CONFLICT (company_id) DO UPDATE SET
                    governance_type=EXCLUDED.governance_type, has_token=EXCLUDED.has_token,
                    total_funding_usd=EXCLUDED.total_funding_usd
            """, cid, _val(r.governance_type), _bool(r.has_token), _val(r.token_symbol),
                _val(r.token_distribution_notes), _int(r.treasury_runway_months),
                _float(r.total_funding_usd), _val(r.revenue_status), _date(r.last_assessed_at),
                now, _cite_json(r),
            )

    async def _insert_compliance(self, conn, cid, rows, now):
        for r in rows:
            if not _val(r.certification_type):
                continue
            await conn.execute("""
                INSERT INTO compliance_certifications (company_id, certification_type,
                    status, issued_date, expiry_date, auditor, certificate_url,
                    extracted_at, _citations)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
                ON CONFLICT (company_id, certification_type) DO UPDATE SET
                    status=EXCLUDED.status, auditor=EXCLUDED.auditor
            """, cid, _val(r.certification_type), _val(r.status), _date(r.issued_date),
                _date(r.expiry_date), _val(r.auditor), _val(r.certificate_url),
                now, _cite_json(r),
            )

    async def _insert_sla(self, conn, cid, rows, now):
        for r in rows:
            if not _val(r.metric):
                continue
            await conn.execute("""
                INSERT INTO sla_commitments (company_id, metric, committed_value,
                    actual_value_last_12m, measurement_period, has_penalty_clause,
                    notes, extracted_at, _citations)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
                ON CONFLICT (company_id, metric) DO UPDATE SET
                    committed_value=EXCLUDED.committed_value
            """, cid, _val(r.metric), _val(r.committed_value),
                _val(r.actual_value_last_12m), _val(r.measurement_period),
                _bool(r.has_penalty_clause), _val(r.notes), now, _cite_json(r),
            )

    async def _insert_stability(self, conn, cid, rows, now):
        for r in rows:
            await conn.execute("""
                INSERT INTO stability_table (company_id, documentation_quality,
                    has_sandbox_environment, has_api_playground, languages_supported,
                    extracted_at, _citations)
                VALUES ($1,$2,$3,$4,$5,$6,$7)
                ON CONFLICT (company_id) DO UPDATE SET
                    documentation_quality=EXCLUDED.documentation_quality
            """, cid, _val(r.documentation_quality), _bool(r.has_sandbox_environment),
                _bool(r.has_api_playground), _val(r.languages_supported),
                now, _cite_json(r),
            )

    async def _insert_tech_stack(self, conn, cid, rows, now):
        for r in rows:
            if not _val(r.component) or not _val(r.technology):
                continue
            chains = _val(r.chains_supported)
            chains_str = json.dumps(chains) if isinstance(chains, list) else chains
            await conn.execute("""
                INSERT INTO tech_stack (company_id, component, technology, version,
                    chains_supported, mainnet_live, notes, extracted_at, _citations)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
                ON CONFLICT (company_id, component, technology) DO UPDATE SET
                    version=EXCLUDED.version, chains_supported=EXCLUDED.chains_supported
            """, cid, _val(r.component), _val(r.technology), _val(r.version),
                chains_str, _bool(r.mainnet_live), _val(r.notes),
                now, _cite_json(r),
            )

    async def _insert_api_capabilities(self, conn, cid, rows, now):
        for r in rows:
            sdks = _val(r.sdk_languages)
            sdks_str = json.dumps(sdks) if isinstance(sdks, list) else sdks
            await conn.execute("""
                INSERT INTO api_capabilities (company_id, api_type, documentation_url,
                    has_sandbox, rate_limit_tier, authentication_method, sdk_languages,
                    webhook_support, api_versioning, extracted_at, _citations)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
                ON CONFLICT (company_id) DO UPDATE SET
                    api_type=EXCLUDED.api_type, documentation_url=EXCLUDED.documentation_url
            """, cid, _val(r.api_type), _val(r.documentation_url),
                _bool(r.has_sandbox), _val(r.rate_limit_tier),
                _val(r.authentication_method), sdks_str,
                _bool(r.webhook_support), _bool(r.api_versioning),
                now, _cite_json(r),
            )

    async def _insert_partnerships(self, conn, cid, rows, now):
        for r in rows:
            if not _val(r.partner_name):
                continue
            await conn.execute("""
                INSERT INTO partnerships (company_id, partner_name, partner_type,
                    partnership_tier, announced_date, description, source_url,
                    extracted_at, _citations)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
                ON CONFLICT (company_id, partner_name) DO UPDATE SET
                    partnership_tier=EXCLUDED.partnership_tier
            """, cid, _val(r.partner_name), _val(r.partner_type),
                _val(r.partnership_tier), _date(r.announced_date),
                _val(r.description), _val(r.source_url), now, _cite_json(r),
            )

    async def _insert_exchange_listings(self, conn, cid, rows, now):
        for r in rows:
            if not _val(r.exchange_name):
                continue
            tradeable = _val(r.asset_classes_tradeable)
            tradeable_str = json.dumps(tradeable) if isinstance(tradeable, list) else tradeable
            await conn.execute("""
                INSERT INTO exchange_listings (company_id, exchange_name, exchange_type,
                    connectivity_type, status, asset_classes_tradeable, extracted_at, _citations)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                ON CONFLICT (company_id, exchange_name) DO UPDATE SET
                    status=EXCLUDED.status
            """, cid, _val(r.exchange_name), _val(r.exchange_type),
                _val(r.connectivity_type), _val(r.status), tradeable_str,
                now, _cite_json(r),
            )

    async def _insert_regulatory_licenses(self, conn, cid, rows, now):
        for r in rows:
            if not _val(r.jurisdiction) or not _val(r.license_type):
                continue
            inv = _val(r.investor_types_allowed)
            inv_str = json.dumps(inv) if isinstance(inv, list) else inv
            ac = _val(r.asset_classes_allowed)
            ac_str = json.dumps(ac) if isinstance(ac, list) else ac
            await conn.execute("""
                INSERT INTO regulatory_licenses (company_id, jurisdiction, license_type,
                    status, issued_date, license_number, regulator_name, coverage_type,
                    investor_types_allowed, asset_classes_allowed, regulatory_basis,
                    extracted_at, _citations)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
                ON CONFLICT (company_id, jurisdiction, license_type) DO UPDATE SET
                    status=EXCLUDED.status, regulator_name=EXCLUDED.regulator_name
            """, cid, _val(r.jurisdiction), _val(r.license_type), _val(r.status),
                _date(r.issued_date), _val(r.license_number), _val(r.regulator_name),
                _val(r.coverage_type), inv_str, ac_str, _val(r.regulatory_basis),
                now, _cite_json(r),
            )

    async def _insert_platform_metrics(self, conn, cid, rows, now):
        for r in rows:
            clients = _val(r.notable_clients)
            clients_str = json.dumps(clients) if isinstance(clients, list) else clients
            await conn.execute("""
                INSERT INTO platform_metrics (company_id, total_aum_tokenized_usd,
                    number_of_issuances, number_of_active_tokens, number_of_clients,
                    notable_clients, as_of_date, extracted_at, _citations)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
                ON CONFLICT (company_id) DO UPDATE SET
                    total_aum_tokenized_usd=EXCLUDED.total_aum_tokenized_usd,
                    number_of_clients=EXCLUDED.number_of_clients
            """, cid, _float(r.total_aum_tokenized_usd), _int(r.number_of_issuances),
                _int(r.number_of_active_tokens), _int(r.number_of_clients),
                clients_str, now, now, _cite_json(r),
            )

    async def _insert_deal_case_studies(self, conn, cid, rows, now):
        for r in rows:
            if not _val(r.title):
                continue
            await conn.execute("""
                INSERT INTO deal_case_studies (company_id, title, asset_class,
                    deal_size_usd, client_name, jurisdiction, completion_date,
                    description, public_url, extracted_at, _citations)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
                ON CONFLICT (company_id, title) DO UPDATE SET
                    deal_size_usd=EXCLUDED.deal_size_usd, client_name=EXCLUDED.client_name
            """, cid, _val(r.title), _val(r.asset_class), _float(r.deal_size_usd),
                _val(r.client_name), _val(r.jurisdiction), _date(r.completion_date),
                _val(r.description), _val(r.public_url), now, _cite_json(r),
            )

    # ------------------------------------------------------------------
    # LLM call log helpers
    # ------------------------------------------------------------------

    # Cost per 1M tokens (input / output) — update as pricing changes
    MODEL_COSTS: dict[str, tuple[float, float]] = {
        "gpt-4o-mini":           (0.15, 0.60),
        "gpt-4o":                (2.50, 10.00),
        "gpt-4o-2024-08-06":     (2.50, 10.00),
        "gpt-4-turbo":           (10.00, 30.00),
        "claude-sonnet-4-20250514": (3.00, 15.00),
        "claude-sonnet-4":         (3.00, 15.00),
        "claude-haiku-4-5-20251001": (0.80, 4.00),
        "glm-4-plus-0111":       (0.0, 0.0),   # z.ai free tier
        "anthropic/claude-sonnet-4": (3.00, 15.00),  # via OpenRouter
    }

    @classmethod
    def _calc_cost(cls, model: str, prompt_tokens: int, completion_tokens: int) -> float:
        rates = cls.MODEL_COSTS.get(model, (0.0, 0.0))
        inp_cost = (prompt_tokens / 1_000_000) * rates[0]
        out_cost = (completion_tokens / 1_000_000) * rates[1]
        return round(inp_cost + out_cost, 6)

    async def _insert_llm_call_logs(
        self,
        conn: asyncpg.Connection,
        run_id: int,
        company_name: str,
        logs: list[dict],
    ) -> None:
        """Insert all LLM call logs and update pipeline_runs.total_cost."""
        total_cost = 0.0
        for log in logs:
            cost = self._calc_cost(log.get("model", ""), log.get("prompt_tokens", 0), log.get("completion_tokens", 0))
            total_cost += cost
            await conn.execute("""
                INSERT INTO llm_call_logs (
                    run_id, company_name, batch_name, provider, model,
                    prompt_tokens, completion_tokens, total_tokens,
                    cost_usd, latency_ms, system_prompt_hash, user_prompt_chars,
                    response_chars, success, error_message
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15)
            """,
                run_id,
                company_name,
                log.get("batch_name", ""),
                log.get("provider", ""),
                log.get("model", ""),
                log.get("prompt_tokens", 0),
                log.get("completion_tokens", 0),
                log.get("total_tokens", 0),
                cost,
                log.get("latency_ms", 0),
                log.get("system_prompt_hash", ""),
                log.get("user_prompt_chars", 0),
                log.get("response_chars", 0),
                log.get("success", True),
                log.get("error_message"),
            )
        # Update pipeline run with total cost
        await conn.execute(
            "UPDATE pipeline_runs SET cost_usd = $1 WHERE run_id = $2",
            round(total_cost, 6), run_id,
        )
        logger.info("Saved %d LLM call logs (total cost: $%.6f)", len(logs), total_cost)
