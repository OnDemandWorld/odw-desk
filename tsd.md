# Technical Specification Document: ODW.ai Desk

**Product:** Desk — Self-Hosted, WhatsApp-First AI Customer Support Agent
**Version:** 1.2
**Date:** 2026-06-24
**Status:** Draft
**Input Documents:** PRD v1.2, SAD v1.2 (2026-06-24)

---

## 1. System Overview

### 1.1 Purpose

Desk is a self-hosted, WhatsApp-first AI customer support agent that provides regulated businesses full sovereignty over conversation data while delivering intelligent automated support grounded in the operator's own knowledge base (Vault). It is a module within the ODW.ai suite.

### 1.2 Architecture Mapping

| SAD Component | TSD Service/Module | Role |
|---|---|---|
| C1 Channel Gateway | `channel-gateway` | Inbound/outbound channel termination and normalization |
| C2 Message Router | `message-router` | Customer resolution, context loading, dispatch |
| C3 Conversation Manager | `conversation-manager` | State machine, message persistence, SLA enforcement |
| C4 AI Engine | `ai-engine` | RAG orchestration: PII → routing → retrieval → inference → confidence |
| C5 PII Shield | `pii-shield` | PII detection, redaction, routing directives |
| C6 Model Router | `model-router` | Model selection based on policy, PII, complexity |
| C7 Vault Client | `vault-client` | Knowledge base retrieval with caching |
| C8 Agent Inbox Service | `agent-inbox` | Human agent interface (REST + WebSocket) |
| C9 Admin Dashboard Service | `admin-dashboard` | Operator configuration, compliance, license |
| C10 Compliance Engine | `compliance-engine` | Retention, export, deletion, audit |
| C11 License Manager | `license-manager` | Feature gating, license validation |
| C12 Data Store | `data-store` | PostgreSQL + Redis + S3 |
| C13 Event Bus | `event-bus` | Redis Streams / NATS JetStream |
| C14 Suite Integration Layer | `suite-integration` | Auth (OIDC), Vault, Billing connectivity |
| C15 Channel Adapter Plugin System | `channel-adapter-plugin` | Generic adapter interface, lifecycle management, health checks |
| **C16 Persona Service** | `persona-service` | Brand Persona prompt composition, LoRA adapter selection |
| **C17 Policy Engine (Guardrails)** | `policy-engine` | Pre/post-generation policy hooks, rule enforcement |
| **C18 Intent/Policy Classifier** | `intent-classifier` | Intent detection for Policy Engine (rules + optional classifier) |

### 1.3 System Boundaries

**Included:**
- WhatsApp Business API connector (first-class, enterprise tier)
- WhatsApp Baileys Bridge connector (first-class, quick-start tier)
- Channel adapter plugin system for extensible channel support
- Web chat widget (second-class)
- Email channel (IMAP/SMTP, second-class)
- AI inference pipeline (local + frontier models)
- Vault knowledge base integration
- PII detection and redaction
- Human agent handoff
- Admin dashboard and agent inbox
- Compliance tooling (export, deletion, audit)
- License management (free/paid tiers)

**Excluded:**
- Multi-tenant SaaS hosting
- SMS, Instagram, LINE, WeChat (may be considered for v2)
- Visual flow builder
- Generative actions (execute transactions)
- CRM integrations
- Mobile admin app
- Custom model fine-tuning within Desk

**Future Optional Modules (v1.1+):**
- Telegram bot adapter
- Discord bot adapter
- Slack app adapter
- Signal messenger adapter
- iMessage bridge adapter

---

## 2. Service & Module Breakdown

### 2.1 Channel Gateway (`channel-gateway`)

**Responsibility:** Terminates inbound/outbound connections for all customer channels via pluggable channel adapters. Normalizes all inbound messages into a canonical `InboundMessage` format. Handles outbound delivery to channel-specific APIs.

**Inputs:**
- WhatsApp Business API webhooks (HTTPS POST)
- WhatsApp Baileys Bridge WebSocket messages (Node.js sidecar)
- Web chat WebSocket connections
- Email via IMAP polling + SMTP relay

**Outputs:**
- `InboundMessage` events published to event bus
- Outbound messages delivered to channel APIs

**Internal Sub-components:**
- `ChannelAdapterManager` — Plugin registry, lifecycle management, health monitoring
- `WhatsAppBusinessAdapter` — Meta/BSP webhook handling, template management, 24h window tracking
- `WhatsAppBaileysAdapter` — Baileys bridge integration, QR code pairing, session management, auto-reconnect
- `WebChatAdapter` — WebSocket server, session management, embed script serving
- `EmailAdapter` — IMAP fetch loop, SMTP send, MIME parsing
- `OutboundDispatcher` — Channel-specific formatting and delivery with retry
- Future adapters (v1.1+): `TelegramAdapter`, `DiscordAdapter`, `SlackAdapter`, `SignalAdapter`, `iMessageAdapter`

**Dependencies:**
- Event bus (Redis Streams) for publishing inbound / consuming outbound
- PostgreSQL (conversation state for WhatsApp 24h window checks, channel adapter config)
- Redis (session tokens for web chat, WhatsApp Baileys session state)
- Node.js Baileys sidecar (for WhatsApp Baileys Bridge)

**Deployment Unit:** Container `desk-api` (FastAPI application, all modules in modular monolith) + `desk-baileys-bridge` (Node.js sidecar container)

#### 2.1.5 Channel Adapter Plugin Interface Specification

All channel adapters implement the following abstract base class:

```python
from abc import ABC, abstractmethod
from typing import AsyncIterator, Literal
from pydantic import BaseModel

class ChannelAdapter(ABC):
    @abstractmethod
    async def connect(self, config: 'ChannelConfig') -> None:
        """Initialize connection to external channel"""
        pass
    
    @abstractmethod
    async def disconnect(self) -> None:
        """Gracefully close connection"""
        pass
    
    @abstractmethod
    async def receive(self) -> AsyncIterator['InboundMessage']:
        """Yield normalized inbound messages"""
        pass
    
    @abstractmethod
    async def send(self, message: 'OutboundMessage') -> 'DeliveryResult':
        """Deliver outbound message to channel"""
        pass
    
    @abstractmethod
    async def health_check(self) -> 'AdapterHealthStatus':
        """Return adapter health and connection status"""
        pass

# Channel configuration schema
class ChannelConfig(BaseModel):
    channel_type: Literal[
        "whatsapp_business", "whatsapp_baileys", "webchat", "email",
        "telegram", "discord", "slack", "signal", "imessage"
    ]
    enabled: bool = True
    credentials: dict  # Channel-specific credentials
    settings: dict     # Channel-specific settings
    reconnect_policy: 'ReconnectPolicy' = 'EXPONENTIAL_BACKOFF'

class ReconnectPolicy(BaseModel):
    type: Literal["none", "linear", "exponential_backoff"]
    max_attempts: int = 10
    base_delay_seconds: int = 1
    max_delay_seconds: int = 300

# WhatsApp Baileys-specific config
class WhatsAppBaileysConfig(ChannelConfig):
    channel_type: Literal["whatsapp_baileys"]
    credentials: dict = {}  # Session state stored in Redis
    settings: 'BaileysSettings'
    baileys_bridge_url: str  # Internal URL to Node.js sidecar

class BaileysSettings(BaseModel):
    auto_reconnect: bool = True
    max_reconnect_attempts: int = 10
    session_ttl_seconds: int = 2592000  # 30 days
    qr_code_timeout_seconds: int = 60

class AdapterHealthStatus(BaseModel):
    status: Literal["healthy", "degraded", "unhealthy"]
    connected: bool
    last_connected_at: str | None
    last_error: str | None
    messages_sent: int
    messages_received: int

class InboundMessage(BaseModel):
    channel: str
    channel_conversation_id: str
    sender_identifier: str
    content: str
    media_urls: list[str] = []
    metadata: dict = {}
    timestamp: str

class OutboundMessage(BaseModel):
    channel: str
    channel_conversation_id: str
    content: str
    media_urls: list[str] = []
    metadata: dict = {}

class DeliveryResult(BaseModel):
    success: bool
    message_id: str | None
    error: str | None
```

#### 2.1.6 WhatsApp Baileys Adapter API

**QR Code Pairing:**

```yaml
POST /api/v1/channels/whatsapp-baileys/pair
Request: {}
Response:
  200:
    qr_code_data_url: "data:image/png;base64,..."
    pairing_code: "ABCD-1234"  # Alternative to QR for phone-based pairing
    expires_in: 60
  400:
    error: "Adapter not configured"
  503:
    error: "Baileys bridge unavailable"
```

**Pairing Status:**

```yaml
GET /api/v1/channels/whatsapp-baileys/status
Response:
  200:
    connected: true
    phone_number: "+1234567890"
    last_seen: "2026-06-23T10:30:00Z"
    session_valid_until: "2026-07-23T10:30:00Z"
    messages_sent: 1234
    messages_received: 5678
  200:
    connected: false
    last_error: "Session expired"
    requires_repairing: true
```

**Force Reconnection:**

```yaml
POST /api/v1/channels/whatsapp-baileys/reconnect
Response:
  200:
    status: "reconnecting"
    attempt: 1
  503:
    error: "Max reconnect attempts exceeded"
```

#### 2.1.7 Channel Adapter Database Schema

```sql
-- Channel adapter instances
CREATE TABLE channel_adapters (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    channel_type VARCHAR(50) NOT NULL,  -- 'whatsapp_business', 'whatsapp_baileys', 'webchat', 'email', etc.
    adapter_name VARCHAR(100) NOT NULL UNIQUE,
    config JSONB NOT NULL,
    enabled BOOLEAN DEFAULT true,
    last_connected_at TIMESTAMP,
    last_error TEXT,
    messages_sent BIGINT DEFAULT 0,
    messages_received BIGINT DEFAULT 0,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);

CREATE INDEX idx_channel_adapters_type ON channel_adapters(channel_type);
CREATE INDEX idx_channel_adapters_enabled ON channel_adapters(enabled);

-- WhatsApp Baileys session state
CREATE TABLE whatsapp_baileys_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    adapter_id UUID REFERENCES channel_adapters(id) ON DELETE CASCADE,
    phone_number VARCHAR(20) NOT NULL UNIQUE,
    session_data JSONB,  -- Encrypted auth credentials
    pairing_code VARCHAR(20),
    qr_code_generated_at TIMESTAMP,
    paired_at TIMESTAMP,
    last_activity_at TIMESTAMP,
    session_expires_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);

CREATE INDEX idx_baileys_sessions_phone ON whatsapp_baileys_sessions(phone_number);
CREATE INDEX idx_baileys_sessions_expires ON whatsapp_baileys_sessions(session_expires_at);
```

---

### 2.2 Message Router (`message-router`)

**Responsibility:** Receives canonical inbound messages, resolves or creates customer profiles, loads conversation context, and dispatches to the appropriate processing pipeline.

**Inputs:**
- `InboundMessage` events from event bus

**Outputs:**
- `ProcessRequest` work items on processing queue

**Internal Sub-components:**
- `CustomerResolver` — Lookup by channel identifier (Redis cache → PostgreSQL fallback)
- `ContextLoader` — Load recent conversation history, customer metadata
- `PipelineDispatcher` — Route to AI pipeline or human agent queue based on conversation state

**Dependencies:**
- Event bus (consume inbound, produce processing requests)
- PostgreSQL (customer records, conversation state)
- Redis (customer lookup cache, conversation context cache)

**Deployment Unit:** Container `desk-api` (same process, event-driven consumer)

---

### 2.3 Conversation Manager (`conversation-manager`)

**Responsibility:** Maintains conversation state machine, persists messages, manages multi-turn context, enforces SLA timers.

**Inputs:**
- Routed work items from Message Router
- Agent actions (takeover, resolve, respond)
- AI responses from AI Engine

**Outputs:**
- State transition events on event bus
- Persisted messages in PostgreSQL
- SLA breach events

**Internal Sub-components:**
- `StateMachine` — Conversation states: `new → active → pending → escalated → resolved → closed`
- `MessageStore` — Append-only message persistence with deduplication
- `SLATimer` — First-response and resolution time tracking
- `ContextManager` — Maintains sliding window of recent messages for AI context

**State Transitions:**
```
new → active (first AI response or agent assignment)
active → pending (awaiting customer reply, 24h timeout)
active → escalated (AI confidence below threshold, or explicit escalation)
escalated → active (agent takes over)
active → resolved (agent or AI confirms resolution)
resolved → closed (retention period expires or manual close)
pending → active (customer replies within window)
pending → closed (24h window expires without reply)
```

**Dependencies:**
- PostgreSQL (conversations, messages, state)
- Redis (context cache, SLA timers)
- Event bus (state transition events)

**Deployment Unit:** Container `desk-api`

---

### 2.4 AI Engine (`ai-engine`)

**Responsibility:** Orchestrates the full RAG pipeline: PII detection → model routing → Vault retrieval → LLM inference → confidence scoring → response generation.

**Inputs:**
- `ProcessRequest` from processing queue

**Outputs:**
- AI response (text, metadata: model used, confidence score, routing decision)
- `OutboundMessage` events on event bus
- `AuditEvent` for AI decision logging

**Internal Sub-components:**
- `PipelineOrchestrator` — Coordinates PII Shield → Model Router → Vault Client → LLM call
- `PromptBuilder` — Constructs system prompt + conversation context + retrieved knowledge
- `ConfidenceScorer` — Calculates response confidence (0.0–1.0) based on model output
- `ResponseFormatter` — Formats AI output for channel-specific delivery (WhatsApp buttons, etc.)

**Processing Pipeline (per message):**
1. Receive `ProcessRequest`
2. Call PII Shield → get PII result + routing directive
3. Call Model Router → get target model + fallback chain
4. Call Vault Client → get relevant document chunks
5. Build prompt (system + context + knowledge + user message)
6. Execute LLM inference (with streaming if supported)
7. Calculate confidence score
8. If confidence ≥ threshold → format response → publish `OutboundMessage`
9. If confidence < threshold → escalate to human → publish escalation event
10. Log decision to audit trail

**Dependencies:**
- PII Shield (synchronous call)
- Model Router (synchronous call)
- Vault Client (synchronous HTTP, cached)
- Ollama/vLLM (local model inference)
- OpenAI/Anthropic API (frontier model inference)
- Event bus (publish outbound messages, audit events)

**Deployment Unit:** Container `desk-worker-ai` (separate for independent scaling)

---

### 2.5 PII Shield (`pii-shield`)

**Responsibility:** Detects personally identifiable information in messages. Generates redacted versions. Issues routing directives (local-only vs. frontier-allowed).

**Inputs:**
- Raw message text

**Outputs:**
- `{pii_detected: bool, pii_types: list[str], redacted_text: str, routing_directive: str}`

**Internal Sub-components:**
- `PIIDetector` — NER-based detection using Presidio + custom patterns
- `PIIRedactor` — Replaces PII with placeholders (e.g., `[PHONE_NUMBER]`, `[NAME]`)
- `RoutingPolicy` — Determines if PII presence forces local-only model

**PII Types Detected:**
- Names, phone numbers, email addresses
- Physical addresses, dates of birth
- Health identifiers (patient IDs, diagnosis codes)
- Financial account numbers, credit card numbers
- Government IDs (SSN, passport, national ID)

**Routing Directives:**
- `LOCAL_MODEL_ONLY` — PII detected, must not leave infrastructure
- `REDACTED_FRONTIER_OK` — Admin allows frontier with redaction
- `NO_RESTRICTION` — No PII detected, follow complexity-based routing

**Dependencies:**
- Presidio library (NER models)
- Configuration store (custom PII patterns, routing policy)

**Deployment Unit:** In-process within `desk-worker-ai` (synchronous call)

---

### 2.6 Model Router (`model-router`)

**Responsibility:** Selects inference target (local vs. frontier) based on routing policy, PII detection result, and complexity scoring. Implements fallback logic.

**Inputs:**
- `{pii_directive: str, complexity_score: float, conversation_context: dict}`

**Outputs:**
- `{model_endpoint: str, model_name: str, fallback_chain: list[str]}`

**Internal Sub-components:**
- `ComplexityScorer` — Heuristic scoring based on message length, question type, context depth
- `PolicyEvaluator` — Applies routing rules (PII directive + admin policy)
- `FallbackManager` — Circuit breaker integration, fallback chain resolution

**Routing Logic:**
```
IF pii_directive == LOCAL_MODEL_ONLY:
    target = local_model
    fallback = [escalate_to_human]  # NO frontier fallback
ELIF pii_directive == REDACTED_FRONTIER_OK:
    target = frontier_model (with redacted text)
    fallback = [local_model, escalate_to_human]
ELIF complexity_score > threshold:
    target = frontier_model
    fallback = [local_model, escalate_to_human]
ELSE:
    target = local_model
    fallback = [frontier_model, escalate_to_human]
```

**Dependencies:**
- Configuration store (routing policies, model endpoints)
- Circuit breaker state (per model endpoint)

**Deployment Unit:** In-process within `desk-worker-ai`

---

### 2.7 Vault Client (`vault-client`)

**Responsibility:** Queries ODW.ai Vault's retrieval API for relevant knowledge base documents. Caches results in Redis.

**Inputs:**
- `{query: str, collection_id: str, top_k: int}`

**Outputs:**
- `{documents: list[{content: str, score: float, source_id: str, metadata: dict}]}`

**Internal Sub-components:**
- `VaultAPIClient` — HTTP client for Vault retrieval endpoint
- `CacheManager` — Redis-backed cache with TTL
- `ResultRanker` — Re-ranks results by relevance score, filters low-confidence chunks

**Cache Strategy:**
- Key: `vault:{collection_id}:{query_hash}`
- TTL: 10 minutes
- Hit rate target: >40% (common questions repeat)

**Dependencies:**
- Vault API (REST, HTTPS)
- Redis (cache)
- ODW.ai Auth (token for Vault API authentication)

**Deployment Unit:** In-process within `desk-worker-ai`

---

### 2.8 Agent Inbox Service (`agent-inbox`)

**Responsibility:** Serves the human-agent interface: conversation list, message history, response composition, takeover/handoff actions. Real-time updates via WebSocket.

**Inputs:**
- Agent HTTP requests (REST API)
- Agent WebSocket connections (real-time)

**Outputs:**
- Conversation data (list, detail, history)
- Real-time event stream (new messages, state changes)

**Internal Sub-components:**
- `InboxAPI` — REST endpoints for conversation CRUD, agent actions
- `WebSocketManager` — Manages persistent connections, broadcasts events
- `AgentSessionManager` — Tracks online agents, assignment state

**Key Operations:**
- List conversations (filtered by status, assignment, channel)
- View conversation detail + full message history
- Take over conversation (escalated → active, agent-assigned)
- Send response (as human agent)
- Resolve conversation
- Provide AI feedback (thumbs up/down on AI responses)

**Dependencies:**
- PostgreSQL (conversation data, read queries)
- Event bus (subscribe to conversation events for real-time updates)
- Redis (WebSocket pub/sub for multi-node broadcast)

**Deployment Unit:** Container `desk-api` (shares process with other modules)

---

### 2.9 Admin Dashboard Service (`admin-dashboard`)

**Responsibility:** Serves operator/admin interface: setup wizard, AI configuration, compliance reports, audit logs, license management.

**Inputs:**
- Admin HTTP requests (REST API)

**Outputs:**
- Configuration data, reports, audit exports

**Internal Sub-components:**
- `SetupWizardAPI` — Guided initial configuration (Vault, model, WhatsApp)
- `ConfigAPI` — AI model configuration, routing policies, PII settings
- `ComplianceAPI` — Data export, deletion requests, compliance reports
- `LicenseAPI` — License status, feature gate display

**Dependencies:**
- PostgreSQL (configuration, audit logs)
- License Manager (feature gate checks)
- ODW.ai Auth (admin role verification)

**Deployment Unit:** Container `desk-api` (REST API) + Container `desk-web` (React frontend)

---

### 2.10 Compliance Engine (`compliance-engine`)

**Responsibility:** Enforces data retention policies, generates compliance reports, handles data export/deletion requests (GDPR right-to-erasure), maintains tamper-evident audit log.

**Inputs:**
- Admin commands (export, delete, report generation)
- Scheduled jobs (retention enforcement)
- Audit events from all modules

**Outputs:**
- Export files (JSON/CSV)
- Deletion confirmations
- Compliance reports (PDF/JSON)

**Internal Sub-components:**
- `RetentionManager` — Enforces data retention policies (age-based deletion)
- `ExportService` — Generates per-customer data exports (GDPR Article 20)
- `DeletionService` — Handles right-to-erasure requests (GDPR Article 17)
- `AuditLogWriter` — Append-only, tamper-evident audit log (hash-chained)
- `ReportGenerator` — Compliance summary reports

**Dependencies:**
- PostgreSQL (audit logs, deletion records)
- S3-compatible storage (export files, backup archives)
- Event bus (consume audit events)

**Deployment Unit:** Container `desk-scheduler` (scheduled jobs) + `desk-api` (API endpoints)

---

### 2.11 License Manager (`license-manager`)

**Responsibility:** Validates license keys (online and offline), enforces feature gates between free and paid tiers, manages grace periods.

**Inputs:**
- Startup hook (validate license on boot)
- Periodic check (re-validate every 24h)
- Admin commands (activate, deactivate)

**Outputs:**
- Feature gate decisions (boolean: feature allowed/denied)
- License status (active, expired, grace period, invalid)

**Feature Gates (Free vs Paid):**

| Feature | Free | Paid |
|---|---|---|
| Web chat channel | ✓ | ✓ |
| Email channel | ✓ | ✓ |
| WhatsApp Business connector | ✗ | ✓ |
| Single AI agent | ✓ | ✓ |
| Multi-agent routing | ✗ | ✓ |
| Basic Vault integration | ✓ | ✓ |
| Advanced compliance (audit exports, retention policies) | ✗ | ✓ |
| SLA-backed support | ✗ | ✓ |

**Dependencies:**
- ODW.ai Billing API (online validation)
- PostgreSQL (license state cache)
- Environment variables (offline license key)

**Deployment Unit:** In-process within `desk-api`

---

### 2.12 Data Store (`data-store`)

**Responsibility:** Primary persistence layer for all Desk data.

**Components:**
- **PostgreSQL 16+** — Conversations, messages, customers, agents, configuration, audit logs
- **Redis 7+** — Cache (customer lookup, Vault results, context), message queues (Redis Streams)
- **S3-compatible (MinIO)** — Media files, backup archives, export files

**Ownership:**
- Conversation Manager owns: `conversations`, `messages`, `conversation_state`
- Message Router owns: `customers`, `channel_identifiers`
- AI Engine owns: `ai_configurations`, `ai_decision_logs`
- Compliance Engine owns: `audit_logs`, `data_deletion_records`, `compliance_reports`
- License Manager owns: `license_state`, `feature_gates`

---

### 2.13 Event Bus (`event-bus`)

**Responsibility:** Internal asynchronous messaging backbone. Carries inbound messages, AI responses, state transitions, and audit events between components.

**Technology:**
- **Default:** Redis Streams (Docker Compose deployments)
- **Kubernetes:** NATS JetStream (better persistence, clustering)

**Event Types:**
- `inbound.message` — New customer message received
- `outbound.message` — AI/agent response ready for delivery
- `conversation.state_changed` — Conversation state transition
- `conversation.agent_assigned` — Human agent took over
- `ai.decision` — AI inference result logged
- `audit.event` — Audit trail entry
- `sla.breach` — SLA timer expired

**Guarantees:**
- At-least-once delivery (idempotent consumers required)
- Per-conversation ordering (partition key: `conversation_id`)
- Dead-letter queue for failed processing

---

### 2.14 Suite Integration Layer (`suite-integration`)

**Responsibility:** Manages connectivity to ODW.ai Auth (SSO/OIDC), Vault (knowledge retrieval), Billing (license validation), and unified admin dashboard.

**Dependencies:**
- ODW.ai Auth (OIDC provider)
- ODW.ai Vault (REST API)
- ODW.ai Billing (REST API)

**Interfaces:**
- `AuthClient` — OIDC token validation, user info retrieval
- `VaultClient` — Knowledge base queries (shared with AI Engine)
- `BillingClient` — License validation, feature entitlement checks

---

## 3. Technical Stack Specification

### 3.1 Backend

| Layer | Technology | Version | Justification |
|---|---|---|---|
| Language | Python | 3.11+ | Team expertise; rich AI/ML ecosystem; async support |
| Web Framework | FastAPI | 0.110+ | Async-native, OpenAPI auto-generation, high performance |
| ORM | SQLAlchemy | 2.0+ | Mature, async support, migration integration |
| Migrations | Alembic | 1.13+ | Standard SQLAlchemy migration tool |
| Task Queue | Redis Streams (built-in) | Redis 7+ | Already required for caching; no additional infrastructure |
| HTTP Client | httpx | 0.27+ | Async-native, HTTP/2 support |
| Validation | Pydantic | 2.6+ | FastAPI integration, strict typing |
| Logging | structlog | 24.1+ | Structured JSON logging, context propagation |
| Testing | pytest + pytest-asyncio | 8.0+ | Industry standard, async test support |

### 3.2 Frontend

| Layer | Technology | Version | Justification |
|---|---|---|---|
| Framework | React | 18.2+ | Team expertise; component ecosystem |
| Language | TypeScript | 5.3+ | Type safety, better IDE support |
| Build Tool | Vite | 5.0+ | Fast HMR, modern bundling |
| UI Library | shadcn/ui + Tailwind CSS | Latest | Accessible components, utility-first styling |
| State Management | Zustand | 4.5+ | Lightweight, TypeScript-friendly |
| WebSocket | Native WebSocket + reconnecting-websocket | — | Real-time agent inbox updates |
| HTTP Client | TanStack Query (React Query) | 5.0+ | Caching, refetching, optimistic updates |

### 3.3 AI/ML Stack

| Component | Technology | Version | Justification |
|---|---|---|---|
| LLM Orchestration | LangChain | 0.1+ | Prompt templates, chain composition, model abstraction |
| Local Model Runtime | Ollama | 0.1.26+ | Easy local model management; REST API |
| Alternative Local Runtime | vLLM | 0.4+ | Higher throughput for GPU-equipped deployments |
| Frontier Models | OpenAI GPT-4o / GPT-4o-mini | Latest | Quality fallback for complex queries |
| Frontier Models | Anthropic Claude 3.5 Sonnet | Latest | Alternative frontier provider |
| PII Detection | Microsoft Presidio | 2.2+ | NER-based PII detection; extensible |
| Embeddings | Vault-managed | — | Desk does not own embedding pipeline |

### 3.4 Data Layer

| Component | Technology | Version | Purpose |
|---|---|---|---|
| Primary Database | PostgreSQL | 16+ | ACID transactions, JSONB flexibility, audit integrity |
| Cache + Queue | Redis | 7+ | Sub-ms cache reads; Redis Streams for event bus |
| Object Storage | MinIO (self-hosted) | Latest | S3-compatible; media files, backups, exports |
| Connection Pool | PgBouncer | 1.21+ | PostgreSQL connection pooling |
| Vector Search | pgvector (via Vault) | 0.6+ | Managed by Vault; Desk queries via API |

### 3.5 DevOps Tooling

| Component | Technology | Purpose |
|---|---|---|
| Containerization | Docker + Docker Compose | Single-node deployment |
| Orchestration | Kubernetes + Helm | Clustered deployment |
| Reverse Proxy | Traefik | TLS termination, routing |
| CI/CD | GitHub Actions | Lint, test, build, deploy |
| Container Registry | GHCR (GitHub Container Registry) | Image storage |
| Infrastructure as Code | Helm charts + docker-compose.yml | Reproducible deployments |
| Secret Management | Environment variables (Compose) / HashiCorp Vault or AWS Secrets Manager (K8s) | Credential storage |

---

## 4. Data Modeling & Schema Definitions

### 4.1 Entity: `customers`

**Table Name:** `customers`
**Owned By:** Message Router

| Field | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PRIMARY KEY, DEFAULT gen_random_uuid() | Unique customer identifier |
| `display_name` | VARCHAR(255) | NULLABLE | Customer display name |
| `channel_identifiers` | JSONB | NOT NULL, DEFAULT '{}' | Map of channel → identifier (e.g., `{"whatsapp": "+1234567890"}`) |
| `metadata` | JSONB | NULLABLE, DEFAULT '{}' | Custom metadata (tags, notes) |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | Creation timestamp |
| `updated_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | Last update timestamp |

**Indexes:**
- `idx_customers_channel_identifiers` — GIN index on `channel_identifiers` (JSONB)
- `idx_customers_created_at` — B-tree on `created_at`

**Relationships:**
- One-to-Many: `customers` → `conversations`

**Example Record:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "display_name": "Carlos Mendez",
  "channel_identifiers": {
    "whatsapp": "+5511999887766",
    "webchat": "session_abc123"
  },
  "metadata": {"vip": true, "language": "pt-BR"},
  "created_at": "2026-06-23T10:00:00Z",
  "updated_at": "2026-06-23T10:00:00Z"
}
```

---

### 4.2 Entity: `conversations`

**Table Name:** `conversations`
**Owned By:** Conversation Manager

| Field | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PRIMARY KEY, DEFAULT gen_random_uuid() | Unique conversation identifier |
| `customer_id` | UUID | NOT NULL, FK → customers.id | Customer reference |
| `channel` | VARCHAR(50) | NOT NULL | Channel type: `whatsapp`, `webchat`, `email` |
| `channel_conversation_id` | VARCHAR(255) | NOT NULL | Channel-specific conversation/thread ID |
| `status` | VARCHAR(30) | NOT NULL, DEFAULT 'new' | State: new, active, pending, escalated, resolved, closed |
| `assigned_agent_id` | UUID | NULLABLE, FK → agents.id | Human agent (if escalated) |
| `ai_enabled` | BOOLEAN | NOT NULL, DEFAULT true | Whether AI auto-responds |
| `confidence_threshold` | FLOAT | NOT NULL, DEFAULT 0.7 | Minimum confidence for AI response |
| `sla_first_response_due` | TIMESTAMPTZ | NULLABLE | SLA deadline for first response |
| `sla_resolution_due` | TIMESTAMPTZ | NULLABLE | SLA deadline for resolution |
| `metadata` | JSONB | NULLABLE, DEFAULT '{}' | Channel-specific metadata |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | Creation timestamp |
| `updated_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | Last update timestamp |

**Indexes:**
- `idx_conversations_customer_status` — Composite on `(customer_id, status, updated_at)`
- `idx_conversations_channel_conversation_id` — Unique on `(channel, channel_conversation_id)` for dedup
- `idx_conversations_assigned_agent` — On `assigned_agent_id` WHERE `assigned_agent_id IS NOT NULL`
- `idx_conversations_status` — On `status` for inbox filtering

**Relationships:**
- Many-to-One: `conversations` → `customers`
- One-to-Many: `conversations` → `messages`
- Many-to-One: `conversations` → `agents` (optional)

**Example Record:**
```json
{
  "id": "660e8400-e29b-41d4-a716-446655440001",
  "customer_id": "550e8400-e29b-41d4-a716-446655440000",
  "channel": "whatsapp",
  "channel_conversation_id": "wa_thread_12345",
  "status": "active",
  "assigned_agent_id": null,
  "ai_enabled": true,
  "confidence_threshold": 0.7,
  "sla_first_response_due": "2026-06-23T10:05:00Z",
  "sla_resolution_due": "2026-06-24T10:00:00Z",
  "metadata": {"whatsapp_session_expires": "2026-06-23T12:00:00Z"},
  "created_at": "2026-06-23T10:00:00Z",
  "updated_at": "2026-06-23T10:01:00Z"
}
```

---

### 4.3 Entity: `messages`

**Table Name:** `messages`
**Owned By:** Conversation Manager

| Field | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PRIMARY KEY, DEFAULT gen_random_uuid() | Unique message identifier |
| `conversation_id` | UUID | NOT NULL, FK → conversations.id | Conversation reference |
| `sender_type` | VARCHAR(20) | NOT NULL | `customer`, `ai`, `agent`, `system` |
| `sender_id` | VARCHAR(255) | NULLABLE | Agent ID or "ai" or customer channel ID |
| `content` | TEXT | NOT NULL | Message text (may be encrypted for PII) |
| `content_redacted` | TEXT | NULLABLE | Redacted version (if PII detected) |
| `media_urls` | JSONB | NULLABLE, DEFAULT '[]' | Array of media file URLs |
| `metadata` | JSONB | NULLABLE, DEFAULT '{}' | AI metadata: model, confidence, routing decision |
| `pii_detected` | BOOLEAN | NOT NULL, DEFAULT false | Whether PII was detected |
| `pii_types` | JSONB | NULLABLE | Array of PII types found |
| `channel_message_id` | VARCHAR(255) | NULLABLE | Channel-specific message ID (for dedup) |
| `persona_id` | UUID | NULLABLE, FK → brand_personas.id | Brand Persona used for this message (if AI-generated) |
| `persona_backend_used` | VARCHAR(20) | NULLABLE | `'prompt'` or `'lora_adapter'` — which persona backend generated this |
| `policy_triggers` | JSONB | NULLABLE, DEFAULT '[]' | Array of policy decisions: `[{policy_id, action, matched_on, timestamp}]` |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | Message timestamp |

**Indexes:**
- `idx_messages_conversation_created` — Composite on `(conversation_id, created_at)`
- `idx_messages_sender_type` — Partial index on `sender_type` WHERE `sender_type = 'ai'`
- `idx_messages_channel_message_id` — Unique on `(conversation_id, channel_message_id)` WHERE NOT NULL
- `idx_messages_persona_id` — Partial index on `persona_id` WHERE `persona_id IS NOT NULL`
- `idx_messages_policy_triggers` — GIN index on `policy_triggers` (JSONB) for policy analytics

**Relationships:**
- Many-to-One: `messages` → `conversations`
- Many-to-One: `messages` → `brand_personas` (optional)

**Example Record:**
```json
{
  "id": "770e8400-e29b-41d4-a716-446655440002",
  "conversation_id": "660e8400-e29b-41d4-a716-446655440001",
  "sender_type": "ai",
  "sender_id": "ai",
  "content": "Hi Carlos! I can help you reschedule. What day next week works best?",
  "content_redacted": null,
  "media_urls": [],
  "metadata": {
    "model": "llama-3.1-8b",
    "confidence": 0.89,
    "routing": "local",
    "vault_sources": ["kb-appointment-policy"]
  },
  "pii_detected": false,
  "pii_types": null,
  "channel_message_id": "wamid.abc123",
  "persona_id": "880e8400-e29b-41d4-a716-446655440010",
  "persona_backend_used": "prompt",
  "policy_triggers": [],
  "created_at": "2026-06-23T10:01:30Z"
}
```

---

### 4.4 Entity: `agents`

**Table Name:** `agents`
**Owned By:** Agent Inbox Service

| Field | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PRIMARY KEY, DEFAULT gen_random_uuid() | Unique agent identifier |
| `user_id` | UUID | NOT NULL, FK → auth.users | ODW.ai Auth user reference |
| `display_name` | VARCHAR(255) | NOT NULL | Agent display name |
| `email` | VARCHAR(255) | NOT NULL, UNIQUE | Agent email |
| `role` | VARCHAR(30) | NOT NULL, DEFAULT 'agent' | `admin`, `agent`, `read_only` |
| `is_online` | BOOLEAN | NOT NULL, DEFAULT false | Current online status |
| `max_concurrent_conversations` | INT | NOT NULL, DEFAULT 5 | Capacity limit |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | Creation timestamp |

**Indexes:**
- `idx_agents_user_id` — On `user_id`
- `idx_agents_online` — On `is_online` WHERE `is_online = true`

---

### 4.5 Entity: `ai_configurations`

**Table Name:** `ai_configurations`
**Owned By:** AI Engine

| Field | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PRIMARY KEY, DEFAULT gen_random_uuid() | Configuration identifier |
| `deployment_id` | UUID | NOT NULL, UNIQUE | One config per deployment |
| `local_model_endpoint` | VARCHAR(500) | NULLABLE | Ollama/vLLM endpoint URL |
| `local_model_name` | VARCHAR(100) | NULLABLE | Model identifier (e.g., `llama-3.1-8b`) |
| `frontier_provider` | VARCHAR(50) | NULLABLE | `openai`, `anthropic` |
| `frontier_model_name` | VARCHAR(100) | NULLABLE | e.g., `gpt-4o`, `claude-3.5-sonnet` |
| `frontier_api_key_encrypted` | BYTEA | NULLABLE | Encrypted API key |
| `routing_policy` | JSONB | NOT NULL | Routing rules (complexity threshold, PII policy) |
| `system_prompt` | TEXT | NOT NULL | Base system prompt for AI |
| `confidence_threshold` | FLOAT | NOT NULL, DEFAULT 0.7 | Global default confidence threshold |
| `vault_collection_id` | UUID | NULLABLE | Default Vault collection for retrieval |
| `pii_shield_enabled` | BOOLEAN | NOT NULL, DEFAULT true | Enable PII detection |
| `pii_frontier_allowed_with_redaction` | BOOLEAN | NOT NULL, DEFAULT false | Allow frontier if PII redacted |
| `active_persona_id` | UUID | NULLABLE, FK → brand_personas.id | Currently active Brand Persona (prompt-based or LoRA) |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | Creation timestamp |
| `updated_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | Last update timestamp |

**Indexes:**
- `idx_ai_configurations_deployment` — Unique on `deployment_id`
- `idx_ai_configurations_active_persona` — Partial index on `active_persona_id` WHERE `active_persona_id IS NOT NULL`

---

### 4.6 Entity: `audit_logs`

**Table Name:** `audit_logs`
**Owned By:** Compliance Engine

| Field | Type | Constraints | Description |
|---|---|---|---|
| `id` | BIGSERIAL | PRIMARY KEY | Auto-incrementing ID |
| `timestamp` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | Event timestamp |
| `event_type` | VARCHAR(100) | NOT NULL | Event category |
| `actor_type` | VARCHAR(30) | NOT NULL | `agent`, `ai`, `system`, `admin` |
| `actor_id` | VARCHAR(255) | NULLABLE | Actor identifier |
| `resource_type` | VARCHAR(50) | NOT NULL | `conversation`, `message`, `customer`, `config` |
| `resource_id` | UUID | NULLABLE | Resource identifier |
| `action` | VARCHAR(50) | NOT NULL | `create`, `update`, `delete`, `access`, `escalate` |
| `details` | JSONB | NULLABLE | Event-specific details |
| `previous_hash` | VARCHAR(64) | NULLABLE | SHA-256 hash of previous record (chain integrity) |
| `hash` | VARCHAR(64) | NOT NULL | SHA-256 hash of this record |

**Indexes:**
- `idx_audit_logs_timestamp_event` — Composite on `(timestamp, event_type)`
- `idx_audit_logs_resource` — Composite on `(resource_type, resource_id)`

**Tamper-Evidence:** Each record's hash includes `previous_hash`, creating a hash chain. Any modification breaks the chain.

---

### 4.7 Entity: `license_state`

**Table Name:** `license_state`
**Owned By:** License Manager

| Field | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PRIMARY KEY, DEFAULT gen_random_uuid() | Record ID |
| `license_key` | VARCHAR(500) | NOT NULL | License key (encrypted at rest) |
| `tier` | VARCHAR(30) | NOT NULL | `free`, `paid` |
| `status` | VARCHAR(30) | NOT NULL | `active`, `expired`, `grace_period`, `invalid` |
| `valid_until` | TIMESTAMPTZ | NULLABLE | License expiry date |
| `grace_period_ends` | TIMESTAMPTZ | NULLABLE | Grace period expiry |
| `features` | JSONB | NOT NULL | Enabled features map |
| `last_validated_at` | TIMESTAMPTZ | NOT NULL | Last successful validation |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | Creation timestamp |

---

### 4.8 Entity: `brand_personas`

**Table Name:** `brand_personas`
**Owned By:** Persona Service

| Field | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PRIMARY KEY, DEFAULT gen_random_uuid() | Unique persona identifier |
| `deployment_id` | UUID | NOT NULL | Deployment reference |
| `name` | VARCHAR(255) | NOT NULL | Persona name (e.g., "Friendly Restaurant", "Formal Law Firm") |
| `tone` | VARCHAR(100) | NOT NULL | Tone descriptor (e.g., "warm", "formal", "playful", "professional") |
| `formality_level` | VARCHAR(30) | NOT NULL, DEFAULT 'neutral' | `casual`, `neutral`, `formal` |
| `vocabulary_notes` | TEXT | NULLABLE | Custom vocabulary guidance (e.g., "use 'guests' not 'customers'", "avoid technical jargon") |
| `dos` | JSONB | NOT NULL, DEFAULT '[]' | Array of "do" guidelines (e.g., ["be empathetic", "use first names"]) |
| `donts` | JSONB | NOT NULL, DEFAULT '[]' | Array of "don't" guidelines (e.g., ["never mention competitors", "avoid legal advice"]) |
| `emoji_policy` | VARCHAR(30) | NOT NULL, DEFAULT 'moderate' | `none`, `minimal`, `moderate`, `liberal` |
| `signature_phrases` | JSONB | NULLABLE, DEFAULT '[]' | Array of signature phrases (e.g., ["How can I help you today?", "We appreciate your business"]) |
| `few_shot_examples` | JSONB | NULLABLE, DEFAULT '[]' | Array of example conversations: `[{user: "...", assistant: "..."}]` for few-shot learning |
| `channel_overrides` | JSONB | NULLABLE, DEFAULT '{}' | Per-channel persona overrides (e.g., `{"whatsapp": {"emoji_policy": "liberal"}, "email": {"formality_level": "formal"}}`) |
| `persona_backend` | VARCHAR(30) | NOT NULL, DEFAULT 'prompt' | `'prompt'` or `'lora_adapter'` |
| `adapter_uri` | VARCHAR(500) | NULLABLE | LoRA/QLoRA adapter URI (local path or S3 URI) when `persona_backend = 'lora_adapter'` |
| `adapter_base_model` | VARCHAR(100) | NULLABLE | Expected base model for adapter (validated on load) |
| `adapter_version` | VARCHAR(50) | NULLABLE | Adapter version identifier for audit trail |
| `version` | INT | NOT NULL, DEFAULT 1 | Persona config version (incremented on updates) |
| `is_active` | BOOLEAN | NOT NULL, DEFAULT true | Whether this persona is currently active (referenced by `ai_configurations.active_persona_id`) |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | Creation timestamp |
| `updated_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | Last update timestamp |

**Indexes:**
- `idx_brand_personas_deployment_active` — Composite on `(deployment_id, is_active)` WHERE `is_active = true`
- `idx_brand_personas_name` — On `name` for lookup
- `idx_brand_personas_backend` — On `persona_backend` for analytics

**Relationships:**
- Many-to-One: `brand_personas` → `ai_configurations` (via `active_persona_id`)
- One-to-Many: `brand_personas` → `messages` (via `persona_id`)

**Example Record:**
```json
{
  "id": "880e8400-e29b-41d4-a716-446655440010",
  "deployment_id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "Friendly Restaurant",
  "tone": "warm",
  "formality_level": "casual",
  "vocabulary_notes": "Use 'guests' instead of 'customers'. Refer to meals as 'dishes'. Always sound welcoming.",
  "dos": ["be empathetic", "use first names when available", "offer alternatives if unavailable"],
  "donts": ["never mention competitors", "avoid negative language", "don't make promises about wait times"],
  "emoji_policy": "moderate",
  "signature_phrases": ["Welcome! How can we help you today? 😊", "We'd love to see you again!"],
  "few_shot_examples": [
    {
      "user": "Do you have vegan options?",
      "assistant": "Absolutely! We have several delicious vegan dishes. Would you like me to share our vegan menu with you?"
    }
  ],
  "channel_overrides": {
    "whatsapp": {"emoji_policy": "liberal"},
    "email": {"formality_level": "neutral"}
  },
  "persona_backend": "prompt",
  "adapter_uri": null,
  "adapter_base_model": null,
  "adapter_version": null,
  "version": 1,
  "is_active": true,
  "created_at": "2026-06-23T10:00:00Z",
  "updated_at": "2026-06-23T10:00:00Z"
}
```

---

### 4.9 Entity: `response_policies`

**Table Name:** `response_policies`
**Owned By:** Policy Engine

| Field | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PRIMARY KEY, DEFAULT gen_random_uuid() | Unique policy identifier |
| `deployment_id` | UUID | NOT NULL | Deployment reference |
| `name` | VARCHAR(255) | NOT NULL | Policy name (e.g., "Competitor Redirect", "Medical Disclaimer") |
| `description` | TEXT | NULLABLE | Human-readable description of the policy |
| `trigger_type` | VARCHAR(30) | NOT NULL | `'keyword'`, `'classifier'`, `'llm_intent'` |
| `trigger_config` | JSONB | NOT NULL | Trigger configuration (e.g., `{"keywords": ["competitor-x", "competitor-y"], "case_sensitive": false}` or `{"intent_label": "competitor_mention", "threshold": 0.8}`) |
| `action` | VARCHAR(50) | NOT NULL | `'template'`, `'redirect'`, `'inject_context'`, `'append_disclaimer'`, `'block'`, `'escalate'` |
| `action_payload` | JSONB | NOT NULL | Action-specific payload (e.g., `{"template_text": "We prefer to focus on our own services..."}` or `{"disclaimer": "This is not medical advice..."}` or `{"vault_doc_id": "kb-competitor-policy"}`) |
| `applies_to` | VARCHAR(20) | NOT NULL, DEFAULT 'pre' | `'pre'` (pre-generation), `'post'` (post-generation), `'both'` |
| `priority` | INT | NOT NULL, DEFAULT 100 | Evaluation order (lower number = higher priority; first hard-match wins for pre-hook) |
| `restricted_topics` | JSONB | NULLABLE, DEFAULT '[]' | Array of restricted topic labels (when action is to block general-knowledge fallback) |
| `allow_general_knowledge_fallback` | BOOLEAN | NOT NULL, DEFAULT true | Whether to allow LLM general knowledge when no Vault doc found (supersedes US-AI-01(c)) |
| `is_active` | BOOLEAN | NOT NULL, DEFAULT true | Whether this policy is currently active |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | Creation timestamp |
| `updated_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | Last update timestamp |

**Indexes:**
- `idx_response_policies_deployment_active` — Composite on `(deployment_id, is_active, priority)` WHERE `is_active = true`
- `idx_response_policies_trigger_type` — On `trigger_type` for filtering
- `idx_response_policies_applies_to` — On `applies_to` for pre/post-hook evaluation

**Relationships:**
- Referenced by: `messages.policy_triggers` (JSONB array of policy decisions)

**Example Record:**
```json
{
  "id": "990e8400-e29b-41d4-a716-446655440020",
  "deployment_id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "Competitor Redirect",
  "description": "Redirect competitor mentions to our value proposition instead of providing factual competitor info",
  "trigger_type": "keyword",
  "trigger_config": {
    "keywords": ["competitor-x", "competitor-y", "competitor-z"],
    "case_sensitive": false,
    "match_mode": "substring"
  },
  "action": "template",
  "action_payload": {
    "template_text": "We prefer to focus on how we can help you! Our services include [list key services]. Would you like to learn more about what we offer?"
  },
  "applies_to": "pre",
  "priority": 10,
  "restricted_topics": ["competitor_info"],
  "allow_general_knowledge_fallback": false,
  "is_active": true,
  "created_at": "2026-06-23T10:00:00Z",
  "updated_at": "2026-06-23T10:00:00Z"
}
```

---

### 4.10 Migration Strategy

- **Tool:** Alembic (auto-generates migrations from SQLAlchemy model changes)
- **Execution:** Migrations run automatically on `desk-api` startup (before serving traffic)
- **Policy:** Backward-compatible migrations only (no breaking changes to running instances)
- **Rollback:** Each migration includes a `downgrade()` function; rollback supported but not automatic
- **Versioning:** Migration files versioned in git; applied migrations tracked in `alembic_version` table

---

## 5. API Contracts (Strict Specification)

### 5.1 External Webhook APIs

#### 5.1.1 WhatsApp Webhook Receiver

- **Service:** Channel Gateway
- **Path:** `POST /api/v1/webhooks/whatsapp`
- **Authentication:** HMAC-SHA256 signature verification (Meta-provided secret in `X-Hub-Signature-256` header)

**Request:**
```
Headers:
  Content-Type: application/json
  X-Hub-Signature-256: sha256=<hmac_hex>

Body (Meta WhatsApp Cloud API format):
{
  "object": "whatsapp_business_account",
  "entry": [{
    "id": "BA_ID",
    "changes": [{
      "value": {
        "messaging_product": "whatsapp",
        "metadata": {"display_phone_number": "+1234567890", "phone_number_id": "PNID"},
        "messages": [{
          "from": "+5511999887766",
          "id": "wamid.abc123",
          "timestamp": "1719136800",
          "type": "text",
          "text": {"body": "Hi, I need to reschedule my appointment"}
        }]
      },
      "field": "messages"
    }]
  }]
}
```

**Response:**
```
Success (200 OK):
{
  "status": "received",
  "message_count": 1
}

Error (400 Bad Request):
{
  "error": {
    "code": "INVALID_SIGNATURE",
    "message": "Webhook signature verification failed"
  }
}

Error (401 Unauthorized):
{
  "error": {
    "code": "UNAUTHORIZED",
    "message": "Invalid or missing signature"
  }
}
```

#### 5.1.2 WhatsApp Webhook Verification (GET)

- **Path:** `GET /api/v1/webhooks/whatsapp`
- **Authentication:** Meta verification token

**Request:**
```
Query Params:
  hub.mode=subscribe
  hub.verify_token=<configured_verify_token>
  hub.challenge=<challenge_string>
```

**Response:**
```
200 OK: <challenge_string> (plain text)
403 Forbidden: if token mismatch
```

#### 5.1.3 Web Chat WebSocket

- **Service:** Channel Gateway
- **Path:** `WS /api/v1/webhooks/chat`
- **Authentication:** Session token (passed in first message or query param)

**Client → Server Messages:**
```json
{
  "type": "chat_message",
  "payload": {
    "session_token": "sess_abc123",
    "content": "Hello, I need help",
    "media_urls": []
  }
}
```

**Server → Client Messages:**
```json
{
  "type": "ai_response",
  "payload": {
    "message_id": "770e8400-...",
    "content": "Hi! How can I help you today?",
    "media_urls": [],
    "timestamp": "2026-06-23T10:01:30Z"
  }
}
```

---

### 5.2 Agent Inbox APIs

#### 5.2.1 List Conversations

- **Service:** Agent Inbox
- **Path:** `GET /api/v1/agent/conversations`
- **Authentication:** OAuth 2.0 / OIDC (Agent or Admin role)

**Request:**
```
Headers:
  Authorization: Bearer <jwt_token>

Query Params:
  status: active|escalated|pending|resolved (optional, comma-separated for multiple)
  channel: whatsapp|webchat|email (optional)
  assigned_to_me: true|false (optional)
  page: int (default: 1)
  page_size: int (default: 20, max: 100)
  sort: updated_at|created_at (default: updated_at)
  order: desc|asc (default: desc)
```

**Response (200 OK):**
```json
{
  "data": [
    {
      "id": "660e8400-...",
      "customer": {
        "id": "550e8400-...",
        "display_name": "Carlos Mendez",
        "channel_identifiers": {"whatsapp": "+5511999887766"}
      },
      "channel": "whatsapp",
      "status": "escalated",
      "assigned_agent": null,
      "last_message": {
        "content": "I need to speak to a human",
        "sender_type": "customer",
        "created_at": "2026-06-23T10:05:00Z"
      },
      "sla": {
        "first_response_due": "2026-06-23T10:10:00Z",
        "resolution_due": "2026-06-24T10:00:00Z",
        "first_response_breached": false,
        "resolution_breached": false
      },
      "updated_at": "2026-06-23T10:05:00Z"
    }
  ],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total": 45,
    "total_pages": 3
  }
}
```

#### 5.2.2 Get Conversation Detail

- **Path:** `GET /api/v1/agent/conversations/{conversation_id}`
- **Authentication:** OAuth 2.0 / OIDC (Agent or Admin role)

**Response (200 OK):**
```json
{
  "id": "660e8400-...",
  "customer": { "..." },
  "channel": "whatsapp",
  "status": "escalated",
  "assigned_agent": null,
  "messages": [
    {
      "id": "770e8400-...",
      "sender_type": "customer",
      "content": "Hi, I need to reschedule my appointment",
      "created_at": "2026-06-23T10:00:00Z"
    },
    {
      "id": "770e8400-...-002",
      "sender_type": "ai",
      "content": "Hi Carlos! I can help you reschedule...",
      "metadata": {"model": "llama-3.1-8b", "confidence": 0.89},
      "created_at": "2026-06-23T10:00:05Z"
    }
  ],
  "sla": { "..." },
  "created_at": "2026-06-23T10:00:00Z",
  "updated_at": "2026-06-23T10:05:00Z"
}
```

#### 5.2.3 Take Over Conversation

- **Path:** `POST /api/v1/agent/conversations/{conversation_id}/takeover`
- **Authentication:** OAuth 2.0 / OIDC (Agent role)

**Request Body:** `{}` (empty)

**Response (200 OK):**
```json
{
  "id": "660e8400-...",
  "status": "active",
  "assigned_agent": {
    "id": "agent-uuid",
    "display_name": "Aisha Johnson"
  },
  "ai_enabled": false
}
```

**Error (409 Conflict):**
```json
{
  "error": {
    "code": "CONVERSATION_ALREADY_ASSIGNED",
    "message": "Conversation is already assigned to another agent"
  }
}
```

#### 5.2.4 Agent Send Response

- **Path:** `POST /api/v1/agent/conversations/{conversation_id}/messages`
- **Authentication:** OAuth 2.0 / OIDC (Agent role)

**Request Body:**
```json
{
  "content": "I've rescheduled your appointment to Tuesday 2pm.",
  "media_urls": []
}
```

**Response (201 Created):**
```json
{
  "id": "msg-uuid",
  "sender_type": "agent",
  "content": "I've rescheduled your appointment to Tuesday 2pm.",
  "created_at": "2026-06-23T10:10:00Z"
}
```

#### 5.2.5 Resolve Conversation

- **Path:** `POST /api/v1/agent/conversations/{conversation_id}/resolve`
- **Authentication:** OAuth 2.0 / OIDC (Agent role)

**Response (200 OK):**
```json
{
  "id": "660e8400-...",
  "status": "resolved",
  "resolved_at": "2026-06-23T10:15:00Z"
}
```

#### 5.2.6 Agent WebSocket (Real-time Updates)

- **Path:** `WS /api/v1/agent/ws`
- **Authentication:** OAuth 2.0 / OIDC (token in query param or first message)

**Server → Client Events:**
```json
{"type": "new_message", "payload": {"conversation_id": "...", "message": {...}}}
{"type": "conversation_updated", "payload": {"conversation_id": "...", "status": "escalated"}}
{"type": "sla_warning", "payload": {"conversation_id": "...", "sla_type": "first_response", "seconds_remaining": 60}}
```

---

### 5.3 Admin APIs

#### 5.3.1 Setup Wizard — Complete Setup

- **Path:** `POST /api/v1/admin/setup/complete`
- **Authentication:** OAuth 2.0 / OIDC (Admin role)

**Request Body:**
```json
{
  "vault": {
    "url": "https://vault.company.com",
    "api_key": "vk_...",
    "collection_id": "col-uuid"
  },
  "ai": {
    "local_model_endpoint": "http://ollama:11434",
    "local_model_name": "llama-3.1-8b",
    "frontier_provider": "openai",
    "frontier_model_name": "gpt-4o",
    "frontier_api_key": "sk-...",
    "confidence_threshold": 0.7,
    "system_prompt": "You are a helpful customer support agent..."
  },
  "whatsapp": {
    "phone_number_id": "PNID",
    "business_account_id": "BAID",
    "access_token": "EAAG...",
    "webhook_verify_token": "custom_verify_token"
  },
  "pii_shield": {
    "enabled": true,
    "frontier_allowed_with_redaction": false
  }
}
```

**Response (200 OK):**
```json
{
  "status": "complete",
  "deployment_id": "dep-uuid",
  "checks": {
    "vault_connection": "ok",
    "ai_model_reachable": "ok",
    "whatsapp_webhook": "ok"
  }
}
```

#### 5.3.2 Update AI Configuration

- **Path:** `PATCH /api/v1/admin/ai/configuration`
- **Authentication:** OAuth 2.0 / OIDC (Admin role)

**Request Body:** (partial update)
```json
{
  "confidence_threshold": 0.75,
  "routing_policy": {
    "complexity_threshold": 0.6,
    "pii_policy": "local_only"
  }
}
```

**Response (200 OK):** Updated configuration object.

#### 5.3.3 Data Export (GDPR)

- **Path:** `POST /api/v1/admin/compliance/export`
- **Authentication:** OAuth 2.0 / OIDC (Admin role)

**Request Body:**
```json
{
  "customer_identifier": "+5511999887766",
  "channel": "whatsapp",
  "format": "json"
}
```

**Response (202 Accepted):**
```json
{
  "export_id": "export-uuid",
  "status": "processing",
  "estimated_completion": "2026-06-23T10:20:00Z"
}
```

#### 5.3.4 Data Deletion (GDPR Right-to-Erasure)

- **Path:** `POST /api/v1/admin/compliance/delete`
- **Authentication:** OAuth 2.0 / OIDC (Admin role)

**Request Body:**
```json
{
  "customer_identifier": "+5511999887766",
  "channel": "whatsapp",
  "scope": "all_data"
}
```

**Response (202 Accepted):**
```json
{
  "deletion_id": "del-uuid",
  "status": "processing",
  "estimated_completion": "2026-06-23T10:25:00Z"
}
```

---

### 5.4 Health & Metrics

#### 5.4.1 Health Check

- **Path:** `GET /health`
- **Authentication:** None

**Response (200 OK):**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "checks": {
    "database": "ok",
    "redis": "ok",
    "vault": "ok",
    "local_model": "ok",
    "license": "active"
  }
}
```

**Response (503 Service Unavailable):**
```json
{
  "status": "degraded",
  "checks": {
    "database": "ok",
    "redis": "ok",
    "vault": "unavailable",
    "local_model": "ok",
    "license": "active"
  }
}
```

#### 5.4.2 Metrics

- **Path:** `GET /metrics`
- **Authentication:** None (network-restricted)
- **Format:** Prometheus text exposition format

---

### 5.5 Standard Error Response Format

All API errors follow this structure:
```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable error description",
    "details": {}
  }
}
```

**HTTP Status Codes:**
- `400` — Validation error (bad request body)
- `401` — Authentication failed
- `403` — Authorization failed (insufficient permissions)
- `404` — Resource not found
- `409` — Conflict (e.g., conversation already assigned)
- `422` — Unprocessable entity (semantic validation failure)
- `429` — Rate limited
- `500` — Internal server error
- `503` — Service unavailable (dependency down)

---

## 6. Business Logic Specification

### 6.1 Inbound Message Processing Pipeline

**Trigger:** New message received via channel webhook (WhatsApp, web chat, or email).

**Step-by-Step Execution:**

```
STEP 1: Webhook Receipt (Channel Gateway)
  - Receive HTTP POST / WebSocket message
  - Verify authentication (HMAC signature for WhatsApp, session token for web chat)
  - Parse channel-specific format into canonical InboundMessage:
    {
      channel: "whatsapp" | "webchat" | "email",
      channel_conversation_id: string,
      sender_identifier: string,
      content: string,
      media_urls: string[],
      metadata: dict,
      timestamp: datetime
    }
  - Return 200 OK to webhook caller immediately (<5s for WhatsApp)
  - Publish `inbound.message` event to event bus

STEP 2: Message Routing (Message Router)
  - Consume `inbound.message` from event bus
  - Resolve customer:
    - Check Redis cache: `customer:{channel}:{hash(sender_identifier)}`
    - Cache miss → query PostgreSQL `customers` by channel_identifiers
    - Not found → create new customer record
  - Load or create conversation:
    - Lookup by `(channel, channel_conversation_id)`
    - Not found → create new conversation (status: `new`)
  - Check conversation state:
    - If `closed` → create new conversation for returning customer
    - If `pending` → transition to `active` (customer replied)
    - If `escalated` with assigned agent → route to agent queue (skip AI)
    - If `active` with ai_enabled=true → proceed to AI pipeline
  - Append message to conversation (persist to PostgreSQL)
  - Start SLA timer (first_response_due = now + configured SLA)
  - Publish `ProcessRequest` to processing queue

STEP 3: AI Pipeline (AI Engine)
  - Consume `ProcessRequest` from processing queue
  - Execute sub-steps 3a–3f:

  STEP 3a: PII Detection (PII Shield)
    - Run Presidio NER on message content
    - Detect PII types: name, phone, email, address, DOB, health_id, financial, government_id
    - If PII detected:
      - Store original content (encrypted) in messages.content
      - Generate redacted version → messages.content_redacted
      - Set routing_directive = LOCAL_MODEL_ONLY
      - Unless admin override: pii_frontier_allowed_with_redaction = true
        → routing_directive = REDACTED_FRONTIER_OK
    - If no PII:
      - routing_directive = NO_RESTRICTION

  STEP 3b: Complexity Scoring (Model Router)
    - Calculate complexity_score (0.0–1.0):
      - Base: message_length / 500 (capped at 0.3)
      - +0.2 if contains question marks or question words
      - +0.2 if conversation context > 5 turns
      - +0.1 if media attached
      - +0.2 if no matching Vault results (requires general reasoning)
    - Cap at 1.0

  STEP 3c: Model Selection (Model Router)
    - Apply routing logic:
      IF routing_directive == LOCAL_MODEL_ONLY:
        target = local_model, fallback = [escalate]
      ELIF routing_directive == REDACTED_FRONTIER_OK:
        target = frontier_model (redacted text), fallback = [local, escalate]
      ELIF complexity_score > routing_policy.complexity_threshold:
        target = frontier_model, fallback = [local, escalate]
      ELSE:
        target = local_model, fallback = [frontier, escalate]
    - Check circuit breaker for target model:
      - If OPEN → use next in fallback chain
    - Return: {model_endpoint, model_name, fallback_chain, use_redacted_text}

  STEP 3d: Knowledge Retrieval (Vault Client)
    - Build query: current message + last 2 customer messages (context)
    - Check Redis cache: `vault:{collection_id}:{hash(query)}`
    - Cache hit → return cached documents
    - Cache miss → HTTP GET to Vault API:
      POST {vault_url}/api/v1/collections/{collection_id}/retrieve
      Body: {"query": query_text, "top_k": 5}
    - Cache result (TTL: 10 min)
    - Filter results: only include chunks with relevance_score > 0.5
    - Return: documents[]

  STEP 3e: LLM Inference
    - Build prompt:
      System: {ai_configuration.system_prompt}
      Knowledge: {formatted vault documents with source attribution}
      Context: {last N messages in conversation}
      Customer: {customer metadata (name, tags)}
      User: {current message (or redacted version if routing requires)}
    - Call model endpoint:
      POST {model_endpoint}/v1/chat/completions
      Body: {model, messages, temperature: 0.3, max_tokens: 1024}
    - Parse response: extract assistant message content
    - If streaming supported: stream tokens, assemble full response

  STEP 3f: Confidence Scoring & Decision
    - Calculate confidence (0.0–1.0):
      - If model provides logprobs: use average token probability
      - Else: heuristic based on:
        - Vault source relevance (avg score of top 3 sources) × 0.4
        - Response coherence (no refusal/hedging language) × 0.3
        - Factual grounding (response references retrieved docs) × 0.3
    - Decision:
      IF confidence >= conversation.confidence_threshold:
        → Format response for channel
        → Publish `outbound.message` to event bus
        → Log: ai.decision (confidence, model, routing)
      ELSE:
        → Escalate to human:
          - Transition conversation state: active → escalated
          - Publish `conversation.state_changed` event
          - Publish `agent.escalation` event (notify Agent Inbox)
        → Optionally send auto-reply: "Let me connect you with a team member..."
        → Log: ai.decision (confidence, model, escalated: true)

STEP 4: Outbound Delivery (Channel Gateway — OutboundDispatcher)
  - Consume `outbound.message` from event bus
  - Format message for target channel:
    - WhatsApp: text message API (or template if outside 24h window)
    - Web chat: WebSocket push
    - Email: SMTP send
  - Deliver via channel API
  - On success: log delivery confirmation
  - On failure: retry (3x, exponential backoff) → dead-letter queue
```

**Edge Cases:**
- Duplicate webhook delivery: deduplicate by `channel_message_id`
- Customer sends multiple messages rapidly: each processed independently; context includes all prior messages
- Media-only message (no text): PII Shield skips text detection; AI receives media description
- Conversation in `pending` state: customer reply reactivates conversation
- WhatsApp 24h window expired: use pre-approved template message for outbound

**Failure Handling:**
- PII Shield failure: fail-open (allow processing, log warning, alert)
- Vault API failure: proceed without knowledge (AI uses general knowledge + disclaimer) or escalate
- Model inference timeout (30s): circuit breaker opens, fallback to next model in chain
- All models unavailable: escalate to human, queue message, send auto-reply
- Outbound delivery failure: retry 3x, then dead-letter; admin notified after 1 hour

---

### 6.2 Human Takeover Flow

**Trigger:** Agent clicks "Take Over" in Agent Inbox, OR AI escalates due to low confidence.

**Step-by-Step:**

```
STEP 1: Escalation (AI-initiated or manual)
  - AI Engine determines confidence < threshold
  - Publish escalation event: conversation.state → escalated

STEP 2: Agent Assignment
  - Agent views escalated conversation in inbox
  - Agent clicks "Take Over"
  - POST /api/v1/agent/conversations/{id}/takeover
  - Conversation Manager:
    - Verify conversation is escalated and unassigned
    - Set assigned_agent_id = current agent
    - Set ai_enabled = false (disable AI auto-respond)
    - Transition state: escalated → active
    - Publish: conversation.agent_assigned

STEP 3: Human Response
  - Agent composes response in inbox
  - POST /api/v1/agent/conversations/{id}/messages
  - Conversation Manager:
    - Persist message (sender_type: agent)
    - Publish outbound.message to event bus
    - Channel Gateway delivers to customer

STEP 4: Resolution
  - Agent clicks "Resolve"
  - POST /api/v1/agent/conversations/{id}/resolve
  - Conversation Manager:
    - Transition state: active → resolved
    - Re-enable AI for future conversations from this customer
    - Clear assigned_agent_id
    - Log resolution in audit trail
```

---

### 6.3 License Validation Flow

**Trigger:** Application startup, periodic check (every 24h), or admin command.

```
STEP 1: Load License State
  - Read from PostgreSQL `license_state` table

STEP 2: Online Validation (if internet available)
  - POST to ODW.ai Billing API: /api/v1/licenses/validate
  - Body: {license_key, deployment_id, version}
  - Response: {status, tier, features, valid_until}
  - Update local license_state

STEP 3: Offline Validation (if no internet)
  - Verify license key signature (RSA public key embedded)
  - Check expiry date
  - If within grace period (14 days post-expiry): allow with warnings

STEP 4: Feature Gate Enforcement
  - On every feature access: check license_state.features[feature_name]
  - If denied: return 403 with message about required tier

STEP 5: Grace Period Handling
  - If license expired < 14 days ago: allow all paid features, log warning
  - If license expired > 14 days ago: downgrade to free tier features
  - Notify admin via dashboard banner and email (if configured)
```

---

### 6.4 PII Detection and Routing Decision

**Trigger:** Every inbound customer message, before AI inference.

```
INPUT: raw_message_text (string)

STEP 1: Run Presidio Analyzer
  - Entities: PERSON, PHONE_NUMBER, EMAIL_ADDRESS, STREET_ADDRESS,
    DATE_OF_BIRTH, MEDICAL_LICENSE, CREDIT_CARD, IBAN, US_SSN,
    PASSPORT, NATIONAL_ID
  - Confidence threshold: 0.85 (Presidio internal)

STEP 2: Apply Custom Patterns
  - Operator-defined regex patterns (e.g., patient ID format, policy numbers)
  - Loaded from ai_configurations.pii_shield_custom_patterns

STEP 3: Aggregate Results
  - pii_detected = any entity found above threshold
  - pii_types = list of unique entity types found
  - Generate redacted_text: replace each PII span with placeholder
    Example: "My name is John and my phone is 555-1234"
    → "My name is [PERSON] and my phone is [PHONE_NUMBER]"

STEP 4: Determine Routing Directive
  IF NOT pii_detected:
    directive = "NO_RESTRICTION"
  ELIF pii_detected AND pii_frontier_allowed_with_redaction:
    directive = "REDACTED_FRONTIER_OK"
  ELSE:
    directive = "LOCAL_MODEL_ONLY"

OUTPUT: {pii_detected, pii_types, redacted_text, routing_directive}
```

---

## 7. State Management & Data Flow

**Stateless Components:** Channel Gateway, Message Router, AI Engine workers, Outbound Dispatcher — all scale horizontally; no local state.

**Stateful Components:**
- **PostgreSQL** — Source of truth for conversations, messages, customers, configuration, audit logs
- **Redis** — Hot-path cache (customer lookup, conversation context, Vault results) + message queue (Redis Streams)

**Caching Layers:**

| Cache | Key Pattern | TTL | Purpose |
|---|---|---|---|
| Customer lookup | `customer:{channel}:{identifier_hash}` | 5 min | Avoid DB query for repeat customers |
| Vault query | `vault:{collection}:{query_hash}` | 10 min | Avoid re-querying for common questions |
| Conversation context | `context:{conversation_id}` | 30 min | Fast context loading for active conversations |
| AI configuration | `ai_config:{deployment_id}` | 60 min | Rarely changes; avoid DB reads |

**Full Data Flow (inbound message → response):**
1. Webhook → Channel Gateway (stateless, normalizes) → Event Bus
2. Event Bus → Message Router (stateless, resolves customer via cache/DB) → Processing Queue
3. Processing Queue → AI Engine (stateless worker) → PII Shield → Model Router → Vault Client (cache → API) → LLM → Confidence Check
4. AI Engine → Event Bus (outbound.message) → Channel Gateway → Customer
5. All state writes go to PostgreSQL; cache invalidation on write

---

## 8. Background Jobs & Asynchronous Processing

**Queue System:** Redis Streams (default) / NATS JetStream (Kubernetes)

| Job Name | Trigger | Input/Output | Retry | Idempotency |
|---|---|---|---|---|
| Inbound message processing | Event bus (`inbound.message`) | InboundMessage → ProcessRequest | 3x exponential (1s, 5s, 30s) | Dedup by `channel_message_id` |
| Outbound message delivery | Event bus (`outbound.message`) | OutboundMessage → channel API | 3x exponential (1s, 5s, 30s) | Idempotent channel APIs (message ID) |
| SLA timer check | Cron (every 60s) | Scan active conversations → emit `sla.breach` | N/A | Stateless scan |
| Data retention enforcement | Cron (daily 02:00) | Delete conversations/messages past retention | 1x | Checked by date; safe to re-run |
| Vault cache warmup | Cron (every 30 min) | Prefetch top-50 common queries | 2x | Cache writes are idempotent |
| License re-validation | Cron (every 24h) | Validate with Billing API → update state | 3x | Last-write-wins |
| Compliance report generation | Admin command / weekly cron | Aggregate audit data → PDF/JSON | 2x | Output keyed by report_id |
| Dead-letter retry | Cron (every 15 min) | Re-process DLQ messages | 1x additional | Same idempotency as original |
| Backup verification | Cron (weekly) | Test restore from latest backup | N/A | Read-only operation |

**Failure Strategy:** Messages failing all retries move to dead-letter queue. Admin dashboard shows DLQ depth. Manual reprocessing available via admin API.

---

## 9. External Integrations

| Integration | Endpoint | Auth | Rate Limits | Fallback |
|---|---|---|---|---|
| WhatsApp Business API (Meta) | `https://graph.facebook.com/v19.0/{phone_id}/messages` | Bearer token (access_token) | 200 calls/hour per phone number | Queue + retry; notify admin |
| WhatsApp BSP (e.g., Twilio, 360dialog) | BSP-specific REST API | API key / OAuth | BSP-defined | Same as Meta fallback |
| OpenAI API | `https://api.openai.com/v1/chat/completions` | Bearer token (API key) | Tier-dependent (5K–10K RPM) | Circuit breaker → local model → escalate |
| Anthropic API | `https://api.anthropic.com/v1/messages` | x-api-key header | 50 RPM (default) | Circuit breaker → local model → escalate |
| Ollama (local) | `http://ollama:11434/api/chat` | None (local network) | Hardware-dependent | Circuit breaker → frontier → escalate |
| ODW.ai Vault | `{vault_url}/api/v1/collections/{id}/retrieve` | Bearer token (Vault API key) | 1000 req/min | Serve from cache; AI proceeds without knowledge + disclaimer |
| ODW.ai Auth (OIDC) | `{auth_url}/.well-known/openid-configuration` | Standard OIDC | N/A | Reject unauthenticated requests |
| ODW.ai Billing | `{billing_url}/api/v1/licenses/validate` | License key | 100 req/min | Offline validation (embedded RSA key) |
| S3/MinIO | S3-compatible API | Access key + secret | N/A (local) | Fail writes; queue for retry |

---

## 10. Configuration & Environment Variables

**Required Environment Variables:**

| Variable | Purpose | Example (dev) | Example (prod) |
|---|---|---|---|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+asyncpg://desk:desk@localhost:5432/desk` | `postgresql+asyncpg://desk:${DB_PASS}@postgres:5432/desk` |
| `REDIS_URL` | Redis connection string | `redis://localhost:6379/0` | `redis://redis:6379/0` |
| `SECRET_KEY` | Application secret (JWT signing, encryption) | `dev-secret-key-change-me` | (generated, 64-char random) |
| `DEPLOYMENT_ID` | Unique deployment identifier | `dev-local-001` | (auto-generated on first boot) |
| `VAULT_URL` | ODW.ai Vault base URL | `http://localhost:8100` | `https://vault.company.com` |
| `VAULT_API_KEY` | Vault API authentication | `vk_dev_...` | (from secrets manager) |
| `VAULT_COLLECTION_ID` | Default knowledge base collection | `col-dev-001` | `col-prod-...` |
| `AUTH_OIDC_ISSUER` | OIDC provider URL | `http://localhost:8080/realms/odw` | `https://auth.company.com/realms/odw` |
| `WHATSAPP_ACCESS_TOKEN` | Meta/BSP access token | (empty for free tier) | `EAAG...` |
| `WHATSAPP_PHONE_NUMBER_ID` | WhatsApp phone number ID | (empty) | `1234567890` |
| `WHATSAPP_WEBHOOK_VERIFY_TOKEN` | Webhook verification token | `dev_verify_token` | (random, configured in Meta) |
| `OLLAMA_ENDPOINT` | Local model endpoint | `http://ollama:11434` | `http://ollama:11434` |
| `LOCAL_MODEL_NAME` | Local model identifier | `llama-3.1-8b` | `llama-3.1-70b` |
| `FRONTIER_PROVIDER` | Frontier model provider | `openai` | `openai` |
| `FRONTIER_API_KEY` | Frontier model API key | (empty for local-only) | (from secrets manager) |
| `FRONTIER_MODEL_NAME` | Frontier model identifier | `gpt-4o-mini` | `gpt-4o` |
| `LICENSE_KEY` | Desk license key | `free` | `desk-prod-...` |
| `S3_ENDPOINT` | S3-compatible endpoint | `http://minio:9000` | `https://s3.company.com` |
| `S3_ACCESS_KEY` | S3 access key | `minioadmin` | (from secrets manager) |
| `S3_SECRET_KEY` | S3 secret key | `minioadmin` | (from secrets manager) |
| `S3_BUCKET` | S3 bucket name | `desk-dev` | `desk-prod` |
| `LOG_LEVEL` | Logging level | `DEBUG` | `INFO` |
| `EVENT_BUS_BACKEND` | `redis_streams` or `nats` | `redis_streams` | `nats` (K8s) |
| `CONFIDENCE_THRESHOLD` | Default AI confidence threshold | `0.6` | `0.7` |
| `PII_SHIELD_ENABLED` | Enable PII detection | `true` | `true` |
| `SLA_FIRST_RESPONSE_MINUTES` | SLA for first response | `10` | `5` |
| `SLA_RESOLUTION_HOURS` | SLA for resolution | `48` | `24` |
| `DATA_RETENTION_DAYS` | Conversation data retention | `365` | `365` |

**Separation by Environment:**
- `dev`: All services on localhost, debug logging, free tier license, local Ollama
- `staging`: Docker Compose on single VM, INFO logging, paid tier (test key), production-like config
- `production`: Customer-managed infra, INFO logging, paid tier license, secrets from manager

---

## 11. Security Implementation Details

**Authentication Flow:**
1. User accesses admin/agent UI → redirected to ODW.ai Auth (OIDC)
2. User authenticates → receives JWT (access token: 1h, refresh token: 7d)
3. JWT presented on every API request in `Authorization: Bearer` header
4. Desk validates JWT signature against OIDC provider's public keys (cached)
5. Role claims extracted from JWT (`realm_access.roles` or custom claim)

**Authorization Model (RBAC):**
- **Admin:** Full access to all endpoints
- **Agent:** Inbox operations only (conversations, messages, takeover, resolve)
- **Read-Only:** View conversations and metrics; no write operations
- Roles consumed from JWT claims; no local role management

**Token Structure (JWT Claims):**
```json
{
  "sub": "user-uuid",
  "email": "agent@company.com",
  "name": "Aisha Johnson",
  "roles": ["desk_agent"],
  "deployment_id": "dep-uuid",
  "iat": 1719136800,
  "exp": 1719140400
}
```

**Data Encryption:**
- At rest (database): AES-256 via PostgreSQL TDE or LUKS filesystem encryption
- At rest (PII fields): Application-level AES-256-GCM; keys from secrets manager
- At rest (object storage): S3 SSE-S3 or SSE-KMS
- In transit: TLS 1.3 for all external; mTLS for inter-service in Kubernetes
- Key management: Environment variables (Compose) or HashiCorp Vault / AWS Secrets Manager (K8s)

**Input Validation:**
- All API inputs validated via Pydantic models (strict types, length limits)
- SQL injection prevented via parameterized queries (SQLAlchemy ORM)
- XSS prevented via output encoding in React frontend
- Webhook payloads verified via HMAC signature before processing
- File uploads validated (type, size limits: 10MB max)

---

## 12. Error Handling & Logging

**Standard Error Response:**
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Request validation failed",
    "details": {
      "field": "confidence_threshold",
      "constraint": "must be between 0.0 and 1.0"
    }
  }
}
```

**Error Categories:**
- **Validation errors (4xx):** Bad input, missing fields, invalid values → return specific field errors
- **System errors (5xx):** Unexpected failures → log full traceback, return generic message
- **External dependency failures (503):** Vault/API down → circuit breaker state, fallback triggered, log dependency name

**Logging Format:**
- Structured JSON via `structlog`
- Every log entry includes: `timestamp`, `level`, `event`, `trace_id`, `component`, `module`
- PII filter: all log output passes through PII redaction before emission
- Example:
```json
{"timestamp": "2026-06-23T10:01:30Z", "level": "info", "event": "ai.inference.complete", "trace_id": "tr-abc123", "component": "ai-engine", "model": "llama-3.1-8b", "confidence": 0.89, "latency_ms": 2340}
```

**Correlation IDs:**
- Every inbound webhook generates a `trace_id` (UUID)
- Propagated through event bus, AI pipeline, outbound delivery
- Logged with every related operation
- Exportable for debugging specific conversations

---

## 13. Performance Considerations

**Expected Load (MVP per deployment):**
- 1,000 concurrent conversations
- ~100 messages/second peak
- ~10,000 conversations/day (medium deployment)

**Bottleneck Analysis:**

| Bottleneck | Impact | Mitigation |
|---|---|---|
| LLM inference latency (3–8s) | Customer wait time | Local model preferred; parallel workers; streaming where supported |
| Vault query latency (cold: 500ms–1s) | Adds to total response time | Redis cache (10-min TTL); prefetch common queries |
| PostgreSQL write throughput | Message persistence | Batch inserts (100ms buffer window); async audit log writes |
| WebSocket connection limit (~10K/node) | Agent inbox scaling | Horizontal scaling of Agent Inbox nodes |

**Optimization Strategies:**
- **Caching:** 4-layer cache (customer, context, Vault, config) with appropriate TTLs
- **Batching:** Audit log writes buffered (100ms window); message inserts batched
- **Parallelism:** Multiple AI workers consume from processing queue; Vault query + PII detection can run in parallel
- **Connection pooling:** PgBouncer for PostgreSQL; Redis connection pool per worker
- **Token optimization:** Truncate conversation context to last 10 turns; compress system prompt; select high-density Vault chunks

---

## 14. Testing Strategy

**Unit Tests:**
- Coverage target: ≥80% for business logic modules (AI Engine, PII Shield, Model Router, Conversation Manager)
- Framework: pytest + pytest-asyncio
- Mocking: External dependencies (Vault API, LLM APIs, Redis) mocked via `unittest.mock` or `respx` (HTTP mocking)
- Key test areas: PII detection accuracy, routing decisions, state transitions, confidence scoring

**Integration Tests:**
- Scope: Module-to-module communication via event bus; database operations; cache behavior
- Infrastructure: Docker Compose with PostgreSQL + Redis (test containers)
- Key scenarios: Full inbound→AI→outbound pipeline; human takeover flow; license validation
- Vault integration: Mock Vault server with canned responses

**End-to-End Tests:**
- Full deployment via Docker Compose
- Simulate WhatsApp webhook → verify AI response delivered
- Simulate agent takeover → verify state transitions
- Simulate PII detection → verify routing to local model only
- Performance: Load test with Locust (100 msg/s target)

**Mocking Strategy:**
- LLM APIs: Canned responses with configurable latency and confidence
- Vault API: Mock server returning pre-indexed documents
- WhatsApp API: Mock Meta endpoint returning success/failure
- Redis: Real Redis in Docker (no mocking — too central to behavior)

---

## 15. Deployment & Build Instructions

**Build Steps:**
```bash
# Backend
cd desk
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head  # Run migrations

# Frontend
cd desk/frontend
npm install
npm run build  # Outputs to dist/

# Container images
docker build -t desk-api:latest -f Dockerfile.api .
docker build -t desk-worker-ai:latest -f Dockerfile.worker .
docker build -t desk-web:latest -f Dockerfile.web .
```

**Dockerfile Requirements:**
- Base image: `python:3.11-slim` (backend), `node:20-alpine` (build) → `nginx:alpine` (frontend)
- Non-root user in all containers
- Health check: `CMD ["curl", "-f", "http://localhost:8000/health"]`
- Multi-stage build for frontend (build → static copy)

**Service Startup Sequence:**
1. PostgreSQL (wait for ready)
2. Redis (wait for ready)
3. MinIO (wait for ready)
4. `desk-api` (runs migrations on startup, then serves)
5. `desk-worker-ai` (connects to event bus, begins consuming)
6. `desk-worker-outbound` (connects to event bus)
7. `desk-scheduler` (starts cron jobs)
8. `desk-web` (serves static frontend)
9. Traefik (routes external traffic)

**CI/CD:**
- GitHub Actions: lint (ruff) → type-check (mypy) → unit tests → integration tests → security scan (Trivy) → build images → push to GHCR
- CD: Deploy to staging → smoke tests → manual approval → rolling update to production
- Image tagging: `desk-api:v1.0.0-abc1234` (semver + git SHA)

---

## 16. Observability Hooks

**Metrics (Prometheus `/metrics` endpoint):**

| Category | Metrics |
|---|---|
| Inbound | `desk_inbound_messages_total{channel}`, `desk_inbound_message_duration_seconds` |
| AI Processing | `desk_ai_inference_duration_seconds{model}`, `desk_ai_confidence_score{model}`, `desk_ai_escalations_total` |
| Routing | `desk_routing_decisions_total{target,reason}`, `desk_pii_detected_total` |
| Outbound | `desk_outbound_messages_total{channel,status}`, `desk_outbound_delivery_duration_seconds` |
| Cache | `desk_cache_hits_total{cache}`, `desk_cache_misses_total{cache}` |
| Queue | `desk_queue_depth{queue}`, `desk_dead_letter_count{queue}` |
| System | `desk_active_conversations`, `desk_connected_agents`, `desk_vault_query_duration_seconds` |

**Logs:**
- Structured JSON (structlog) with PII filter
- Levels: DEBUG (dev), INFO (prod default)
- Correlation via `trace_id` on every entry

**Traces:**
- OpenTelemetry SDK integrated
- Spans: webhook receipt → routing → PII detection → Vault query → model inference → outbound delivery
- Export: OTLP (operators configure Jaeger/Tempo backend)

**Health Checks:**
- `GET /health` — Overall system health (DB, Redis, Vault, model, license)
- `GET /health/ready` — Kubernetes readiness probe (can serve traffic)
- `GET /health/live` — Kubernetes liveness probe (process alive)

**Pre-configured Alerts (Grafana):**
- AI inference P95 > 10s for 5 min → Warning
- Escalation rate > 50% for 10 min → Warning
- DLQ depth > 100 for 5 min → Critical
- WhatsApp webhook failure > 5% for 5 min → Critical
- DB connection pool > 90% → Critical
- Disk > 85% → Warning
- License expiry < 14 days → Info

---

## 17. File & Folder Structure

```
desk/
├── docker-compose.yml
├── docker-compose.dev.yml
├── Dockerfile.api
├── Dockerfile.worker
├── Dockerfile.web
├── alembic.ini
├── alembic/
│   ├── env.py
│   └── versions/
├── requirements.txt
├── pyproject.toml
├── src/
│   └── desk/
│       ├── __init__.py
│       ├── main.py                    # FastAPI app entry point
│       ├── config.py                  # Settings (pydantic-settings)
│       ├── dependencies.py            # FastAPI dependency injection
│       ├── channels/
│       │   ├── __init__.py
│       │   ├── base.py               # ChannelAdapter interface
│       │   ├── whatsapp.py           # WhatsApp Business API adapter
│       │   ├── webchat.py            # Web chat WebSocket adapter
│       │   ├── email.py              # Email IMAP/SMTP adapter
│       │   └── outbound.py           # OutboundDispatcher
│       ├── router/
│       │   ├── __init__.py
│       │   ├── message_router.py     # MessageRouter module
│       │   └── customer_resolver.py  # Customer resolution logic
│       ├── conversations/
│       │   ├── __init__.py
│       │   ├── manager.py            # ConversationManager
│       │   ├── state_machine.py      # State transitions
│       │   ├── sla.py                # SLA timer logic
│       │   └── models.py             # SQLAlchemy models
│       ├── ai/
│       │   ├── __init__.py
│       │   ├── engine.py             # AI Engine orchestrator
│       │   ├── pipeline.py           # Pipeline steps
│       │   ├── prompt_builder.py     # Prompt construction
│       │   ├── confidence.py         # Confidence scoring
│       │   ├── pii_shield.py         # PII detection + redaction
│       │   ├── model_router.py       # Model selection logic
│       │   ├── vault_client.py       # Vault API client + cache
│       │   └── providers/
│       │       ├── __init__.py
│       │       ├── base.py           # ModelProvider interface
│       │       ├── ollama.py         # Ollama/vLLM provider
│       │       ├── openai.py         # OpenAI provider
│       │       └── anthropic.py      # Anthropic provider
│       ├── agents/
│       │   ├── __init__.py
│       │   ├── inbox_api.py          # Agent REST endpoints
│       │   ├── websocket.py          # Agent WebSocket manager
│       │   └── models.py             # Agent SQLAlchemy models
│       ├── admin/
│       │   ├── __init__.py
│       │   ├── setup_api.py          # Setup wizard endpoints
│       │   ├── config_api.py         # AI config endpoints
│       │   ├── compliance_api.py     # Export/delete/report endpoints
│       │   └── license_api.py        # License management
│       ├── compliance/
│       │   ├── __init__.py
│       │   ├── engine.py             # ComplianceEngine
│       │   ├── retention.py          # Retention enforcement
│       │   ├── export.py             # Data export service
│       │   ├── deletion.py           # Data deletion service
│       │   └── audit.py              # Audit log writer (hash-chained)
│       ├── license/
│       │   ├── __init__.py
│       │   └── manager.py            # License validation + feature gates
│       ├── suite/
│       │   ├── __init__.py
│       │   ├── auth_client.py        # OIDC client
│       │   └── billing_client.py     # Billing API client
│       ├── events/
│       │   ├── __init__.py
│       │   ├── bus.py                # Event bus abstraction
│       │   ├── redis_streams.py      # Redis Streams implementation
│       │   ├── nats.py               # NATS JetStream implementation
│       │   └── schemas.py            # Event payload schemas
│       ├── models/
│       │   ├── __init__.py
│       │   ├── base.py               # SQLAlchemy base, mixins
│       │   ├── customer.py
│       │   ├── conversation.py
│       │   ├── message.py
│       │   ├── agent.py
│       │   ├── ai_configuration.py
│       │   ├── audit_log.py
│       │   └── license_state.py
│       ├── schemas/
│       │   ├── __init__.py
│       │   ├── api.py                # Request/response Pydantic models
│       │   ├── events.py             # Event payload models
│       │   └── channels.py           # Channel-specific schemas
│       └── utils/
│           ├── __init__.py
│           ├── encryption.py         # Field-level encryption
│           ├── pii_filter.py         # Log PII redaction filter
│           └── hashing.py            # Audit log hash chain
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   ├── api/                      # API client (TanStack Query)
│   │   ├── components/               # Shared UI components
│   │   ├── pages/
│   │   │   ├── inbox/                # Agent inbox pages
│   │   │   ├── admin/                # Admin dashboard pages
│   │   │   └── setup/                # Setup wizard pages
│   │   ├── hooks/                    # Custom React hooks
│   │   ├── stores/                   # Zustand stores
│   │   └── types/                    # TypeScript type definitions
│   └── public/
│       └── widget.js                 # Embeddable web chat widget script
├── helm/
│   ├── Chart.yaml
│   ├── values.yaml
│   └── templates/
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/
└── docs/
    ├── api.md
    ├── deployment.md
    └── configuration.md
```

---

## 18. Coding Standards & Conventions

**Naming Conventions:**
- Python: `snake_case` for functions/variables, `PascalCase` for classes, `UPPER_SNAKE_CASE` for constants
- TypeScript/React: `camelCase` for functions/variables, `PascalCase` for components/types
- Database: `snake_case` for tables, columns, indexes
- API paths: `kebab-case` (`/api/v1/agent/conversations`)
- Event types: `dot.separated` (`inbound.message`, `conversation.state_changed`)

**API Naming Rules:**
- RESTful resource naming: `/api/v1/{resource}` (plural nouns)
- Nested resources: `/api/v1/conversations/{id}/messages`
- Actions (non-CRUD): `POST /api/v1/conversations/{id}/takeover`
- Consistent pagination: `page`, `page_size`, `total`, `total_pages`
- Consistent sorting: `sort`, `order` query params

**Error Format Standard:**
```json
{
  "error": {
    "code": "UPPER_SNAKE_CASE_CODE",
    "message": "Human-readable description",
    "details": {}
  }
}
```

**Code Organization Principles:**
- One module = one responsibility (single-module ownership of tables)
- No cross-module direct imports; communicate via event bus or defined interfaces
- All external calls behind interfaces (ModelProvider, ChannelAdapter, KnowledgeProvider)
- Configuration via pydantic-settings (typed, validated, env-sourced)
- Async-first: all I/O operations use `async/await`
- Type hints everywhere: mypy strict mode enabled
- Docstrings on all public functions (Google style)

**Git Conventions:**
- Conventional commits: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`
- Branch naming: `feature/DESK-123-short-description`, `fix/DESK-456-issue`
- PR required for merge; CI must pass

---

## 19. Assumptions & Constraints

**Assumptions (inherited from PRD/SAD):**
- A1: Operators can deploy Docker/Kubernetes infrastructure (target persona is DevOps-literate)
- A2: WhatsApp Business API access is obtainable (multiple BSPs available)
- A3: Local models (8B–70B) achieve ≥60% resolution rate when grounded in Vault knowledge
- A4: Vault API remains stable across Desk releases (version-pinned, semver)
- A5: Target scale is 1,000 concurrent conversations per deployment (SMB market)
- A6: Single-region deployment (operators choose their region for data residency)
- A7: PostgreSQL + Redis sufficient for MVP (no Kafka/Elasticsearch needed)
- A8: OpenAI and Anthropic APIs remain available and reasonably priced

**Constraints:**
- C1: 6-month MVP timeline with 5–7 engineers → strict scope management
- C2: WhatsApp 24-hour conversation window and template requirements → limits outbound flexibility
- C3: Self-hosted only (no managed SaaS) → limits market to infrastructure-capable customers
- C4: AGPL-3.0 licensing → some enterprises cannot adopt; commercial license available
- C5: Vault dependency (shared API contract) → version-pinned client, compatibility tested in CI
- C6: Regulatory compliance varies by jurisdiction → Desk provides tools, operator ensures compliance
- C7: Local model hardware requirements (GPU for larger models) → CPU-optimized quantized models available
- C8: Python 3.11+ required (async features, performance)
- C9: Maximum 50–60KB TSD document size (conciseness enforced)

---

**End of Technical Specification Document**
