"""
ODW.ai Desk — Observability Metrics (DEPLOY-004)

Prometheus metrics for monitoring and observability.
"""

from prometheus_client import Counter, Gauge, Histogram, Info

# Application info
APP_INFO = Info("desk_app", "ODW.ai Desk application information")
APP_INFO.info({"version": "1.0.0", "environment": "production"})

# Message metrics
MESSAGES_RECEIVED = Counter(
    "desk_messages_received_total",
    "Total messages received",
    ["channel", "status"],
)

MESSAGES_PROCESSED = Counter(
    "desk_messages_processed_total",
    "Total messages processed",
    ["channel", "sender_type"],
)

MESSAGES_DISPATCHED = Counter(
    "desk_messages_dispatched_total",
    "Total messages dispatched",
    ["channel", "status"],
)

# AI pipeline metrics
AI_PIPELINE_DURATION = Histogram(
    "desk_ai_pipeline_duration_seconds",
    "AI pipeline processing duration",
    ["step"],
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0),
)

PII_DETECTED = Counter(
    "desk_pii_detected_total",
    "Total PII detections",
    ["pii_type"],
)

LLM_REQUESTS = Counter(
    "desk_llm_requests_total",
    "Total LLM requests",
    ["provider", "model", "status"],
)

LLM_TOKENS_USED = Counter(
    "desk_llm_tokens_used_total",
    "Total LLM tokens used",
    ["provider", "model", "type"],
)

CONFIDENCE_SCORES = Histogram(
    "desk_confidence_scores",
    "AI confidence score distribution",
    buckets=(0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
)

ESCALATIONS = Counter(
    "desk_escalations_total",
    "Total escalations to human agents",
    ["reason"],
)

# Conversation metrics
ACTIVE_CONVERSATIONS = Gauge(
    "desk_active_conversations",
    "Number of active conversations",
    ["status", "channel"],
)

CONVERSATION_DURATION = Histogram(
    "desk_conversation_duration_seconds",
    "Conversation duration",
    buckets=(60, 300, 600, 1800, 3600, 7200, 14400, 28800),
)

# Agent metrics
ONLINE_AGENTS = Gauge(
    "desk_online_agents",
    "Number of online agents",
)

AGENT_WORKLOAD = Gauge(
    "desk_agent_workload",
    "Active conversations per agent",
    ["agent_id"],
)

# System metrics
DB_CONNECTION_POOL = Gauge(
    "desk_db_connection_pool",
    "Database connection pool status",
    ["state"],
)

REDIS_CONNECTIONS = Gauge(
    "desk_redis_connections",
    "Redis connection status",
    ["state"],
)

EVENT_BUS_MESSAGES = Counter(
    "desk_event_bus_messages_total",
    "Total event bus messages",
    ["stream", "action"],
)

# Compliance metrics
AUDIT_LOG_ENTRIES = Counter(
    "desk_audit_log_entries_total",
    "Total audit log entries",
    ["action", "actor_type"],
)

DATA_EXPORTS = Counter(
    "desk_data_exports_total",
    "Total data export requests",
)

DATA_DELETIONS = Counter(
    "desk_data_deletions_total",
    "Total data deletion requests",
)

# License metrics
LICENSE_STATUS = Gauge(
    "desk_license_status",
    "License validation status (1=valid, 0=invalid)",
)

FEATURE_GATES = Counter(
    "desk_feature_gate_checks_total",
    "Total feature gate checks",
    ["feature", "allowed"],
)
