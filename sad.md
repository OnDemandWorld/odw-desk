# System Architecture Document: ODW.ai Desk

**Product:** Desk — Self-Hosted, WhatsApp-First AI Customer Support Agent
**Author:** ODW.ai Architecture Team
**Version:** 1.2
**Date:** 2026-06-24
**Status:** Draft
**Input Document:** PRD v1.2 (2026-06-24)

---

## 1. Architecture Overview

### 1.1 Purpose

Desk is a self-hosted, WhatsApp-first AI customer support agent that gives regulated businesses full sovereignty over conversation data while delivering intelligent, automated support grounded in the operator's own knowledge base (Vault). It is a module within the ODW.ai suite, sharing authentication, user management, and UI patterns with sibling products.

### 1.2 Architectural Style

**Modular monolith with event-driven internal messaging and channel-agnostic adapter pattern**, deployed as a set of containerized services via Docker Compose (single-node) or Kubernetes Helm chart (clustered).

The system is organized into clearly bounded modules within a single deployable codebase. Inter-module communication uses an internal event bus (Redis Streams or NATS) rather than direct function calls, preserving the ability to extract modules into independent services when scaling demands it.

Channel integration follows a pluggable adapter pattern: a generic `ChannelAdapter` interface defines the contract for all channels (WhatsApp Business API, WhatsApp Baileys Bridge, web chat, email, and future channels like Telegram, Discord, Slack, Signal, iMessage). Each adapter implements the same interface, enabling new channels to be added without architectural changes.

### 1.3 Justification & Trade-offs

| Decision | Rationale | Trade-off Accepted |
|---|---|---|
| Modular monolith over microservices | Team size (5–7 engineers) cannot sustain distributed-service operational overhead; single deployable reduces infrastructure complexity for self-hosted operators | Sacrifices independent deployability of modules until v2 extraction; requires disciplined module boundaries to avoid coupling drift |
| Event-driven internal messaging | Decouples channel ingestion from AI processing; enables back-pressure, retries, and dead-letter handling without blocking inbound webhooks | Adds operational complexity (message queue durability, ordering guarantees); requires idempotent consumers |
| Container-first deployment | Target operators are technical (DevOps-literate); containers provide reproducible environments and align with Kubernetes scaling path | Excludes operators without container infrastructure; mitigated by single-command Docker Compose entry point |
| PostgreSQL as single source of truth | Regulated customers require ACID transactions for audit trails; JSONB columns handle flexible metadata without schema proliferation | Limits write throughput vs. purpose-built event stores; acceptable at target scale (1,000 concurrent conversations per deployment) |
| Suite integration via API contracts (not shared database) | Preserves Vault and Auth as independently deployable modules; avoids tight coupling to Vault's internal schema | Adds latency to Vault queries (~50–100ms network hop); mitigated by Redis caching layer |

---

## 2. High-Level System Components

### 2.1 Component Map

| # | Component | Responsibility | Inputs | Outputs | Technology |
|---|---|---|---|---|---|
| C1 | **Channel Gateway** | Terminates inbound/outbound connections via pluggable channel adapters. Normalizes all messages into canonical `InboundMessage` format. Supports: WhatsApp Business API (enterprise), WhatsApp Baileys Bridge (quick-start), web chat (WebSocket), email (IMAP/SMTP). Future adapters: Telegram, Discord, Slack, Signal, iMessage. | External webhooks, WebSocket connections, Baileys bridge (Node.js sidecar), IMAP polling | Canonical `InboundMessage` events on internal bus | FastAPI (Python), channel adapter plugins, WebSocket server, Baileys bridge (Node.js sidecar), IMAP client |
| C2 | **Message Router** | Receives canonical inbound messages, resolves or creates customer profiles, loads conversation context, and dispatches to the appropriate processing pipeline (AI or human-agent). | `InboundMessage` events | Routed work items on processing queue | Internal module (Python), Redis Streams |
| C3 | **Conversation Manager** | Maintains conversation state machine (active → pending → escalated → resolved). Persists messages, manages multi-turn context, enforces SLA timers. | Routed work items, agent actions, AI responses | State transitions, persisted messages, SLA events | Internal module, PostgreSQL |
| C4 | **AI Engine** | Orchestrates the RAG pipeline: PII detection → model routing → Vault retrieval → LLM inference → confidence scoring → response generation. | Processing queue work items | AI responses (with metadata: model used, confidence, routing decision) | Python, LangChain/LlamaIndex, Ollama/vLLM client, OpenAI/Anthropic SDK |
| C5 | **PII Shield** | Detects personally identifiable information in messages. Redacts PII before forwarding to frontier models. Enforces routing policy (PII → local model only, unless admin overrides). | Raw message content | PII detection result, redacted content, routing directive | Presidio or custom NER model, internal module |
| C6 | **Model Router** | Selects inference target (local vs. frontier) based on routing policy, PII detection result, and complexity scoring. Implements fallback logic on model unavailability. | Routing directive, complexity score | Selected model endpoint, fallback chain | Internal module, configuration store |
| C7 | **Vault Client** | Queries ODW.ai Vault's retrieval API for relevant knowledge base documents. Caches results. Handles authentication to Vault. | Query text, collection ID | Retrieved document chunks with relevance scores | HTTP client, Redis cache |
| C8 | **Agent Inbox Service** | Serves the human-agent interface: conversation list, message history, response composition, takeover/handoff actions. Real-time updates via WebSocket. | Agent HTTP/WebSocket requests | Conversation data, real-time event stream | FastAPI, WebSocket, PostgreSQL |
| C9 | **Admin Dashboard Service** | Serves the operator/admin interface: setup wizard, AI configuration, compliance reports, audit logs, license management. | Admin HTTP requests | Configuration data, reports, audit exports | FastAPI, React (frontend) |
| C10 | **Compliance Engine** | Enforces data retention policies, generates compliance reports, handles data export/deletion requests (GDPR right-to-erasure), maintains tamper-evident audit log. | Admin commands, scheduled jobs | Export files, deletion confirmations, compliance reports | Internal module, PostgreSQL, S3-compatible storage |
| C11 | **License Manager** | Validates license keys (online and offline), enforces feature gates between free and paid tiers, manages grace periods. | Startup hook, periodic check, admin commands | Feature gate decisions, license status | Internal module, ODW.ai Billing API |
| C12 | **Data Store** | Primary persistence layer: conversation data, customer profiles, audit logs, configuration. | All components | Durable storage, query results | PostgreSQL 16+, Redis 7+ (cache + queue), S3-compatible object storage |
| C13 | **Event Bus** | Internal asynchronous messaging backbone. Carries inbound messages, AI responses, state transitions, and audit events between components. | All components (producers) | All components (consumers) | Redis Streams (default) or NATS JetStream (Kubernetes) |
| C14 | **Suite Integration Layer** | Manages connectivity to ODW.ai Auth (SSO/OIDC), Vault (knowledge retrieval), Billing (license validation), and unified admin dashboard. | Internal API calls from all modules | Auth tokens, Vault documents, license status | HTTP client, OIDC client library |
| C15 | **Channel Adapter Plugin System** | Provides generic adapter interface for channel integration. Each channel implements: `connect()`, `disconnect()`, `receive()` → `InboundMessage`, `send(OutboundMessage)`. Manages adapter lifecycle, health checks, and reconnection logic. | Channel config, adapter implementations | Adapter state, normalized messages | Python ABC + adapter plugins, Node.js sidecar for Baileys |
| **C16** | **Persona Service** | Composes the final prompt with Brand Persona: merges operator's brand voice config (tone, vocabulary, do's/don'ts), few-shot examples, retrieved Vault context, and conversation history into the system prompt. When a fine-tuned LoRA/QLoRA adapter is configured, selects the adapter-backed model endpoint instead of (or in addition to) prompt-based persona. Single place where "how Desk sounds" is assembled. | Brand Persona config, few-shot examples, Vault context, conversation history | Composed system prompt, selected persona backend (prompt or LoRA adapter) | Internal module, prompt templating engine |
| **C17** | **Policy Engine (Guardrails)** | Runs as two hooks in the AI pipeline: (1) **pre-generation hook** — detects policy-triggering intents (competitor mentions, sensitive topics) and decides allow/template/redirect/escalate/inject-context; (2) **post-generation hook** — validates generated response against active policies and decides allow/rewrite/block-and-template/escalate. Reads policy config and writes every decision to audit log. Enforces topic-based response rules and disclaimers. | Inbound message (pre-hook), generated response (post-hook), ResponsePolicy config | Policy decision (allow/template/redirect/block/escalate), audit log entry | Internal module, rule engine, optional classifier |
| **C18** | **Intent/Policy Classifier** | Detection mechanism called by Policy Engine. Tiered approach for MVP: (1) cheap deterministic rules/keywords first (fast, free, transparent — perfect for competitor names and banned terms); (2) optional small local classifier or LLM-based classifier for fuzzier intents. Keeps latency and cost predictable. | Message text, classifier config | Intent label, confidence score, matched keywords | Internal module, regex/keyword engine, optional classifier model |

### 2.2 External Integrations

| Integration | Direction | Protocol | Purpose |
|---|---|---|---|
| WhatsApp Business API (Meta or BSP) | Bidirectional | HTTPS webhooks + REST | Enterprise customer channel (official) |
| **WhatsApp Baileys Bridge** | Bidirectional | WebSocket (WhatsApp Web protocol) | Quick-start customer channel (unofficial bridge) |
| Web chat widget | Bidirectional | WebSocket + HTTPS | Embedded customer channel |
| Email (IMAP/SMTP) | Bidirectional | IMAP fetch + SMTP send | Async customer channel |
| **Telegram Bot API (future)** | Bidirectional | HTTPS polling or webhooks | Optional customer channel (v1.1+) |
| **Discord API (future)** | Bidirectional | WebSocket + REST | Optional community channel (v1.1+) |
| **Slack API (future)** | Bidirectional | WebSocket + REST | Optional workspace channel (v1.1+) |
| **Signal protocol (future)** | Bidirectional | Signal protocol bridge | Optional secure channel (v1.1+) |
| ODW.ai Vault | Inbound query | REST (HTTPS) | Knowledge base retrieval |
| ODW.ai Auth | Inbound verify | OIDC/OAuth 2.0 | Single sign-on |
| ODW.ai Billing | Inbound verify | REST (HTTPS) | License validation |
| Ollama / vLLM | Outbound inference | REST (local network) | Local model inference |
| OpenAI / Anthropic API | Outbound inference | HTTPS | Frontier model inference |
| S3-compatible object storage | Bidirectional | S3 API | Media file storage, backup archival |

---

## 3. Component Interaction & Data Flow

### 3.1 Normal Operation: Inbound Customer Message → AI Response

```
Customer (WhatsApp)
    │
    ├─▶ [WhatsApp Business API] ──▶ Webhook ──▶ [C1 Channel Gateway: BusinessAPIAdapter]
    │
    └─▶ [WhatsApp Baileys Bridge] ──▶ WebSocket ──▶ [C1 Channel Gateway: BaileysAdapter]
                                                                              │
                                                                              ▼
                                                                    Normalize to InboundMessage
                                                                              │
                                                                              ▼
                                                                    [C13 Event Bus] ── publish: inbound.message ──▶
                                                                              │
                                                                              ▼
                                                                    [C2 Message Router] ── consume ──▶ resolve customer (DB lookup / cache)
                                                                              │                                load conversation context
                                                                              │                                check conversation state
                                                                              ▼
                                                                    [C3 Conversation Manager] ── append message ──▶ persist to PostgreSQL
                                                                              │
                                                                              ▼ (if AI-enabled and conversation is active)
                                                                    [C4 AI Engine] ── orchestrate pipeline ──▶
                                                                              │
                                                                              ├──▶ [C5 PII Shield] ── detect/redact PII ──▶ routing directive
                                                                              │
                                                                              ├──▶ [C17 Policy Engine] ── PRE-HOOK ──▶ detect intents via [C18 Intent/Policy Classifier]
                                                                              │         │
                                                                              │         ├── Hard rule match? → serve template/redirect/escalate → SKIP generation
                                                                              │         │                              └──▶ [C13 Event Bus] → outbound.message
                                                                              │         │
                                                                              │         └── No hard match → continue to model routing
                                                                              │
                                                                              ├──▶ [C6 Model Router] ── select model ──▶ local or frontier endpoint
                                                                              │
                                                                              ├──▶ [C16 Persona Service] ── compose prompt ──▶ [system: base + brand persona + policies]
                                                                              │         └── if LoRA adapter configured → select adapter-backed endpoint
                                                                              │
                                                                              ├──▶ [C7 Vault Client] ── retrieve knowledge ──▶ document chunks
                                                                              │         (cache hit? → Redis; miss → Vault API)
                                                                              │
                                                                              ├──▶ [C4 AI Engine] ── compose prompt + context + knowledge ──▶ LLM inference
                                                                              │         (base model or LoRA adapter per Persona Service)
                                                                              │
                                                                              ├──▶ [C4 AI Engine] ── calculate confidence score
                                                                              │
                                                                              ├──▶ [C17 Policy Engine] ── POST-HOOK ──▶ validate response against active policies
                                                                              │         │
                                                                              │         ├── Violation? → rewrite/block-and-template/escalate
                                                                              │         │
                                                                              │         └── Pass → continue to send
                                                                              │
                                                                              └──▶ [C4 AI Engine] ── confidence ≥ threshold?
                                                                                        │
                                                                                        ├── YES → format response → [C13 Event Bus] → outbound.message
                                                                                        │                              → [C1 Channel Gateway] → WhatsApp API → Customer
                                                                                        │
                                                                                        └── NO  → escalate to human → [C3 Conversation Manager] state → escalated
                                                                                                                         → [C13 Event Bus] → agent.escalation
                                                                                                                         → [C8 Agent Inbox] → notify agent
```

**Latency budget (end-to-end, P95):**
- Webhook receipt → canonical message: <50ms
- Customer resolution + context load: <100ms (cached)
- PII detection: <200ms
- Vault retrieval: <500ms (cached), <1000ms (cold)
- LLM inference (local): <3000ms
- LLM inference (frontier): <5000ms
- Confidence scoring + response formatting: <100ms
- Outbound delivery: <500ms
- **Total: <5s (local), <8s (frontier)** — matches NFR-P-01

### 3.2 Failure Scenario: Local Model Unavailable

```
[C4 AI Engine] ── attempt local inference ──▶ timeout / connection refused
    │
    ▼
[C6 Model Router] ── circuit breaker open ──▶ check fallback policy
    │
    ├── PII detected → NO frontier fallback allowed
    │       → escalate to human agent with context
    │       → log: model_unavailable, pii_present, escalated
    │
    └── No PII → frontier fallback allowed
            → route to frontier model (with PII redacted)
            → log: fallback_triggered, model=frontier
```

### 3.3 Human Takeover Flow

```
[C8 Agent Inbox] ── agent clicks "Take Over" ──▶
    │
    ▼
[C3 Conversation Manager] ── state: escalated → active (agent-assigned)
    │                        ── disable AI auto-respond for this conversation
    │                        ── persist assignment
    ▼
[C13 Event Bus] ── publish: conversation.agent_assigned ──▶
    │
    ▼
[C2 Message Router] ── on next inbound message for this conversation ──▶
    │                   route to agent queue (skip AI pipeline)
    ▼
[C8 Agent Inbox] ── display new message to assigned agent ──▶
    │
    ▼ (agent resolves)
[C3 Conversation Manager] ── state → resolved
    │                        ── re-enable AI for future conversations from this customer
```

### 3.4 Channel Adapter Plugin Architecture

```
┌─────────────────────────────────────────┐
│   Channel Adapter Plugin Interface      │
├─────────────────────────────────────────┤
│ + connect(config) → void                │
│ + disconnect() → void                   │
│ + receive() → InboundMessage            │
│ + send(OutboundMessage) → DeliveryResult│
│ + healthCheck() → Status                │
│ + onDisconnect(callback)                │
│ + reconnect() → void                    │
└─────────────────────────────────────────┘
              ▲
              │ implements
    ┌─────────┴──────────┬──────────────┬────────────┐
    │                    │              │            │
WhatsAppBA      WhatsAppBaileys    WebChat       Email
(Business API)  (Bridge)          (WebSocket)   (IMAP/SMTP)
```

**Adapter Lifecycle:**
1. Admin configures adapter via Admin Dashboard (provides credentials, settings)
2. `ChannelAdapterManager` instantiates adapter with config
3. Adapter calls `connect()` — establishes connection to external channel
4. Adapter starts `receive()` loop — yields `InboundMessage` events
5. On connection loss, adapter calls `reconnect()` with exponential backoff
6. Admin can disable adapter via Dashboard — calls `disconnect()`

**Baileys Bridge Architecture:**
- Runs as Node.js sidecar container (`desk-baileys-bridge`)
- Communicates with Python Channel Gateway via internal REST/WebSocket
- Stores WhatsApp session state in Redis (auth credentials, chat history)
- QR code generation endpoint for initial pairing
- Auto-reconnection logic with exponential backoff
- Session persistence across container restarts (Redis-backed)
- Session expiry handling (30-day TTL, admin notification before expiry)

**WhatsApp Baileys Bridge Flow:**

```
[Operator scans QR code] ──▶ [Admin Dashboard] ──▶ [C15 Channel Adapter Plugin System]
    │
    ▼
[C15] ── POST /api/v1/channels/whatsapp-baileys/pair ──▶ [Node.js Baileys Sidecar]
    │
    ▼
[Node.js Sidecar] ── generate QR code ──▶ return to Admin Dashboard
    │
    ▼ (operator scans QR with WhatsApp mobile app)
[Node.js Sidecar] ── WhatsApp Web protocol handshake ──▶ session established
    │
    ▼
[Node.js Sidecar] ── store session in Redis ──▶ start WebSocket listener
    │
    ▼ (customer sends message)
[Node.js Sidecar] ── receive via WhatsApp Web protocol ──▶ normalize to InboundMessage
    │
    ▼
[Node.js Sidecar] ── POST to Python Channel Gateway ──▶ [C1 Channel Gateway]
    │
    ▼
[C1] ── publish to [C13 Event Bus] ──▶ [C2 Message Router] ──▶ ...
```

### 3.5 Async vs Sync Boundaries

| Boundary | Pattern | Rationale |
|---|---|---|
| Channel Gateway → Message Router | Async (event bus) | Decouples webhook response time from processing; webhook must return <5s to WhatsApp |
| Message Router → AI Engine | Async (processing queue) | AI inference is slow (seconds); must not block message ingestion |
| AI Engine → Channel Gateway (outbound) | Async (event bus) | Outbound delivery is independent of inference; enables retry without re-inference |
| Agent Inbox ↔ Conversation Manager | Sync (REST) for reads, Async (WebSocket) for real-time updates | Agents need immediate reads; real-time updates pushed via WebSocket |
| Admin Dashboard ↔ Configuration | Sync (REST) | Low-frequency admin operations; immediate consistency required |
| Vault Client → Vault API | Sync with cache | Vault query is on critical path; cache reduces latency for repeated queries |
| Policy Engine (pre-hook) → Intent Classifier | Sync (in-process) | Pre-hook must be fast (<20ms for keyword rules); classifier runs in same process |
| Persona Service → Model Router | Sync (in-process) | Prompt composition is on critical path; must complete before inference |

### 3.6 Fine-Tuning Architecture Stance

**Desk does not perform fine-tuning inside the product for MVP/v1.1. Desk *consumes* fine-tuned artifacts (LoRA/QLoRA adapters) produced by an external pipeline.**

**Rationale:**
- Training is a heavyweight, GPU-bound, occasional batch workload that doesn't belong in the real-time serving path
- Keeps the core deployment lightweight and avoids forcing every operator to provision training hardware
- Operators can use external fine-tuning tools (Hugging Face Transformers, Axolotl, LLaMA-Factory) with their preferred infrastructure
- Separation of concerns: serving (Desk) vs training (external pipeline)

**Serving Layer Support:**
- **vLLM:** Supports LoRA adapters natively via `--enable-lora` flag and per-request LoRA serving; Persona Service specifies adapter ID in inference request
- **Ollama:** Requires adapter merge into Modelfile workflow; document the merge process for operators
- **Startup Validation:** Desk verifies `adapter_base_model` matches the configured local model; on mismatch or load failure, log error and fall back to prompt-based persona (per FR-BP-07/US-BP-02 AC)

**Adapter Storage:**
- Adapters stored as directory/artifact (`adapter_config.json` + adapter weights, PEFT-format)
- Referenced by `adapter_uri` (local filesystem path or S3-compatible object store URI, consistent with NFR-S-04)
- Audit log records which adapter version served each response (for traceability)

### 3.7 Sovereignty & Compliance for Fine-Tuning

**Critical Constraint: Fine-tuning data must be synthetic or rigorously anonymized.**

Training on raw transcripts bakes PII into model weights, which is incompatible with:
- **GDPR right-to-erasure (FR-DS-05):** Cannot delete PII from trained model weights without retraining
- **Sovereignty promise:** PII in weights could leak to frontier models if adapter is shared or compromised
- **Audit requirements:** Cannot trace which PII influenced which weights

**Requirements for External Fine-Tuning Pipeline:**
1. **Data Anonymization:** All PII must be removed or replaced with synthetic equivalents before training
2. **Synthetic Data Preferred:** Generate synthetic training examples that reflect brand voice without using real customer transcripts
3. **Audit Trail:** External pipeline must document data sources and anonymization steps
4. **Adapter Versioning:** Each adapter version must be traceable to its training data provenance

**Risk Mitigation (add to §11.1):**
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| PII baked into fine-tuned weights | Medium | Critical | Enforce anonymized/synthetic training data only; require external pipeline to certify data provenance; adapter versioning in audit log; never train on raw transcripts |

---

## 4. API & Service Boundaries

### 4.1 External API Surface

| API | Protocol | Consumers | Authentication |
|---|---|---|---|
| `/api/v1/webhooks/whatsapp` | REST (POST) | Meta / BSP | HMAC signature verification |
| `/api/v1/webhooks/chat` | WebSocket | Web chat widget | Session token (anonymous or authenticated) |
| `/api/v1/admin/*` | REST | Admin Dashboard (React) | OAuth 2.0 / OIDC (Admin role) |
| `/api/v1/agent/*` | REST + WebSocket | Agent Inbox (React) | OAuth 2.0 / OIDC (Agent role) |
| `/api/v1/compliance/*` | REST | Admin Dashboard | OAuth 2.0 / OIDC (Admin role) |
| `/health` | REST (GET) | Load balancer, Kubernetes probes | None |
| `/metrics` | REST (GET) | Prometheus | None (network-restricted) |

### 4.2 Internal Service Boundaries

| Module Boundary | Communication | Contract |
|---|---|---|
| Channel Gateway ↔ Message Router | Event bus (Redis Streams) | `InboundMessage` schema: `{channel, channel_conversation_id, sender_identifier, content, media_urls[], metadata, timestamp}` |
| Message Router ↔ AI Engine | Event bus (processing queue) | `ProcessRequest` schema: `{conversation_id, customer_id, message, context[], routing_directive}` |
| AI Engine ↔ Channel Gateway | Event bus (outbound queue) | `OutboundMessage` schema: `{channel, channel_conversation_id, content, media_urls[], metadata}` |
| AI Engine ↔ PII Shield | Synchronous function call (same process) | Input: raw text. Output: `{pii_detected: bool, pii_types[], redacted_text}` |
| AI Engine ↔ Model Router | Synchronous function call | Input: `{pii_directive, complexity_score}`. Output: `{model_endpoint, model_name, fallback_chain[]}` |
| AI Engine ↔ Vault Client | Synchronous HTTP (cached) | Input: `{query, collection_id, top_k}`. Output: `{documents[{content, score, source_id}]}` |
| All modules → Compliance Engine | Event bus (audit events) | `AuditEvent` schema: `{timestamp, event_type, actor, resource, action, details}` |

### 4.3 Service Decoupling Opportunities

The event bus boundary between Channel Gateway and AI Engine is the primary decoupling point. This enables:
- Independent scaling of ingestion (channel adapters) vs. processing (AI workers)
- Zero-loss message buffering during AI model outages
- Future extraction of AI Engine into a separate service without changing channel adapters

The Vault Client is isolated behind an interface, allowing swap between Vault API, direct vector DB query, or mock (for testing).

---

## 5. Data Architecture

### 5.1 Storage Strategy

| Data Category | Store | Rationale |
|---|---|---|
| Conversations, messages, customers, agents, configuration | PostgreSQL 16+ | ACID transactions required for audit integrity; JSONB handles flexible metadata; mature ecosystem for self-hosted deployments |
| Session context, customer lookup cache, Vault query cache | Redis 7+ | Sub-millisecond reads for hot-path data; TTL-based expiry prevents stale context |
| Message queues (inbound, outbound, processing) | Redis Streams (default) or NATS JetStream (K8s) | Lightweight, already required for caching; NATS selected for K8s for better persistence guarantees |
| Media files (images, documents, audio) | S3-compatible object storage (MinIO for self-hosted) | Separates large binary data from relational store; enables independent scaling and backup |
| Vector embeddings (if Vault co-deployed) | Managed by Vault (pgvector or dedicated vector DB) | Desk does not own embedding storage; queries Vault's retrieval API |

### 5.2 Data Ownership

| Module | Owned Tables/Data | Access by Others |
|---|---|---|
| Conversation Manager | `conversations`, `messages`, `conversation_state` | Read-only by Agent Inbox, Compliance Engine |
| Message Router | `customers`, `channel_identifiers` | Read-only by AI Engine (for context), Compliance Engine |
| AI Engine | `ai_configurations`, `ai_decision_logs` | Read-only by Admin Dashboard, Compliance Engine |
| Compliance Engine | `audit_logs`, `data_deletion_records`, `compliance_reports` | Read-only by Admin Dashboard |
| License Manager | `license_state`, `feature_gates` | Read-only by all modules (gate checks) |

### 5.3 Consistency Model

- **Strong consistency** for: conversation state transitions, message persistence, audit log writes (PostgreSQL transactions)
- **Eventual consistency** for: cache invalidation (Redis TTL), cross-module event propagation (event bus delivery), Vault query cache refresh
- **At-least-once delivery** for event bus messages (idempotent consumers required)

### 5.4 Indexing Strategy

- `conversations`: composite index on `(customer_id, status, updated_at)` for inbox queries; index on `channel_conversation_id` for webhook deduplication
- `messages`: index on `(conversation_id, created_at)` for timeline retrieval; partial index on `sender_type = 'ai'` for AI review queries
- `customers`: index on `channel_identifiers` (GIN index on JSONB) for cross-channel customer resolution
- `audit_logs`: index on `(timestamp, event_type)` for compliance report queries; index on `(resource_type, resource_id)` for per-customer audit exports

### 5.5 Data Partitioning

At MVP scale (1,000 concurrent conversations), partitioning is not required. The architecture supports future partitioning by:
- `conversations` partitioned by `created_at` (monthly ranges) for archival
- `audit_logs` partitioned by `timestamp` (quarterly ranges) for retention management
- `messages` inherits conversation partitioning via foreign key

---

## 6. Scalability & Performance Design

### 6.1 Scaling Model

| Component | Scaling Strategy | Constraint |
|---|---|---|
| Channel Gateway | Horizontal (stateless). Multiple replicas behind load balancer. | Webhook ordering per conversation must be preserved (handled by Redis Streams consumer groups with per-conversation hashing) |
| Message Router | Horizontal (stateless). Scales with conversation volume. | Customer resolution requires Redis cache; cache coherence across replicas via Redis Cluster |
| AI Engine | Horizontal (stateless workers). Each worker consumes from processing queue. | Inference latency is the bottleneck; scale workers to match throughput target (100 msg/s) |
| Agent Inbox | Horizontal (stateless API + WebSocket). Sticky sessions for WebSocket connections. | WebSocket connection limit per node (~10K); scale nodes for connection count |
| PostgreSQL | Vertical scaling (primary); read replicas for inbox queries. Connection pooling via PgBouncer. | Write throughput limited by single primary; sufficient at target scale |
| Redis | Redis Cluster for horizontal cache scaling. Single-node sufficient for MVP. | Memory-bound; monitor cache hit rates and eviction |

### 6.2 Caching Layers

| Cache | Key Pattern | TTL | Hit Rate Target |
|---|---|---|---|
| Customer lookup | `customer:{channel}:{identifier_hash}` | 5 min | >80% (repeat customers dominate) |
| Vault query result | `vault:{collection}:{query_hash}` | 10 min | >40% (common questions repeat) |
| Conversation context | `context:{conversation_id}` | 30 min | >95% (active conversations) |
| AI configuration | `ai_config:{deployment_id}` | 60 min | >99% (rarely changes) |

### 6.3 Load Balancing

- **Inbound webhooks:** Round-robin across Channel Gateway replicas (stateless; any replica can process any webhook)
- **Agent WebSocket:** Sticky sessions (IP hash or cookie-based) to maintain persistent connections
- **AI processing workers:** Consumer group load balancing via Redis Streams (message assigned to one consumer; not broadcast)

### 6.4 Rate Limiting

- **Inbound webhook rate limit:** Configurable per deployment (default: 1000 req/min per channel); protects against webhook floods
- **Frontier model API rate limit:** Token bucket per provider (respecting provider rate limits); queued requests wait or fallback to local model
- **Admin/Agent API rate limit:** 100 req/min per user; prevents abuse of export/compliance endpoints

### 6.5 Bottleneck Mitigation

| Bottleneck | Mitigation |
|---|---|
| LLM inference latency | Parallel processing (multiple AI workers); local model preferred for latency-sensitive queries; streaming responses where channel supports it |
| Vault query latency (cold) | Redis cache (10-min TTL); prefetch common queries during low-traffic periods |
| Database write throughput | Batch message inserts (buffer 100ms window); async audit log writes (event bus → dedicated writer) |
| WebSocket connection limit | Horizontal scaling of Agent Inbox nodes; connection migration on node drain |

---

## 7. Reliability & Fault Tolerance

### 7.1 Failover Strategies

| Component | Failure Mode | Failover Strategy |
|---|---|---|
| PostgreSQL primary | Node failure | Streaming replication to standby; automated failover via Patroni or cloud-managed HA |
| Redis | Node failure | Redis Sentinel (single-node) or Redis Cluster (multi-node); cache misses fall through to PostgreSQL |
| AI Engine worker | Process crash | Consumer group ensures unacknowledged messages are redelivered to another worker |
| Channel Gateway | Node failure | Stateless; load balancer routes to healthy replicas; webhook retries from Meta/BSP cover transient failures |
| Vault API | Unavailable | Cached results served until TTL expires; degradation mode: AI responds with disclaimer ("I cannot access our knowledge base right now") or escalates to human |
| Frontier model API | Unavailable / rate-limited | Circuit breaker opens after 3 failures; fallback to local model (if policy allows) or escalate to human |
| Local model (Ollama/vLLM) | Unavailable / OOM | Circuit breaker opens; fallback to frontier model (if no PII) or escalate to human |

### 7.2 Retry Mechanisms

| Operation | Retry Policy | Dead-Letter Behavior |
|---|---|---|
| Inbound message processing | 3 retries, exponential backoff (1s, 5s, 30s) | Message moved to dead-letter queue; admin notified; conversation flagged for manual review |
| Outbound message delivery | 3 retries, exponential backoff (1s, 5s, 30s) | Message held in DLQ; channel-specific retry (WhatsApp has its own retry semantics); admin notified after 1 hour |
| Vault API query | 2 retries, 500ms backoff | Return empty result set; AI proceeds without knowledge grounding (with disclaimer) or escalates |
| Frontier model API call | 2 retries, 1s backoff | Trigger circuit breaker; fallback to local model or escalate |

### 7.3 Circuit Breakers

Implemented for all external dependencies (Vault API, OpenAI, Anthropic, Ollama):
- **Closed** (normal): requests pass through
- **Open** (failure threshold exceeded, e.g., 5 failures in 60s): requests immediately fail over to fallback
- **Half-open** (after cooldown, e.g., 30s): probe with single request; close on success, re-open on failure

### 7.4 Graceful Degradation

| Scenario | Degraded Behavior |
|---|---|
| AI completely unavailable | All inbound messages queued; human agents notified; customer receives auto-reply ("Our team will respond shortly") |
| Vault unavailable | AI responds without knowledge grounding (general knowledge with disclaimer) or escalates all queries to human |
| Redis unavailable | Direct database queries (slower but functional); message queue falls back to PostgreSQL-backed queue |
| WhatsApp API unavailable | Messages queued for retry; web chat and email channels continue operating |

### 7.5 Single Points of Failure & Mitigations

| SPOF | Mitigation |
|---|---|
| PostgreSQL primary | Streaming replication + automated failover (Patroni); daily backups + continuous WAL archiving (RPO <5 min) |
| Redis (cache + queue) | Redis Sentinel for HA; application falls back to direct DB queries if cache unavailable |
| Event bus (Redis Streams) | Same Redis HA; if fully unavailable, components fall back to synchronous processing (degraded throughput, no data loss) |

---

## 8. Security Architecture

### 8.1 Authentication & Authorization

| Surface | Method | Details |
|---|---|---|
| Admin / Agent login | OAuth 2.0 / OIDC via ODW.ai Auth | SSO across suite; JWT tokens with 1-hour expiry; refresh tokens with 7-day expiry |
| API programmatic access | API keys | Scoped to specific operations; rotated via admin dashboard; stored hashed |
| Web chat widget | Anonymous session token | Generated on widget load; linked to conversation; no PII required |
| WhatsApp webhook | HMAC-SHA256 signature | Meta-provided secret; signature verified on every webhook payload |
| Inter-service (suite) | mTLS or shared JWT validation | Services validate tokens issued by ODW.ai Auth; no separate credentials |

### 8.2 Authorization Model (RBAC)

| Role | Permissions |
|---|---|
| **Admin** | Full access: configuration, license, compliance, user management, all data |
| **Agent** | Inbox access: view assigned conversations, send responses, take over/resolve, provide AI feedback |
| **Read-Only** | View conversations and metrics; no write access |

Role assignments managed via ODW.ai Auth; Desk consumes role claims from JWT.

### 8.3 Data Protection

| Layer | Mechanism |
|---|---|
| Encryption at rest (database) | AES-256 via PostgreSQL TDE or filesystem-level encryption (LUKS) |
| Encryption at rest (PII fields) | Field-level encryption using application-managed keys (AES-256-GCM); keys stored in secrets manager |
| Encryption at rest (object storage) | S3 server-side encryption (SSE-S3 or SSE-KMS) |
| Encryption in transit | TLS 1.3 for all external connections; mTLS for inter-service communication in Kubernetes |
| Key management | Environment variables (Docker Compose) or secrets manager (HashiCorp Vault, AWS Secrets Manager) for Kubernetes |

### 8.4 PII Protection Architecture

```
Inbound message
    │
    ▼
[PII Shield] ── NER detection (Presidio / custom model) ──▶
    │
    ├── PII detected:
    │       ├── Store original (encrypted) in PostgreSQL
    │       ├── Generate redacted version
    │       ├── Routing directive: LOCAL_MODEL_ONLY (unless admin override)
    │       └── If admin allows frontier with redaction: send redacted version only
    │
    └── No PII detected:
            └── Routing directive: follow complexity-based policy
```

PII types detected: names, phone numbers, email addresses, physical addresses, dates of birth, health identifiers, financial account numbers, government IDs.

### 8.5 API Security

- All external APIs behind reverse proxy (Traefik / nginx) with TLS termination
- Rate limiting at proxy layer (per-IP and per-API-key)
- Input validation and sanitization on all endpoints (prevent SQL injection, XSS, command injection)
- CORS configured to allow only operator's domains
- Webhook endpoints verify payload signature before processing
- API versioning (`/api/v1/`) with backward compatibility for 2 major versions

### 8.6 Threat Considerations

| Threat | Mitigation |
|---|---|
| Prompt injection via customer messages | Input sanitization; system prompt isolation; output validation; confidence scoring catches anomalous responses |
| Webhook spoofing | HMAC signature verification; IP allowlisting for Meta webhooks |
| Data exfiltration via AI responses | Output filtering; PII detection on outbound messages; audit logging of all AI outputs |
| Unauthorized data access | RBAC enforcement; audit logging of all data access; field-level encryption for PII |
| Supply chain attack (compromised dependency) | Locked dependencies; checksum verification; automated vulnerability scanning in CI; minimal base images |
| Credential leakage in logs | Structured logging with PII filter; secrets never logged; log review in CI |

---

## 9. Infrastructure & Deployment Architecture

### 9.1 Deployment Models

| Model | Target User | Components |
|---|---|---|
| **Docker Compose (single-node)** | SMB operators, developer evaluation | All services in one `docker-compose.yml`; PostgreSQL, Redis, MinIO, Ollama as sidecar containers; Traefik for TLS |
| **Kubernetes Helm chart** | Production deployments, scaled operations | Separate Deployments per component; StatefulSets for PostgreSQL/Redis; HPA for horizontal scaling; Ingress for TLS |

### 9.2 Container Inventory

| Container | Image | Resource Profile (MVP) |
|---|---|---|
| `desk-api` | FastAPI application (all modules) | 2 CPU, 4GB RAM (×2 replicas for HA) |
| `desk-worker-ai` | AI processing workers | 2 CPU, 4GB RAM (×3 replicas; GPU optional for local models) |
| `desk-worker-outbound` | Outbound message delivery workers | 1 CPU, 1GB RAM (×2 replicas) |
| `desk-scheduler` | Scheduled jobs (retention, reports, cache warmup) | 0.5 CPU, 512MB RAM (×1 replica) |
| `desk-web` | React frontend (nginx static) | 0.5 CPU, 256MB RAM (×2 replicas) |
| `postgres` | PostgreSQL 16 | 2 CPU, 8GB RAM, 100GB SSD |
| `redis` | Redis 7 | 1 CPU, 2GB RAM |
| `minio` | MinIO (S3-compatible) | 1 CPU, 1GB RAM, storage-sized |
| `ollama` (optional) | Ollama + model | 4 CPU, 16GB RAM, GPU if available |
| `traefik` | Traefik reverse proxy | 0.5 CPU, 256MB RAM |

### 9.3 Environments

| Environment | Purpose | Infrastructure |
|---|---|---|
| `dev` | Local development | Docker Compose on developer machine; hot-reload enabled |
| `staging` | Pre-production validation | Single-node VM or small K8s cluster; mirrors production config |
| `production` | Operator deployments | Customer-managed infrastructure; Helm chart or Docker Compose |

### 9.4 CI/CD Approach

```
Source (GitHub)
    │
    ▼
[CI Pipeline] ── lint, type-check, unit tests ──▶
    │            ── integration tests (docker-compose) ──▶
    │            ── security scan (dependency audit, SAST) ──▶
    │            ── build container images ──▶
    │            ── push to container registry ──▶
    ▼
[CD Pipeline] ── deploy to staging ──▶
    │             ── smoke tests ──▶
    │             ── manual approval ──▶
    │             ── deploy to production (rolling update) ──▶
    ▼
[Post-deploy] ── health checks ──▶
    │             ── canary metrics validation ──▶
    │             ── full rollout or automatic rollback
```

- Container images tagged with semantic version + git SHA
- Database migrations run automatically on startup (Alembic); backward-compatible migrations only
- Zero-downtime deployments via rolling updates (Kubernetes) or blue-green (Docker Compose with Traefik)

---

## 10. Observability & Operations

### 10.1 Logging Strategy

- **Structured JSON logging** across all components (via Python `structlog`)
- **Log levels:** DEBUG (dev), INFO (production default), configurable per-component
- **PII filter:** All log entries pass through a PII redaction filter before output
- **Correlation IDs:** Every inbound message receives a unique `trace_id` propagated across all components and logged with every related entry
- **Log aggregation:** Operators configure their own stack (ELK, Loki, CloudWatch); Desk emits to stdout/stderr

### 10.2 Metrics Collection

Prometheus-compatible `/metrics` endpoint exposing:

| Metric Category | Examples |
|---|---|
| Inbound throughput | `desk_inbound_messages_total{channel=...}`, `desk_inbound_message_duration_seconds` |
| AI processing | `desk_ai_inference_duration_seconds{model=...}`, `desk_ai_confidence_score{model=...}`, `desk_ai_escalations_total` |
| Routing | `desk_routing_decisions_total{target=..., reason=...}`, `desk_pii_detected_total` |
| Channel delivery | `desk_outbound_messages_total{channel=..., status=...}`, `desk_outbound_delivery_duration_seconds` |
| Cache | `desk_cache_hits_total{cache=...}`, `desk_cache_misses_total{cache=...}` |
| Queue depth | `desk_queue_depth{queue=...}`, `desk_dead_letter_count{queue=...}` |
| System | `desk_active_conversations`, `desk_connected_agents`, `desk_vault_query_duration_seconds` |

### 10.3 Distributed Tracing

- **OpenTelemetry SDK** integrated in all Python services
- **Trace propagation:** `trace_id` from inbound webhook propagated through event bus, AI pipeline, and outbound delivery
- **Export:** OTLP-compatible; operators configure their own backend (Jaeger, Tempo, Grafana Cloud)
- **Span coverage:** webhook receipt → message routing → PII detection → Vault query → model inference → outbound delivery

### 10.4 Alerting & Monitoring

Pre-configured Grafana dashboards and alert rules (operators import via Helm values or Docker Compose):

| Alert | Condition | Severity |
|---|---|---|
| AI inference latency high | P95 > 10s for 5 minutes | Warning |
| AI escalation rate spike | Escalations > 50% of total for 10 minutes | Warning |
| Dead letter queue growing | DLQ depth > 100 for 5 minutes | Critical |
| WhatsApp webhook failures | >5% failure rate for 5 minutes | Critical |
| Database connection pool exhausted | Active connections > 90% of pool | Critical |
| Disk space low | >85% utilization on data volumes | Warning |
| License expiry | <14 days remaining | Info |
| Vault API unreachable | Circuit breaker open for >5 minutes | Warning |

---

## 11. Cost & Resource Considerations

### 11.1 Major Cost Drivers

| Driver | Cost Profile | Optimization |
|---|---|---|
| **LLM inference (frontier)** | $0.01–$0.10 per query; dominates variable cost at scale | Route 60%+ queries to local model; cache Vault results to reduce token count; use smaller frontier models (GPT-4o-mini) for simple queries |
| **LLM inference (local)** | Electricity + GPU amortization; fixed cost | Right-size model (8B for simple queries, 70B for complex); batch requests; use CPU-only for non-latency-sensitive workloads |
| **Compute (application)** | 4–8 CPU cores, 16–32GB RAM for MVP deployment | Stateless workers scale on demand; idle workers scale to zero in K8s |
| **Database** | PostgreSQL: 2 CPU, 8GB RAM, 100GB SSD | Read replicas for inbox queries; archive old conversations to cold storage |
| **Object storage** | Media files; grows linearly with usage | Lifecycle policies to move old media to cold storage (S3 Glacier) |
| **WhatsApp Business API** | Per-conversation pricing (Meta); varies by country | Optimize conversation length; use templates for common responses (lower cost) |

### 11.2 Cost Optimization Strategies

1. **Intelligent routing:** PII and complexity-based routing ensures expensive frontier models are used only when necessary. Target: <40% of queries reach frontier models.
2. **Response caching:** Identical or near-identical questions served from Vault query cache without re-inference.
3. **Token optimization:** System prompts compressed; conversation context truncated to relevant turns; Vault chunks selected for information density.
4. **Batch processing:** Audit log writes, analytics aggregation, and compliance report generation batched to reduce database I/O.
5. **Model selection guidance:** Operators guided to start with 8B local models; upgrade to larger models only if confidence metrics indicate quality gaps.

### 11.3 Resource Sizing (MVP Deployment)

| Deployment Size | Conversations/Day | Infrastructure | Estimated Monthly Cost (excl. frontier API) |
|---|---|---|---|
| Small (evaluation) | <100 | 4 CPU, 16GB RAM, 50GB storage | $50–80 (cloud VM) |
| Medium (production SMB) | 100–1,000 | 8 CPU, 32GB RAM, 200GB storage | $150–300 |
| Large (scaled) | 1,000–10,000 | 16+ CPU, 64GB+ RAM, K8s cluster | $500–1,500 |

Frontier API costs additional: $50–500/month depending on routing policy and volume.

---

## 12. Trade-offs & Design Decisions

### 12.1 Modular Monolith vs Microservices

**Options considered:** Full microservices, modular monolith, serverless
**Chosen:** Modular monolith with event-driven internal boundaries

| Pros | Cons |
|---|---|
| Single deployment simplifies self-hosted operations | Cannot scale modules independently until extracted |
| Faster development iteration (no network boundaries) | Requires discipline to maintain module boundaries |
| Lower operational overhead for operators | Risk of coupling creep without clear ownership |
| Event bus preserves extraction path for v2 | Event bus adds complexity vs direct calls |

### 12.2 Redis Streams vs Dedicated Message Queue (RabbitMQ/Kafka)

**Options considered:** RabbitMQ, Kafka, Redis Streams, NATS JetStream
**Chosen:** Redis Streams (default), NATS JetStream (Kubernetes)

| Pros | Cons |
|---|---|
| Redis already required for caching; no additional infrastructure | Redis Streams less battle-tested than RabbitMQ for complex routing |
| Simpler deployment (one fewer container) | Limited consumer group features vs RabbitMQ |
| Sub-millisecond latency for queue operations | Not suitable for long-term message retention |
| NATS selected for K8s provides persistence and clustering | Two queue technologies to maintain |

### 12.3 PostgreSQL vs Multi-Database (Postgres + MongoDB + Vector DB)

**Options considered:** PostgreSQL only, PostgreSQL + MongoDB, PostgreSQL + dedicated vector DB
**Chosen:** PostgreSQL only (for Desk's own data); Vault manages its own vector store

| Pros | Cons |
|---|---|
| Single database simplifies backup, replication, compliance | JSONB less flexible than document DB for highly nested data |
| Operators manage one database engine | Cannot use specialized vector search for Desk's own embeddings |
| ACID transactions for audit integrity | Write throughput ceiling on single primary |
| pgvector available if Desk ever needs local embeddings | — |

### 12.4 Synchronous Vault Query vs Async Prefetch

**Options considered:** Synchronous query on critical path, async prefetch + cache, hybrid
**Chosen:** Synchronous query with Redis cache (hybrid)

| Pros | Cons |
|---|---|
| Always fresh results (cache TTL bounds staleness) | Adds 50–500ms to inference latency |
| Simple implementation; no prefetch scheduling | Vault outage directly impacts AI quality |
| Cache absorbs repeated-question load | Cold cache (after restart) causes latency spike |

### 12.5 Open-Core (AGPL-3.0) vs Fully Proprietary vs Fully Open

**Options considered:** AGPL-3.0 open-core, fully proprietary, fully open-source (MIT/Apache)
**Chosen:** AGPL-3.0 open-core (free: chatbot + web/email; paid: WhatsApp connector, multi-agent, compliance)

| Pros | Cons |
|---|---|
| AGPL ensures derivative works remain open | Limits enterprise adoption (some legal teams block AGPL) |
| Free tier drives adoption and community | Paid features must be clearly valuable to justify cost |
| Commercial license available for AGPL-incompatible companies | Dual-license management overhead |

### 12.6 WhatsApp-First vs Channel-Agnostic

**Options considered:** Channel-agnostic abstraction from day one, WhatsApp-first with adapters for others
**Chosen:** WhatsApp-first; channel abstraction via adapter pattern but WhatsApp shapes the core data model

| Pros | Cons |
|---|---|
| Optimized for WhatsApp's constraints (24h windows, templates, media limits) | Adding new channels requires adapter work |
| Better UX for primary channel (buttons, lists, interactive messages) | Data model carries WhatsApp-specific fields that other channels don't use |
| Differentiates from competitors who bolt WhatsApp on | — |

---

## 13. Risks & Mitigations

### 13.1 Technical Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **WhatsApp Business API breaking changes** | Medium | High | Channel adapter abstraction; support multiple BSPs; webhook version pinning; monitoring for API deprecation notices |
| **Local model quality insufficient for 60% resolution target** | High | Medium | Clear model-selection guidance; hybrid routing; confidence-based escalation ensures human fallback; operators can fine-tune externally |
| **Vault API instability across versions** | Medium | High | Version-pinned Vault client; compatibility matrix tested in CI; graceful degradation (cache, disclaimer) when Vault unavailable |
| **Event bus message loss or ordering violation** | Low | High | Redis Streams consumer groups with explicit acknowledgment; idempotent consumers; per-conversation ordering via partition key |
| **PII leak to frontier model** | Low | Critical | Defense in depth: PII detection → routing policy → redaction → audit log; automated regression tests for PII redaction; zero-tolerance alerting |
| **PostgreSQL single-primary write bottleneck at scale** | Medium | Medium | Read replicas for inbox queries; batch inserts; archive old data; partitioning path documented for v2 |
| **Open-source dependency vulnerability** | High | High | Automated scanning (Dependabot/Trivy); locked versions; rapid patch release process; minimal base images |

### 13.2 Operational Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **Operator misconfiguration exposes data** | Medium | Critical | Setup wizard validates configuration; security audit endpoint; documentation with security checklist; default-secure configuration |
| **Backup failure goes undetected** | Low | Critical | Automated backup verification (test restore weekly); alerting on backup failures; backup status visible in admin dashboard |
| **Upgrade breaks running deployment** | Medium | High | Pre-upgrade automated backup; database migration rollback support; blue-green deployment support; upgrade tested in staging first |

---

## 14. Assumptions & Constraints

### 14.1 Assumptions

| # | Assumption | Validation Approach |
|---|---|---|
| A1 | Operators can deploy and maintain Docker/Kubernetes infrastructure | Target persona validation (Maria has IT team; Raj is technical); comprehensive docs reduce barrier |
| A2 | WhatsApp Business API access is obtainable by target customers | Multiple BSPs available; Meta's cloud API lowers barrier; paid tier includes BSP integration |
| A3 | Local models (8B–70B) achieve ≥60% resolution rate when grounded in knowledge base | Benchmarking during development; confidence-based escalation handles gaps |
| A4 | Vault API remains stable across Desk release cycles | Version-pinned integration; compatibility testing in CI; Vault team committed to semver |
| A5 | Target scale is 1,000 concurrent conversations per deployment (not cross-deployment) | Aligns with SMB target market (10–500 employees); enterprise scale deferred to v2 |
| A6 | Operators run deployment in a single region (no cross-region replication required) | Data-residency requirements satisfied by single-region deployment; operators choose region |
| A7 | PostgreSQL + Redis is sufficient infrastructure for MVP (no Kafka, no Elasticsearch) | Target scale validates this; scaling path documented for v2 |
| A8 | OpenAI and Anthropic APIs remain available and reasonably priced | Multiple providers available; local model as fallback; cost optimization via routing |

### 14.2 Constraints

| # | Constraint | Impact | Mitigation |
|---|---|---|---|
| C1 | 6-month MVP timeline with 5–7 engineers | Scope must be tightly managed; no feature creep | Strict MVP scope (PRD §3.1); paid-tier features deferred to v1.1 |
| C2 | WhatsApp 24-hour conversation window and template requirements | Limits outbound messaging flexibility; requires template pre-approval | Template management in admin dashboard; session-window tracking in Conversation Manager |
| C3 | Self-hosted only (no managed SaaS offering) | Limits addressable market to infrastructure-capable customers | Comprehensive docs; paid onboarding service; community support |
| C4 | AGPL-3.0 licensing | Some enterprises cannot adopt AGPL; limits partnership options | Commercial license available; clear licensing documentation |
| C5 | Vault dependency (shared API contract) | Vault changes may break Desk; Vault team has independent roadmap | Version-pinned client; compatibility matrix; mock Vault for isolated testing |
| C6 | Regulatory compliance requirements vary by jurisdiction | Cannot pre-certify for all regulations; compliance is operator responsibility | Provide tools (export, deletion, audit log) that enable compliance; documentation maps features to regulation requirements |
| C7 | Local model hardware requirements (GPU for larger models) | Operators without GPU limited to smaller models (lower quality) | CPU-optimized models (GGUF quantized); clear hardware guidance; frontier fallback for complex queries |

---

## 15. Future Evolution & Extensibility

### 15.1 Planned Extensions (v1.1 – v2.0)

| Extension | Architecture Impact | Extension Point |
|---|---|---|
| **Multi-agent routing** (different AI personas per topic) | Add Agent Persona configuration; Model Router selects persona-specific prompts and models | AI Engine module; new `agent_personas` table |
| **Telegram channel** | New channel adapter implementing same `InboundMessage`/`OutboundMessage` contract | Channel Gateway; new adapter module |
| **Generative actions** (execute transactions via API) | Add Action Executor module; tool-use framework in AI Engine; operator-defined action schemas | AI Engine; new module with sandboxed execution |
| **Multi-language support** | L10n framework for UI; multi-language knowledge base indexing in Vault; language detection in PII Shield | Vault Client; PII Shield; frontend i18n |
| **Advanced compliance** (automated retention, compliance reports) | Compliance Engine extended with policy engine; scheduled jobs for automated redaction | Compliance Engine; new policy configuration |
| **Unified admin dashboard integration** | Embed Desk admin views in ODW.ai suite dashboard; shared navigation and theming | Admin Dashboard Service; iframe or micro-frontend integration |
| **White-labeling for agencies** | Multi-tenant data isolation; per-tenant branding; agency admin role | Data model (tenant_id on all tables); License Manager |

### 15.2 Scaling Evolution Path

| Scale Trigger | Architecture Change |
|---|---|
| >1,000 concurrent conversations per deployment | Extract AI Engine into separate service; dedicated GPU nodes; independent scaling |
| >10,000 concurrent conversations | Extract Channel Gateway into separate service; dedicated webhook infrastructure |
| Multi-region deployment | Add region-aware routing; cross-region replication for configuration; per-region data isolation |
| >50,000 conversations/day | Introduce Kafka for event bus (durability, replay); partition PostgreSQL by time; add Elasticsearch for conversation search |
| Enterprise multi-tenancy | Add tenant isolation layer; per-tenant resource quotas; dedicated tenant infrastructure option |

### 15.3 Extension Points

| Extension Point | Mechanism | Example |
|---|---|---|
| New channel | Implement Channel Adapter interface (inbound normalization + outbound delivery) | Telegram, Instagram, SMS |
| New LLM provider | Implement Model Provider interface (inference + streaming + token counting) | Google Gemini, AWS Bedrock, Azure OpenAI |
| New knowledge base | Implement Knowledge Provider interface (query + retrieval) | Direct Elasticsearch, Notion, Confluence |
| Custom actions (v1.1) | Register action schemas; implement Action Handler interface | Create refund, update CRM record, schedule appointment |
| Custom PII rules | Configure PII Shield with custom patterns and entity types | Industry-specific identifiers (patient ID, policy number) |
| Webhook integrations | Outbound webhook emitter for conversation events | CRM sync, analytics pipeline, Slack notifications |
| Theme/branding | CSS variable injection + logo upload in admin dashboard | White-label for agency partners |

### 15.4 Design for Extractability

The modular monolith architecture is explicitly designed to allow module extraction:
- Each module communicates via the event bus (not direct imports)
- Module boundaries align with future service boundaries
- Database tables are owned by single modules (no cross-module joins)
- API contracts between modules are versioned and documented

This means that when scaling demands it, any module can be extracted into an independent service with minimal refactoring — primarily changing the transport from in-process event bus to network-based messaging.

---

## Appendix: Architecture Decision Records

| ADR # | Decision | Date | Status |
|---|---|---|---|
| ADR-001 | Modular monolith over microservices | 2026-06-23 | Accepted |
| ADR-002 | Redis Streams as default event bus | 2026-06-23 | Accepted |
| ADR-003 | PostgreSQL as sole primary data store | 2026-06-23 | Accepted |
| ADR-004 | AGPL-3.0 open-core licensing | 2026-06-23 | Accepted |
| ADR-005 | WhatsApp-first data model design | 2026-06-23 | Accepted |
| ADR-006 | PII Shield as mandatory pipeline stage | 2026-06-23 | Accepted |
| ADR-007 | Vault integration via API (not shared DB) | 2026-06-23 | Accepted |
| ADR-008 | NATS JetStream for Kubernetes deployments | 2026-06-23 | Proposed |

---

**End of Document**
