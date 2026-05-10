-- =============================================================================
-- 51 Insights — Tokenized Assets Pipeline
-- PostgreSQL Schema
-- =============================================================================
-- Design notes:
--   • Every table has a `_citations` JSONB column storing {field: {source_url, confidence}}
--     so the data columns match the xlsx exactly and citations travel alongside them.
--   • All FKs reference companies(company_id).
--   • Upsert-friendly: natural unique keys are defined on each table.
--   • pipeline_runs tracks every extraction run for auditability.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Extensions
-- ---------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS "pgcrypto";   -- gen_random_uuid() if needed


-- ---------------------------------------------------------------------------
-- 1. companies
--    Root table. All other tables FK back here.
--    The xlsx mixes social/profile fields into this table — kept as-is.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS companies (
    company_id              SERIAL PRIMARY KEY,
    company_name            VARCHAR(255)        NOT NULL,
    legal_name              VARCHAR(255),
    hq_country              VARCHAR(100),
    hq_city                 VARCHAR(100),
    founded_year            INTEGER,
    website                 VARCHAR(500),
    description             TEXT,
    company_type            VARCHAR(50),        -- platform | protocol | fund | bank | etc.
    operational_status      VARCHAR(50)         DEFAULT 'active',
    employee_count_range    VARCHAR(50),        -- e.g. 51-100
    logo_url                VARCHAR(500),
    is_active               BOOLEAN             DEFAULT TRUE,
    -- social presence (one row per company; multi-platform stored in social_profiles)
    platform                VARCHAR(50),        -- twitter | linkedin | etc.
    url                     VARCHAR(500),
    handle                  VARCHAR(255),
    follower_count          INTEGER,
    total_employees         INTEGER,
    founder_still_active    BOOLEAN,
    -- pipeline metadata
    extracted_at            TIMESTAMPTZ,
    created_at              TIMESTAMPTZ         NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ         NOT NULL DEFAULT NOW(),
    _citations              JSONB               DEFAULT '{}'::JSONB,

    CONSTRAINT uq_companies_name UNIQUE (company_name)
);

CREATE INDEX IF NOT EXISTS idx_companies_name    ON companies (company_name);
CREATE INDEX IF NOT EXISTS idx_companies_website ON companies (website);
CREATE INDEX IF NOT EXISTS idx_companies_active  ON companies (is_active);


-- ---------------------------------------------------------------------------
-- 2. products
--    One row per product per company.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS products (
    product_id      SERIAL PRIMARY KEY,
    company_id      INTEGER             NOT NULL REFERENCES companies (company_id) ON DELETE CASCADE,
    product_name    VARCHAR(255)        NOT NULL,
    product_type    VARCHAR(100),       -- issuance_platform | transfer_agent | marketplace | etc.
    description     TEXT,
    launch_date     DATE,
    status          VARCHAR(50)         DEFAULT 'active',
    pricing_model   VARCHAR(50),        -- saas | transaction | hybrid | free | etc.
    pricing_notes   TEXT,
    target_segment  VARCHAR(100),       -- institutional | retail | both
    extracted_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ         NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ         NOT NULL DEFAULT NOW(),
    _citations      JSONB               DEFAULT '{}'::JSONB,

    CONSTRAINT uq_products UNIQUE (company_id, product_name)
);

CREATE INDEX IF NOT EXISTS idx_products_company ON products (company_id);


-- ---------------------------------------------------------------------------
-- 3. asset_classes
--    Which asset classes a company supports, and how mature that support is.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS asset_classes (
    asset_class_id  SERIAL PRIMARY KEY,
    company_id      INTEGER             NOT NULL REFERENCES companies (company_id) ON DELETE CASCADE,
    asset_class     VARCHAR(100)        NOT NULL, -- real_estate | funds | equity | debt | art | etc.
    is_primary      BOOLEAN             DEFAULT FALSE,
    maturity_level  VARCHAR(50),                  -- production | beta | planned
    notes           TEXT,
    extracted_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ         NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ         NOT NULL DEFAULT NOW(),
    _citations      JSONB               DEFAULT '{}'::JSONB,

    CONSTRAINT uq_asset_classes UNIQUE (company_id, asset_class)
);

CREATE INDEX IF NOT EXISTS idx_asset_classes_company ON asset_classes (company_id);


-- ---------------------------------------------------------------------------
-- 4. features
--    Platform feature breakdown, one row per feature.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS features (
    feature_id          SERIAL PRIMARY KEY,
    company_id          INTEGER         NOT NULL REFERENCES companies (company_id) ON DELETE CASCADE,
    feature_category    VARCHAR(100),   -- issuance | compliance | secondary | investor_mgmt | etc.
    feature_name        VARCHAR(255)    NOT NULL,
    feature_tier        VARCHAR(50),    -- basic | advanced | enterprise
    description         TEXT,
    extracted_at        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    _citations          JSONB           DEFAULT '{}'::JSONB,

    CONSTRAINT uq_features UNIQUE (company_id, feature_name)
);

CREATE INDEX IF NOT EXISTS idx_features_company ON features (company_id);


-- ---------------------------------------------------------------------------
-- 5. token_standards
--    Token standards the platform natively supports.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS token_standards (
    standard_id         SERIAL PRIMARY KEY,
    company_id          INTEGER         NOT NULL REFERENCES companies (company_id) ON DELETE CASCADE,
    standard_name       VARCHAR(100)    NOT NULL, -- ERC-3643 | ERC-1400 | ERC-20 | SPL | etc.
    is_native_support   BOOLEAN         DEFAULT FALSE,
    compliance_built_in BOOLEAN         DEFAULT FALSE,
    notes               TEXT,
    extracted_at        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    _citations          JSONB           DEFAULT '{}'::JSONB,

    CONSTRAINT uq_token_standards UNIQUE (company_id, standard_name)
);

CREATE INDEX IF NOT EXISTS idx_token_standards_company ON token_standards (company_id);


-- ---------------------------------------------------------------------------
-- 6. integrations
--    Third-party integrations (custodians, KYC, oracles, etc.)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS integrations (
    integration_id      SERIAL PRIMARY KEY,
    company_id          INTEGER         NOT NULL REFERENCES companies (company_id) ON DELETE CASCADE,
    partner_name        VARCHAR(255)    NOT NULL, -- Fireblocks | Onfido | Chainlink | etc.
    integration_type    VARCHAR(100),             -- custodian | kyc | oracle | wallet | exchange
    integration_depth   VARCHAR(50),              -- native | api | partnership
    status              VARCHAR(50)     DEFAULT 'active',
    description         TEXT,
    extracted_at        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    _citations          JSONB           DEFAULT '{}'::JSONB,

    CONSTRAINT uq_integrations UNIQUE (company_id, partner_name, integration_type)
);

CREATE INDEX IF NOT EXISTS idx_integrations_company ON integrations (company_id);


-- ---------------------------------------------------------------------------
-- 7. funding_rounds
--    Investment history — multiple rows per company.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS funding_rounds (
    round_id        SERIAL PRIMARY KEY,
    company_id      INTEGER             NOT NULL REFERENCES companies (company_id) ON DELETE CASCADE,
    round_type      VARCHAR(50),        -- seed | pre_seed | series_a | series_b | grant | etc.
    amount_usd      DECIMAL(15, 2),
    date            DATE,
    lead_investor   VARCHAR(255),
    other_investors TEXT,               -- comma-separated or free text
    valuation_usd   DECIMAL(15, 2),
    source_url      VARCHAR(500),
    notes           TEXT,
    extracted_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ         NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ         NOT NULL DEFAULT NOW(),
    _citations      JSONB               DEFAULT '{}'::JSONB,

    CONSTRAINT uq_funding_rounds UNIQUE (company_id, round_type, date)
);

CREATE INDEX IF NOT EXISTS idx_funding_rounds_company ON funding_rounds (company_id);


-- ---------------------------------------------------------------------------
-- 8. governance_model
--    One row per company (singleton). Upsert on company_id.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS governance_model (
    governance_id               SERIAL PRIMARY KEY,
    company_id                  INTEGER         NOT NULL REFERENCES companies (company_id) ON DELETE CASCADE,
    governance_type             VARCHAR(50),    -- centralized | dao | hybrid
    has_token                   BOOLEAN         DEFAULT FALSE,
    token_symbol                VARCHAR(20),
    token_distribution_notes    TEXT,
    treasury_runway_months      INTEGER,
    total_funding_usd           DECIMAL(15, 2),
    revenue_status              VARCHAR(50),    -- pre_revenue | revenue_generating | profitable
    last_assessed_at            DATE,
    extracted_at                TIMESTAMPTZ,
    created_at                  TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at                  TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    _citations                  JSONB           DEFAULT '{}'::JSONB,

    CONSTRAINT uq_governance_model UNIQUE (company_id)
);


-- ---------------------------------------------------------------------------
-- 9. compliance_certifications
--    SOC2, ISO 27001, etc. Multiple rows per company.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS compliance_certifications (
    cert_id             SERIAL PRIMARY KEY,
    company_id          INTEGER         NOT NULL REFERENCES companies (company_id) ON DELETE CASCADE,
    certification_type  VARCHAR(100)    NOT NULL, -- SOC2_Type_II | ISO_27001 | PCI_DSS | etc.
    status              VARCHAR(50),              -- certified | in_progress | expired
    issued_date         DATE,
    expiry_date         DATE,
    auditor             VARCHAR(255),
    certificate_url     VARCHAR(500),
    extracted_at        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    _citations          JSONB           DEFAULT '{}'::JSONB,

    CONSTRAINT uq_compliance_certifications UNIQUE (company_id, certification_type)
);

CREATE INDEX IF NOT EXISTS idx_compliance_certs_company ON compliance_certifications (company_id);


-- ---------------------------------------------------------------------------
-- 10. sla_commitments
--     Uptime, response time, and other SLA metrics.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sla_commitments (
    sla_id                  SERIAL PRIMARY KEY,
    company_id              INTEGER         NOT NULL REFERENCES companies (company_id) ON DELETE CASCADE,
    metric                  VARCHAR(100)    NOT NULL, -- uptime | response_time | recovery_time
    committed_value         VARCHAR(100),             -- e.g. 99.95%
    actual_value_last_12m   VARCHAR(100),
    measurement_period      VARCHAR(50),              -- monthly | quarterly | annual
    has_penalty_clause      BOOLEAN         DEFAULT FALSE,
    notes                   TEXT,
    extracted_at            TIMESTAMPTZ,
    created_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    _citations              JSONB           DEFAULT '{}'::JSONB,

    CONSTRAINT uq_sla_commitments UNIQUE (company_id, metric)
);

CREATE INDEX IF NOT EXISTS idx_sla_commitments_company ON sla_commitments (company_id);


-- ---------------------------------------------------------------------------
-- 11. stability_table  (developer / enterprise readiness)
--     One row per company (singleton).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS stability_table (
    stability_id            SERIAL PRIMARY KEY,
    company_id              INTEGER         NOT NULL REFERENCES companies (company_id) ON DELETE CASCADE,
    documentation_quality   VARCHAR(50),    -- poor | fair | good | excellent
    has_sandbox_environment BOOLEAN         DEFAULT FALSE,
    has_api_playground      BOOLEAN         DEFAULT FALSE,
    languages_supported     TEXT,           -- free text or JSON array
    extracted_at            TIMESTAMPTZ,
    created_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    _citations              JSONB           DEFAULT '{}'::JSONB,

    CONSTRAINT uq_stability_table UNIQUE (company_id)
);


-- ---------------------------------------------------------------------------
-- 12. tech_stack
--     Blockchain layers, smart contract languages, infra tech.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tech_stack (
    tech_id             SERIAL PRIMARY KEY,
    company_id          INTEGER         NOT NULL REFERENCES companies (company_id) ON DELETE CASCADE,
    component           VARCHAR(100)    NOT NULL, -- smart_contracts | indexer | storage | frontend
    technology          VARCHAR(255)    NOT NULL, -- Solidity | Rust | IPFS | React | etc.
    version             VARCHAR(50),
    chains_supported    TEXT,                     -- JSON array: ["Ethereum","Polygon","Solana"]
    mainnet_live        BOOLEAN         DEFAULT FALSE,
    notes               TEXT,
    extracted_at        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    _citations          JSONB           DEFAULT '{}'::JSONB,

    CONSTRAINT uq_tech_stack UNIQUE (company_id, component, technology)
);

CREATE INDEX IF NOT EXISTS idx_tech_stack_company ON tech_stack (company_id);


-- ---------------------------------------------------------------------------
-- 13. api_capabilities
--     One row per company (singleton) — REST/GraphQL/WebSocket capabilities.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS api_capabilities (
    api_id                  SERIAL PRIMARY KEY,
    company_id              INTEGER         NOT NULL REFERENCES companies (company_id) ON DELETE CASCADE,
    api_type                VARCHAR(50),    -- REST | GraphQL | WebSocket | gRPC
    documentation_url       VARCHAR(500),
    has_sandbox             BOOLEAN         DEFAULT FALSE,
    rate_limit_tier         VARCHAR(100),   -- e.g. "1000 req/min (enterprise)"
    authentication_method   VARCHAR(100),   -- OAuth2 | API_Key | JWT
    sdk_languages           TEXT,           -- JSON array: ["JavaScript","Python"]
    webhook_support         BOOLEAN         DEFAULT FALSE,
    api_versioning          BOOLEAN         DEFAULT FALSE,
    extracted_at            TIMESTAMPTZ,
    created_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    _citations              JSONB           DEFAULT '{}'::JSONB,

    CONSTRAINT uq_api_capabilities UNIQUE (company_id)
);


-- ---------------------------------------------------------------------------
-- 14. partnerships
--     Strategic and integration partners announced publicly.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS partnerships (
    partnership_id      SERIAL PRIMARY KEY,
    company_id          INTEGER         NOT NULL REFERENCES companies (company_id) ON DELETE CASCADE,
    partner_name        VARCHAR(255)    NOT NULL,
    partner_type        VARCHAR(100),   -- asset_manager | custodian | exchange | bank | tech
    partnership_tier    VARCHAR(50),    -- strategic | integration | reseller | referral
    announced_date      DATE,
    description         TEXT,
    source_url          VARCHAR(500),
    extracted_at        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    _citations          JSONB           DEFAULT '{}'::JSONB,

    CONSTRAINT uq_partnerships UNIQUE (company_id, partner_name)
);

CREATE INDEX IF NOT EXISTS idx_partnerships_company ON partnerships (company_id);


-- ---------------------------------------------------------------------------
-- 15. exchange_listings
--     Exchanges or trading venues where company tokens are accessible.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS exchange_listings (
    listing_id              SERIAL PRIMARY KEY,
    company_id              INTEGER         NOT NULL REFERENCES companies (company_id) ON DELETE CASCADE,
    exchange_name           VARCHAR(255)    NOT NULL,
    exchange_type           VARCHAR(50),    -- ATS | MTF | DEX | CEX | OTC
    connectivity_type       VARCHAR(50),    -- direct_listing | api | white_label
    status                  VARCHAR(50)     DEFAULT 'active',
    asset_classes_tradeable TEXT,           -- JSON array: ["equities","debt"]
    extracted_at            TIMESTAMPTZ,
    created_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    _citations              JSONB           DEFAULT '{}'::JSONB,

    CONSTRAINT uq_exchange_listings UNIQUE (company_id, exchange_name)
);

CREATE INDEX IF NOT EXISTS idx_exchange_listings_company ON exchange_listings (company_id);


-- ---------------------------------------------------------------------------
-- 16. regulatory_licenses
--     Licenses, registrations, and regulatory approvals per jurisdiction.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS regulatory_licenses (
    license_id              SERIAL PRIMARY KEY,
    company_id              INTEGER         NOT NULL REFERENCES companies (company_id) ON DELETE CASCADE,
    jurisdiction            VARCHAR(100)    NOT NULL, -- United States | EU | Singapore | etc.
    license_type            VARCHAR(100)    NOT NULL, -- broker_dealer | transfer_agent | VASP | MiCA
    status                  VARCHAR(50),              -- active | pending | expired | revoked
    issued_date             DATE,
    license_number          VARCHAR(255),
    regulator_name          VARCHAR(255),             -- SEC | FINRA | FCA | MAS | etc.
    coverage_type           VARCHAR(100),             -- full_operations | restricted | pilot
    investor_types_allowed  TEXT,                     -- JSON array: ["retail","institutional"]
    asset_classes_allowed   TEXT,                     -- JSON array: ["equities","bonds"]
    regulatory_basis        VARCHAR(255),             -- e.g. MiFID II passporting
    extracted_at            TIMESTAMPTZ,
    created_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    _citations              JSONB           DEFAULT '{}'::JSONB,

    CONSTRAINT uq_regulatory_licenses UNIQUE (company_id, jurisdiction, license_type)
);

CREATE INDEX IF NOT EXISTS idx_regulatory_licenses_company     ON regulatory_licenses (company_id);
CREATE INDEX IF NOT EXISTS idx_regulatory_licenses_jurisdiction ON regulatory_licenses (jurisdiction);


-- ---------------------------------------------------------------------------
-- 17. platform_metrics
--     AUM, issuances, active tokens, client counts. One row per company (singleton).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS platform_metrics (
    metric_id               SERIAL PRIMARY KEY,
    company_id              INTEGER         NOT NULL REFERENCES companies (company_id) ON DELETE CASCADE,
    total_aum_tokenized_usd DECIMAL(18, 2),
    number_of_issuances     INTEGER,
    number_of_active_tokens INTEGER,
    number_of_clients       INTEGER,
    notable_clients         TEXT,           -- JSON array: ["BlackRock","KKR"]
    as_of_date              DATE,           -- snapshot date for these metrics
    extracted_at            TIMESTAMPTZ,
    created_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    _citations              JSONB           DEFAULT '{}'::JSONB,

    CONSTRAINT uq_platform_metrics UNIQUE (company_id)
);


-- ---------------------------------------------------------------------------
-- 18. deal_case_studies
--     Notable tokenization deals. Multiple rows per company.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS deal_case_studies (
    deal_id         SERIAL PRIMARY KEY,
    company_id      INTEGER         NOT NULL REFERENCES companies (company_id) ON DELETE CASCADE,
    title           VARCHAR(255)    NOT NULL,
    asset_class     VARCHAR(100),
    deal_size_usd   DECIMAL(18, 2),
    client_name     VARCHAR(255),
    jurisdiction    VARCHAR(100),
    completion_date DATE,
    description     TEXT,
    public_url      VARCHAR(500),
    extracted_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    _citations      JSONB           DEFAULT '{}'::JSONB,

    CONSTRAINT uq_deal_case_studies UNIQUE (company_id, title)
);

CREATE INDEX IF NOT EXISTS idx_deal_case_studies_company ON deal_case_studies (company_id);


-- ---------------------------------------------------------------------------
-- 19. pipeline_runs  (audit / observability — not in xlsx, essential for ops)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id          SERIAL PRIMARY KEY,
    company_id      INTEGER         REFERENCES companies (company_id) ON DELETE SET NULL,
    company_name    VARCHAR(255),               -- denormalised for easy querying
    domain          VARCHAR(255),
    started_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,
    status          VARCHAR(50)     DEFAULT 'running',  -- running | completed | failed
    llm_provider    VARCHAR(100),               -- openai | anthropic | zai | openrouter
    llm_model       VARCHAR(100),
    fill_rate       DECIMAL(5, 4),              -- 0.0–1.0  all fields inc. defaults
    real_fill       DECIMAL(5, 4),              -- fields with confidence >= 0.4
    high_fill       DECIMAL(5, 4),              -- fields with confidence >= 0.7
    total_fields    INTEGER,
    filled_fields   INTEGER,
    pages_scraped   INTEGER,
    search_results  INTEGER,
    duration_secs   DECIMAL(8, 2),
    cost_usd        DECIMAL(10, 6)  DEFAULT 0,
    error_message   TEXT,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pipeline_runs_company    ON pipeline_runs (company_id);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_started_at ON pipeline_runs (started_at DESC);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_status     ON pipeline_runs (status);


-- ---------------------------------------------------------------------------
-- 20. llm_call_logs  (per-call cost tracking)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS llm_call_logs (
    log_id              SERIAL PRIMARY KEY,
    run_id              INTEGER         REFERENCES pipeline_runs (run_id) ON DELETE CASCADE,
    company_name        VARCHAR(255),
    batch_name          VARCHAR(100),               -- e.g. BatchA_Company, knowledge_gap
    provider            VARCHAR(50)     NOT NULL,   -- openai | anthropic | zai | openrouter
    model               VARCHAR(100)    NOT NULL,
    prompt_tokens       INTEGER,
    completion_tokens   INTEGER,
    total_tokens        INTEGER,
    cost_usd            DECIMAL(10, 6),             -- calculated cost
    latency_ms          INTEGER,                    -- response time in ms
    system_prompt_hash  VARCHAR(64),                -- SHA-256 hash of system prompt
    user_prompt_chars   INTEGER,                    -- length of user prompt
    response_chars      INTEGER,                    -- length of raw response
    success             BOOLEAN         DEFAULT TRUE,
    error_message       TEXT,
    called_at           TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_llm_call_logs_run     ON llm_call_logs (run_id);
CREATE INDEX IF NOT EXISTS idx_llm_call_logs_provider ON llm_call_logs (provider);
CREATE INDEX IF NOT EXISTS idx_llm_call_logs_called   ON llm_call_logs (called_at DESC);


-- ---------------------------------------------------------------------------
-- updated_at auto-trigger
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$
DECLARE
    t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'companies','products','asset_classes','features','token_standards',
        'integrations','funding_rounds','governance_model','compliance_certifications',
        'sla_commitments','stability_table','tech_stack','api_capabilities',
        'partnerships','exchange_listings','regulatory_licenses',
        'platform_metrics','deal_case_studies'
    ] LOOP
        EXECUTE format(
            'CREATE TRIGGER trg_%I_updated_at
             BEFORE UPDATE ON %I
             FOR EACH ROW EXECUTE FUNCTION set_updated_at()',
            t, t
        );
    END LOOP;
END;
$$;
