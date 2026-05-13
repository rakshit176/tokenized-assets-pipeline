"""
Database connection and models for the Tokenized Assets Pipeline API.
"""

import os
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

import asyncpg
from pydantic import BaseModel

logger = logging.getLogger(__name__)


# =============================================================================
# Pydantic Models for API responses
# =============================================================================

class CompanyBase(BaseModel):
    company_id: int
    company_name: str
    domain: Optional[str] = None
    status: str
    created_at: datetime
    completed_at: Optional[datetime] = None
    processing_time_seconds: Optional[float] = None
    fill_rate: Optional[float] = None
    total_cost_usd: Optional[float] = None


class CompanyDetail(CompanyBase):
    legal_name: Optional[str] = None
    hq_country: Optional[str] = None
    hq_city: Optional[str] = None
    founded_year: Optional[int] = None
    description: Optional[str] = None
    company_type: Optional[str] = None
    employee_count_range: Optional[str] = None
    logo_url: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    sources: List[Dict[str, Any]] = []
    fields: List[Dict[str, Any]] = []
    errors: List[str] = []


class Source(BaseModel):
    url: str
    title: str
    type: str
    retrieved_at: str


class FieldData(BaseModel):
    field_name: str
    value: Any
    confidence: float
    sources: List[str] = []


class PipelineRunSummary(BaseModel):
    run_id: int
    company_id: Optional[int] = None
    company_name: str
    domain: Optional[str] = None
    status: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    fill_rate: Optional[float] = None
    duration_secs: Optional[float] = None
    cost_usd: Optional[float] = None


# =============================================================================
# Database connection
# =============================================================================

class Database:
    """Async PostgreSQL database connection."""

    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self):
        """Create connection pool."""
        self.pool = await asyncpg.create_pool(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "5432")),
            user=os.getenv("DB_USER", "postgres"),
            password=os.getenv("DB_PASSWORD", "postgres"),
            database=os.getenv("DB_NAME", "fiftyone_insights"),
            min_size=2,
            max_size=10,
        )

    async def close(self):
        """Close connection pool."""
        if self.pool:
            await self.pool.close()

    async def execute(self, query: str, *args):
        """Execute a query."""
        async with self.pool.acquire() as conn:
            return await conn.execute(query, *args)

    async def fetch(self, query: str, *args):
        """Fetch rows from a query."""
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, *args)

    async def fetchrow(self, query: str, *args):
        """Fetch a single row from a query."""
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def get_companies(
        self,
        limit: int = 100,
        offset: int = 0,
        status: Optional[str] = None,
    ) -> List[CompanyBase]:
        """Get unique companies from pipeline runs (latest run per domain)."""
        query = """
            SELECT DISTINCT ON (pr.domain)
                pr.run_id as company_id,
                pr.company_name,
                pr.domain,
                pr.status,
                pr.started_at as created_at,
                pr.completed_at,
                EXTRACT(EPOCH FROM (pr.completed_at - pr.started_at)) as processing_time_seconds,
                pr.fill_rate,
                pr.cost_usd as total_cost_usd
            FROM pipeline_runs pr
            WHERE 1=1
        """
        params = []

        if status:
            query += " AND pr.status = $1"
            params.append(status)

        query += " ORDER BY pr.domain, pr.started_at DESC LIMIT $" + str(len(params) + 1) + " OFFSET $" + str(len(params) + 2)
        params.extend([limit, offset])

        rows = await self.fetch(query, *params)
        return [CompanyBase(**dict(row)) for row in rows]

    async def get_company_by_domain(self, domain: str) -> Optional[CompanyDetail]:
        """Get company details by domain."""
        # Get the latest pipeline run for this domain
        run_query = """
            SELECT
                pr.run_id,
                pr.company_id,
                pr.company_name,
                pr.domain,
                pr.status,
                pr.started_at,
                pr.completed_at,
                EXTRACT(EPOCH FROM (pr.completed_at - pr.started_at)) as processing_time_seconds,
                pr.fill_rate,
                pr.cost_usd,
                pr.error_message
            FROM pipeline_runs pr
            WHERE pr.domain = $1
            ORDER BY pr.started_at DESC
            LIMIT 1
        """
        run_row = await self.fetchrow(run_query, domain)

        if not run_row:
            return None

        # Get company details
        company_query = """
            SELECT
                company_id,
                company_name,
                legal_name,
                hq_country,
                hq_city,
                founded_year,
                website,
                description,
                company_type,
                employee_count_range,
                logo_url
            FROM companies
            WHERE website ILIKE '%' || $1 || '%'
            LIMIT 1
        """
        company_row = await self.fetchrow(company_query, domain)

        # Get sources from llm_call_logs
        sources_query = """
            SELECT DISTINCT
                'web' as type,
                'Pipeline Log' as title,
                NOW()::text as retrieved_at,
                domain as url
            FROM pipeline_runs
            WHERE domain = $1
            LIMIT 50
        """
        sources_rows = await self.fetch(sources_query, run_row['domain'])

        # Build fields list from all tables
        fields = await self._get_company_fields(run_row['company_id'] or 0, domain)

        return CompanyDetail(
            company_id=company_row['company_id'] if company_row else run_row['run_id'],
            company_name=run_row['company_name'],
            domain=run_row['domain'],
            status=run_row['status'],
            created_at=run_row['started_at'],
            completed_at=run_row['completed_at'],
            processing_time_seconds=run_row['processing_time_seconds'],
            fill_rate=float(run_row['fill_rate']) if run_row['fill_rate'] else None,
            total_cost_usd=float(run_row['cost_usd']) if run_row['cost_usd'] else None,
            legal_name=company_row['legal_name'] if company_row else None,
            hq_country=company_row['hq_country'] if company_row else None,
            hq_city=company_row['hq_city'] if company_row else None,
            founded_year=company_row['founded_year'] if company_row else None,
            description=company_row['description'] if company_row else None,
            company_type=company_row['company_type'] if company_row else None,
            employee_count_range=company_row['employee_count_range'] if company_row else None,
            logo_url=company_row['logo_url'] if company_row else None,
            fields=fields,
            sources=[Source(url=r['url'], title=r['title'], type=r['type'], retrieved_at=r['retrieved_at']).model_dump() for r in sources_rows],
            errors=[run_row['error_message']] if run_row['error_message'] else [],
        )

    async def _get_company_fields(self, company_id: int, domain: str) -> List[FieldData]:
        """Get all extracted fields for a company."""
        fields = []
        logger.info(f"Getting fields for company_id={company_id}, domain={domain}")

        # Query all tables and build field list
        tables_to_query = [
            ('products', ['product_name', 'product_type', 'description', 'status']),
            ('asset_classes', ['asset_class', 'is_primary', 'maturity_level']),
            ('features', ['feature_category', 'feature_name', 'feature_tier', 'description']),
            ('integrations', ['partner_name', 'integration_type', 'integration_depth', 'status']),
            ('funding_rounds', ['round_type', 'amount_usd', 'date', 'lead_investor']),
            ('compliance_certifications', ['certification_type', 'status', 'issued_date']),
            ('regulatory_licenses', ['jurisdiction', 'license_type', 'status', 'regulator_name']),
            ('platform_metrics', ['total_aum_tokenized_usd', 'number_of_issuances', 'number_of_clients']),
        ]

        for table_name, columns in tables_to_query:
            try:
                query = f"""
                    SELECT {', '.join(columns)}, _citations
                    FROM {table_name}
                    WHERE company_id = $1
                    LIMIT 10
                """
                rows = await self.fetch(query, company_id)
                logger.info(f"Query {table_name}: found {len(rows)} rows for company_id={company_id}")

                for row in rows:
                    for col in columns:
                        if row[col] is not None:
                            field_name = f"{table_name}_{col}"

                            # Parse _citations JSON if it's a string
                            citations_json = row.get('_citations')
                            if isinstance(citations_json, str):
                                import json
                                try:
                                    citations = json.loads(citations_json)
                                except:
                                    citations = {}
                            else:
                                citations = citations_json or {}

                            field_citations = citations.get(col, {})
                            sources = list(field_citations.get('sources', [])) if isinstance(field_citations, dict) else []

                            fields.append(FieldData(
                                field_name=field_name,
                                value=row[col],
                                confidence=field_citations.get('confidence', 0.8) if isinstance(field_citations, dict) else 0.8,
                                sources=[str(s) for s in sources] if sources else [],
                            ).model_dump())
            except Exception as e:
                logger.error(f"Error querying {table_name}: {e}")
                continue

        logger.info(f"Total fields found: {len(fields)}")
        return fields

    async def create_pipeline_run(
        self,
        company_name: str,
        domain: str,
        llm_provider: str = "openai",
        llm_model: str = "gpt-4o",
    ) -> int:
        """Create a new pipeline run."""
        query = """
            INSERT INTO pipeline_runs (company_name, domain, llm_provider, llm_model, status)
            VALUES ($1, $2, $3, $4, 'running')
            RETURNING run_id
        """
        row = await self.fetchrow(query, company_name, domain, llm_provider, llm_model)
        return row['run_id']

    async def update_pipeline_run(
        self,
        run_id: int,
        status: str,
        fill_rate: Optional[float] = None,
        duration_secs: Optional[float] = None,
        cost_usd: Optional[float] = None,
        error_message: Optional[str] = None,
    ):
        """Update pipeline run status."""
        query = """
            UPDATE pipeline_runs
            SET status = $1,
                completed_at = NOW(),
                fill_rate = $2,
                duration_secs = $3,
                cost_usd = $4,
                error_message = $5
            WHERE run_id = $6
        """
        await self.execute(
            query,
            status,
            fill_rate,
            duration_secs,
            cost_usd,
            error_message,
            run_id,
        )


# Global database instance
db = Database()
