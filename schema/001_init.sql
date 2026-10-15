CREATE DATABASE IF NOT EXISTS skill_warden;

CREATE TABLE skill_warden.skills
(
    publisher LowCardinality(String),
    name String,
    version String,
    content_hash String,
    fetched_at DateTime64(3, 'UTC'),
    source_url String,
    inserted_at DateTime64(3, 'UTC') DEFAULT now64(3, 'UTC')
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(fetched_at)
ORDER BY (publisher, name, content_hash, fetched_at)
TTL fetched_at + INTERVAL 180 DAY
SETTINGS non_replicated_deduplication_window = 1000;

CREATE TABLE skill_warden.scan_runs
(
    run_id UUID,
    skill_hash String,
    started_at DateTime64(3, 'UTC'),
    finished_at Nullable(DateTime64(3, 'UTC')),
    backend Enum8('local' = 1, 'akash' = 2),
    status Enum8('running' = 1, 'completed' = 2, 'timeout' = 3, 'error' = 4),
    budget_cents UInt32,
    inserted_at DateTime64(3, 'UTC') DEFAULT now64(3, 'UTC')
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(started_at)
ORDER BY (started_at, run_id)
TTL started_at + INTERVAL 180 DAY
SETTINGS non_replicated_deduplication_window = 1000;

CREATE TABLE skill_warden.findings
(
    run_id UUID,
    source Enum8('semgrep' = 1, 'reader' = 2, 'canary' = 3, 'policy' = 4, 'jail' = 5),
    rule_id LowCardinality(String),
    severity Enum8('info' = 1, 'low' = 2, 'medium' = 3, 'high' = 4, 'critical' = 5, 'error' = 6),
    file String,
    evidence_hash String,
    excerpt String TTL observed_at + INTERVAL 14 DAY,
    indicator String DEFAULT '',
    observed_at DateTime64(3, 'UTC') DEFAULT now64(3, 'UTC'),
    inserted_at DateTime64(3, 'UTC') DEFAULT now64(3, 'UTC')
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(observed_at)
ORDER BY (run_id, source, rule_id, evidence_hash)
TTL observed_at + INTERVAL 180 DAY
SETTINGS non_replicated_deduplication_window = 1000;

CREATE TABLE skill_warden.model_io
(
    run_id UUID,
    model LowCardinality(String),
    prompt_hash String,
    response_hash String,
    response_json String TTL inserted_at + INTERVAL 14 DAY,
    injection_flag UInt8,
    inserted_at DateTime64(3, 'UTC') DEFAULT now64(3, 'UTC')
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(inserted_at)
ORDER BY (run_id, prompt_hash)
TTL inserted_at + INTERVAL 180 DAY
SETTINGS non_replicated_deduplication_window = 1000;

CREATE TABLE skill_warden.verdicts
(
    run_id UUID,
    decision Enum8('BLOCK' = 1, 'ASK' = 2, 'ALLOW' = 3),
    reason_code LowCardinality(String),
    signer LowCardinality(String),
    signature String,
    published_url String DEFAULT '',
    pr_url String DEFAULT '',
    immutable UInt8 DEFAULT 1,
    payload_hash String,
    prev_hash String DEFAULT '',
    signed_at DateTime64(3, 'UTC') DEFAULT now64(3, 'UTC')
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(signed_at)
ORDER BY (signed_at, run_id)
SETTINGS non_replicated_deduplication_window = 1000;

CREATE TABLE skill_warden.budget_events
(
    event_id UUID,
    run_id UUID,
    occurred_at DateTime64(3, 'UTC'),
    kind LowCardinality(String),
    cents Int64,
    inserted_at DateTime64(3, 'UTC') DEFAULT now64(3, 'UTC')
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(occurred_at)
ORDER BY (occurred_at, run_id, event_id)
TTL occurred_at + INTERVAL 180 DAY
SETTINGS non_replicated_deduplication_window = 1000;

ALTER TABLE skill_warden.findings
MODIFY COLUMN source Enum8('semgrep' = 1, 'reader' = 2, 'canary' = 3, 'policy' = 4, 'jail' = 5);

CREATE USER IF NOT EXISTS scanner IDENTIFIED WITH sha256_password BY 'test';
GRANT SELECT, INSERT ON skill_warden.* TO scanner;
GRANT ALTER UPDATE(status, finished_at) ON skill_warden.scan_runs TO scanner;
