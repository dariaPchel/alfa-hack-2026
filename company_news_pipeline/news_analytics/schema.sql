PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS import_batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_filename TEXT NOT NULL,
    relations_filename TEXT NOT NULL,
    company_sha256 TEXT,
    relations_sha256 TEXT,
    mock_data INTEGER NOT NULL DEFAULT 0 CHECK (mock_data IN (0, 1)),
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL DEFAULT 'started'
        CHECK (status IN ('started', 'completed', 'partial', 'failed')),
    summary_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS active_dataset (
    singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
    import_batch_id INTEGER NOT NULL REFERENCES import_batches(id),
    activated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS synthetic_companies (
    synthetic_id TEXT NOT NULL,
    org_type TEXT,
    okfs_name TEXT,
    company_age_years_gradation TEXT,
    eco_mark_label TEXT,
    mainokved_code TEXT,
    mainokved_name TEXT,
    negativemark TEXT,
    amount_workers_fns_gradation TEXT,
    amount_workers_spark_gradation TEXT,
    cl_type TEXT,
    cl_product_rko_mark TEXT,
    cl_product_gar_mark TEXT,
    cl_product_loa_mark TEXT,
    cl_product_lea_mark TEXT,
    cl_product_dep_mark TEXT,
    cl_product_zpp_mark TEXT,
    fts_flag TEXT,
    fts_country_name TEXT,
    factoring_mark TEXT,
    revenue_company TEXT,
    group_id TEXT,
    city TEXT,
    region TEXT,
    source_row_json TEXT NOT NULL DEFAULT '{}',
    import_batch_id INTEGER NOT NULL REFERENCES import_batches(id),
    PRIMARY KEY (import_batch_id, synthetic_id)
);

CREATE INDEX IF NOT EXISTS idx_synthetic_companies_okved
    ON synthetic_companies(import_batch_id, mainokved_code, mainokved_name);
CREATE INDEX IF NOT EXISTS idx_synthetic_companies_region
    ON synthetic_companies(import_batch_id, region, city);
CREATE INDEX IF NOT EXISTS idx_synthetic_companies_group
    ON synthetic_companies(import_batch_id, group_id);

CREATE TABLE IF NOT EXISTS person_company_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    synthetic_f TEXT NOT NULL,
    city_name TEXT,
    rc_name TEXT,
    synthetic_id TEXT NOT NULL,
    source_row_json TEXT NOT NULL DEFAULT '{}',
    import_batch_id INTEGER NOT NULL REFERENCES import_batches(id)
);

CREATE INDEX IF NOT EXISTS idx_person_company_links_company
    ON person_company_links(synthetic_id);
CREATE INDEX IF NOT EXISTS idx_person_company_links_person
    ON person_company_links(synthetic_f);

CREATE TABLE IF NOT EXISTS payment_edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    beneficiary TEXT NOT NULL,
    payer TEXT NOT NULL,
    pay_amt TEXT,
    pay_cnt TEXT,
    source_row_json TEXT NOT NULL DEFAULT '{}',
    import_batch_id INTEGER NOT NULL REFERENCES import_batches(id)
);

CREATE INDEX IF NOT EXISTS idx_payment_edges_payer
    ON payment_edges(payer);
CREATE INDEX IF NOT EXISTS idx_payment_edges_beneficiary
    ON payment_edges(beneficiary);

CREATE TABLE IF NOT EXISTS peer_scores (
    dataset_batch_id INTEGER NOT NULL REFERENCES import_batches(id),
    target_synthetic_id TEXT NOT NULL,
    peer_synthetic_id TEXT NOT NULL,
    similarity_score REAL NOT NULL CHECK (similarity_score >= 0 AND similarity_score <= 1),
    feature_scores_json TEXT NOT NULL DEFAULT '{}',
    calculated_at TEXT NOT NULL,
    PRIMARY KEY (dataset_batch_id, target_synthetic_id, peer_synthetic_id),
    FOREIGN KEY (dataset_batch_id, target_synthetic_id)
        REFERENCES synthetic_companies(import_batch_id, synthetic_id),
    FOREIGN KEY (dataset_batch_id, peer_synthetic_id)
        REFERENCES synthetic_companies(import_batch_id, synthetic_id),
    CHECK (target_synthetic_id <> peer_synthetic_id)
);

CREATE TABLE IF NOT EXISTS schema_warnings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    import_batch_id INTEGER NOT NULL REFERENCES import_batches(id),
    filename TEXT NOT NULL,
    row_number INTEGER,
    column_name TEXT,
    warning_code TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS news_events (
    event_id TEXT PRIMARY KEY,
    canonical_url TEXT NOT NULL UNIQUE,
    content_fingerprint TEXT NOT NULL,
    title TEXT NOT NULL,
    snippet TEXT NOT NULL DEFAULT '',
    publisher TEXT,
    provider_published_at TEXT,
    published_at TEXT,
    date_status TEXT NOT NULL,
    image_url TEXT,
    provider TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_news_events_published ON news_events(published_at);
CREATE INDEX IF NOT EXISTS idx_news_events_fingerprint ON news_events(content_fingerprint);

CREATE TABLE IF NOT EXISTS news_query_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    synthetic_id TEXT NOT NULL,
    window_name TEXT NOT NULL CHECK (window_name IN ('90d', '7d', '24h')),
    query TEXT NOT NULL,
    category TEXT NOT NULL,
    provider TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('success', 'partial', 'failed')),
    result_count INTEGER NOT NULL DEFAULT 0,
    error_code TEXT,
    warning TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_news_runs_company_window ON news_query_runs(synthetic_id, window_name, finished_at);

CREATE TABLE IF NOT EXISTS company_news_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    synthetic_id TEXT NOT NULL,
    event_id TEXT NOT NULL REFERENCES news_events(event_id),
    query_run_id INTEGER NOT NULL REFERENCES news_query_runs(id),
    window_name TEXT NOT NULL CHECK (window_name IN ('90d', '7d', '24h')),
    matched_search_query TEXT NOT NULL,
    profile_reasons_json TEXT NOT NULL DEFAULT '[]',
    selection_rank INTEGER,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    UNIQUE (synthetic_id, event_id, query_run_id)
);

CREATE INDEX IF NOT EXISTS idx_company_news_lookup ON company_news_links(synthetic_id, window_name, last_seen_at);

CREATE TABLE IF NOT EXISTS rejected_news_candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    synthetic_id TEXT NOT NULL,
    query_run_id INTEGER NOT NULL REFERENCES news_query_runs(id),
    candidate_url TEXT,
    candidate_title TEXT,
    rejection_reason TEXT NOT NULL,
    provider_payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS company_news_window_status (
    synthetic_id TEXT NOT NULL,
    window_name TEXT NOT NULL CHECK (window_name IN ('90d', '7d', '24h')),
    last_started_at TEXT NOT NULL,
    last_success_at TEXT,
    last_error TEXT,
    status TEXT NOT NULL CHECK (status IN ('success', 'partial', 'failed')),
    PRIMARY KEY (synthetic_id, window_name)
);

CREATE TABLE IF NOT EXISTS llm_budget_reservations (
    request_id TEXT PRIMARY KEY,
    day_key TEXT NOT NULL,
    role TEXT NOT NULL,
    model_alias TEXT NOT NULL,
    estimated_tokens INTEGER NOT NULL,
    reserved_cost_rub REAL NOT NULL,
    actual_tokens INTEGER,
    actual_cost_rub REAL,
    status TEXT NOT NULL CHECK (status IN ('reserved', 'completed', 'failed', 'cancelled')),
    created_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_llm_budget_day ON llm_budget_reservations(day_key, status);

CREATE TABLE IF NOT EXISTS agent_tool_audit (
    request_id TEXT PRIMARY KEY,
    role TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    tool_version TEXT,
    arguments_sha256 TEXT NOT NULL,
    provider TEXT,
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL CHECK (status IN ('success', 'partial', 'error')),
    error_code TEXT,
    elapsed_ms INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_agent_tool_audit_created ON agent_tool_audit(created_at);

CREATE TABLE IF NOT EXISTS company_news_analyses (
    analysis_id TEXT PRIMARY KEY,
    synthetic_id TEXT NOT NULL,
    dataset_batch_id INTEGER,
    event_ids_json TEXT NOT NULL DEFAULT '[]',
    model_alias TEXT NOT NULL,
    status TEXT NOT NULL,
    source_ids_json TEXT NOT NULL DEFAULT '[]',
    analysis_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_news_analyses_company ON company_news_analyses(synthetic_id, created_at);
