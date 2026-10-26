CREATE TABLE IF NOT EXISTS companies (
    id TEXT PRIMARY KEY,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS news_items (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_news_items_company ON news_items(company_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS analysis_jobs (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL REFERENCES companies(id),
    event_id TEXT NOT NULL REFERENCES news_items(id),
    status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'complete', 'failed')),
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_analysis_jobs_company ON analysis_jobs(company_id, created_at DESC);

CREATE TABLE IF NOT EXISTS analyses (
    id TEXT PRIMARY KEY REFERENCES analysis_jobs(id) ON DELETE CASCADE,
    company_id TEXT NOT NULL REFERENCES companies(id),
    event_id TEXT NOT NULL REFERENCES news_items(id),
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE analysis_jobs ADD COLUMN IF NOT EXISTS question TEXT NOT NULL DEFAULT '';

CREATE TABLE IF NOT EXISTS bank_research (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    page INTEGER NOT NULL,
    content TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS llm_budget (
    usage_day DATE PRIMARY KEY,
    reserved_rub NUMERIC(12,2) NOT NULL DEFAULT 0
);
ALTER TABLE analysis_jobs ADD COLUMN IF NOT EXISTS attempts INTEGER NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS analysis_outbox (
    analysis_id TEXT PRIMARY KEY REFERENCES analysis_jobs(id) ON DELETE CASCADE,
    published_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_analysis_outbox_pending ON analysis_outbox(created_at) WHERE published_at IS NULL;

CREATE TABLE IF NOT EXISTS analysis_feedback (
    id BIGSERIAL PRIMARY KEY,
    analysis_id TEXT NOT NULL REFERENCES analysis_jobs(id) ON DELETE CASCADE,
    rating TEXT NOT NULL CHECK (rating IN ('useful','not_useful')),
    comment TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_analysis_feedback_analysis ON analysis_feedback(analysis_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_companies_okved_prefix ON companies ((left(payload->>'okved', 2)));
CREATE INDEX IF NOT EXISTS idx_companies_region ON companies ((payload->>'region'));

CREATE TABLE IF NOT EXISTS news_refresh_jobs (
    company_id TEXT PRIMARY KEY REFERENCES companies(id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK(status IN ('queued','running','complete','failed')),
    error_message TEXT,
    requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_news_refresh_queued ON news_refresh_jobs(requested_at) WHERE status='queued';

CREATE TABLE IF NOT EXISTS dataset_imports (
    name TEXT PRIMARY KEY,
    content_hash TEXT NOT NULL,
    record_count INTEGER NOT NULL,
    imported_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
