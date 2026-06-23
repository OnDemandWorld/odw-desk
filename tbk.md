# Task Breakdown Knowledge Base (TBK): ODW.ai Desk

**Product:** Desk — Self-Hosted, WhatsApp-First AI Customer Support Agent
**Version:** 1.2
**Date:** 2026-06-24
**Source Document:** TSD v1.2 (2026-06-24)
**Status:** Ready for Execution
**Target:** 10 Epics, ~64 Tasks, ~240 Subtasks

---

## 1. Execution Overview

### 1.1 Implementation Strategy

ODW.ai Desk is a complex, event-driven system comprising 15 architectural components (14 original + Channel Adapter Plugin System) organized as a modular monolith (backend) with a React frontend. The implementation strategy follows a layered approach: foundation first, then core message pipeline with dual WhatsApp support, then AI intelligence, then user interfaces, deployment hardening, and finally multi-channel expansion.

**Critical Path:** The critical path runs through:
1. Infrastructure setup (PostgreSQL + Redis + Event Bus) → 
2. **Channel Adapter Plugin System** →
3. Channel Gateway (WhatsApp Business API **OR** WhatsApp Baileys Bridge, parallel) → 
4. Message Router → 
5. Conversation Manager → 
6. AI Engine (PII Shield → Model Router → Vault Client → LLM) → 
7. Outbound delivery → 
8. Agent Inbox (takeover flow)

Any delay on this path directly delays the first end-to-end demo.

### 1.2 Major Phases

| Phase | Duration Estimate | Description |
|---|---|---|
| Phase 1: Environment & Project Setup | Week 1 | Scaffolding, DB schema, Redis, event bus, **channel adapter plugin system**, Docker dev environment |
| Phase 2: Core Infrastructure | Weeks 2–3 | Channel Gateway (**WhatsApp Business API + Baileys Bridge**), Message Router, Conversation Manager, data models |
| Phase 3: AI Intelligence Pipeline | Weeks 3–5 | PII Shield, Model Router, Vault Client, LLM providers, confidence scoring |
| Phase 4: Agent & Admin Interfaces | Weeks 5–7 | Agent Inbox (REST + WebSocket), Admin Dashboard (**channel management UI**), Compliance, License |
| Phase 5: Deployment & Hardening | Weeks 7–8 | Docker production images, CI/CD, E2E tests, observability, Helm charts |
| **Phase 6: Multi-Channel Expansion** | **Weeks 9–12** | **Telegram, Discord, Slack, Signal, iMessage adapters (optional, parallelizable)** |

### 1.3 Parallelizable vs Sequential Workstreams

**Sequential (Critical Path):**
- Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5 (each depends on the previous)
- Within Phase 2: Channel Gateway → Message Router → Conversation Manager (ordered by data flow)
- Within Phase 3: PII Shield → Model Router → Vault Client → LLM Engine (ordered by pipeline)

**Parallelizable Workstreams:**
- **Track A (Backend Core):** Channel Gateway + Message Router + Conversation Manager
- **Track B (AI Pipeline):** PII Shield + Model Router + Vault Client (can scaffold in parallel with Track A)
- **Track C (Frontend):** React app scaffolding, component library setup, API client layer (starts in Week 3)
- **Track D (Infrastructure):** Docker Compose, Helm charts, CI/CD pipeline (starts in Week 1, continues throughout)
- **Track E (Testing):** Unit test scaffolding (Week 2), integration tests (Week 4), E2E tests (Week 7)

**Maximum Parallelism:** During Weeks 3–5, up to 4 tracks can run simultaneously:
- Track A: Conversation Manager + SLA timers
- Track B: AI Engine + LLM providers
- Track C: Agent Inbox API + WebSocket
- Track D: Compliance Engine + License Manager

### 1.4 Key Risk Areas

- **WhatsApp Business API:** External dependency; requires Meta Business verification. Mitigate with mock adapter from Day 1.
- **LLM Inference Latency:** 3–8s per inference; affects user experience. Mitigate with local model preference and streaming.
- **PII Shield Accuracy:** False positives block frontier model usage. Mitigate with configurable patterns and admin override.
- **Vault API Dependency:** Single point of failure for knowledge retrieval. Mitigate with Redis caching and graceful degradation.

---

## 2. Task Breakdown Structure

### Epic Overview

| Epic ID | Epic Name | Tasks | Subtasks | Priority |
|---|---|---|---|---|
| EPIC-1 | Environment & Project Setup | 6 | 21 | Critical |
| EPIC-2 | Core Message Pipeline | 9 | 36 | Critical |
| EPIC-3 | AI Intelligence Pipeline | 7 | 30 | Critical |
| EPIC-4 | Agent & Admin Interfaces | 6 | 26 | High |
| EPIC-5 | Deployment & Hardening | 5 | 20 | Medium |
| EPIC-6 | Multi-Channel Expansion (v1.1+) | 6 | 24 | Low |
| **EPIC-A** | **Brand Persona (Voice) [MVP]** | **6** | **22** | **High** |
| **EPIC-B** | **Response Policy & Guardrails [MVP, paid]** | **8** | **28** | **High** |
| **EPIC-C** | **Fine-tuned Local Persona (LoRA/QLoRA) [v1.1, paid]** | **7** | **21** | **Medium** |
| **EPIC-D** | **Compliance & Observability [cross-cutting]** | **4** | **12** | **Medium** |
| **TOTAL** | | **64** | **240** | |

### Epic 1: Environment & Project Setup (INFRA)

Foundation work: project scaffolding, database schema, Redis configuration, event bus, **channel adapter plugin system**, Docker development environment.

**Tasks:**
- INFRA-001: Project Scaffolding & Tooling Configuration
- INFRA-002: Database Schema & Migrations
- INFRA-003: Redis Configuration & Connection Management
- INFRA-004: Event Bus Implementation (Redis Streams)
- INFRA-005: Docker Development Environment
- **INFRA-006: Channel Adapter Plugin System Foundation**

### Epic 2: Core Message Pipeline (CORE)

The heart of the system: receiving messages from channels (with **dual WhatsApp support**), routing them, managing conversation state, and delivering responses.

**Tasks:**
- **CORE-001a: Channel Adapter Base & WhatsApp Business API Adapter**
- **CORE-001b: WhatsApp Baileys Bridge Adapter**
- CORE-002: Web Chat Adapter (WebSocket)
- CORE-003: Email Adapter (IMAP/SMTP)
- CORE-004: Message Router & Customer Resolver
- CORE-005: Conversation Manager & State Machine
- CORE-006: SLA Timer & Enforcement
- CORE-007: Outbound Dispatcher
- **CORE-008: Channel Adapter Configuration & Management API**
- **CORE-009: Multi-Channel Message Routing Enhancements**

### Epic 3: AI Intelligence Pipeline (AI)

The brain of the system: PII detection, model routing, knowledge retrieval, LLM inference, and confidence scoring.

**Tasks:**
- AI-001: PII Shield (Detection & Redaction)
- AI-002: Model Router (Selection & Fallback)
- AI-003: Vault Client (Knowledge Retrieval & Caching)
- AI-004: LLM Provider Abstraction & Implementations
- AI-005: AI Engine Orchestrator (Pipeline)
- AI-006: Prompt Builder & Response Formatter
- AI-007: Confidence Scorer & Decision Engine

### Epic 4: Agent & Admin Interfaces (AGENT)

Human-facing interfaces: agent inbox for conversation management, admin dashboard for configuration, compliance tools, and license management.

**Tasks:**
- AGENT-001: Agent Inbox REST API
- AGENT-002: Agent WebSocket (Real-time Updates)
- AGENT-003: Admin Setup Wizard API
- AGENT-004: Admin Configuration & Compliance APIs
- AGENT-005: Compliance Engine (Retention, Export, Deletion, Audit)
- AGENT-006: License Manager (Validation & Feature Gates)

### Epic 5: Deployment & Hardening (DEPLOY)

Production readiness: containerization, CI/CD, end-to-end testing, observability, and Kubernetes deployment.

**Tasks:**
- DEPLOY-001: Production Docker Images & Multi-stage Builds
- DEPLOY-002: CI/CD Pipeline (GitHub Actions)
- DEPLOY-003: End-to-End Test Suite
- DEPLOY-004: Observability (Metrics, Logging, Tracing)
- DEPLOY-005: Kubernetes Helm Charts

### Epic 6: Multi-Channel Expansion (v1.1+) (CHANNEL)

Optional post-MVP expansion to additional chat channels via the channel adapter plugin system. All tasks are parallelizable.

**Tasks:**
- **CHANNEL-001: Telegram Bot Adapter**
- **CHANNEL-002: Discord Bot Adapter**
- **CHANNEL-003: Slack App Adapter**
- **CHANNEL-004: Signal Messenger Adapter**
- **CHANNEL-005: iMessage Bridge Adapter**
- **CHANNEL-006: Channel Adapter SDK & Documentation**

---

### Epic A: Brand Persona (Voice) [MVP] (PERSONA)

Implements configurable brand voice (tone, vocabulary, formality, do's/don'ts) via prompt-based persona injection. Operators can define how Desk "sounds" to represent their business, and test/preview before going live.

**Tasks:**
- **PERSONA-001: Brand Persona Data Model & Migration**
- **PERSONA-002: Brand Persona Admin UI**
- **PERSONA-003: Persona Service Prompt Composition**
- **PERSONA-004: Persona Preview/Test Tool**
- **PERSONA-005: Persona Injection into Inference Path**
- **PERSONA-006: Persona Versioning & Rollback (v1.1)**

---

### Epic B: Response Policy & Guardrails [MVP, paid] (POLICY)

Implements configurable topic-based response rules (competitor mentions, pricing, legal/medical disclaimers) with pre-generation intent detection and post-generation validation. Enforces guardrails and logs all policy decisions to audit trail.

**Tasks:**
- **POLICY-001: Response Policy Data Model & Migration**
- **POLICY-002: Policy Admin UI (Rule Builder)**
- **POLICY-003: Deterministic Keyword/Rule Pre-Hook**
- **POLICY-004: Intent Classifier Integration (Tiered)**
- **POLICY-005: Templated/Redirect Response Actions**
- **POLICY-006: Post-Generation Check**
- **POLICY-007: Policy Audit Logging**
- **POLICY-008: Restricted-Topics & No General-Knowledge Fallback Mode**

---

### Epic C: Fine-tuned Local Persona (LoRA/QLoRA) [v1.1, paid] (LORA)

Implements support for loading externally-trained LoRA/QLoRA adapters as the persona backend. Desk consumes (does not produce) fine-tuned artifacts. Includes vLLM/Ollama adapter loading, validation, fallback, and audit logging.

**Tasks:**
- **LORA-001: Adapter Storage & `adapter_uri` Plumbing**
- **LORA-002: vLLM LoRA Serving Integration**
- **LORA-003: Ollama Adapter Workflow & Documentation**
- **LORA-004: Startup Validation & Graceful Fallback**
- **LORA-005: Persona-Backend Switch (Prompt ↔ Adapter)**
- **LORA-006: Audit Logging of `persona_backend_used`**
- **LORA-007: Operator-Facing Docs/Runbook for External Adapter Production**

---

### Epic D: Compliance & Observability [cross-cutting] (COMPLIANCE-OBS)

Cross-cutting concerns for persona/policy compliance: anonymized training data enforcement, adapter versioning traceability, metrics, and dashboards for guardrail quality.

**Tasks:**
- **COMPLIANCE-OBS-001: Anonymized/Synthetic Data Requirement Enforcement**
- **COMPLIANCE-OBS-002: Adapter Versioning Traceability**
- **COMPLIANCE-OBS-003: Persona/Policy Decision Metrics (Prometheus)**
- **COMPLIANCE-OBS-004: Guardrail False-Positive/Negative Dashboards**

---

## 3. Task Definition Format

Each task and subtask follows this strict schema:

```
ID: <hierarchical-id>
Title: <descriptive-title>
Description: <clear-and-specific-description>
Inputs: <TSD section references, schemas, APIs>
Output: <exact expected artifact>
Acceptance Criteria: <testable conditions>
Dependencies: <task IDs>
Execution Type: AI-Agent | Developer | Either
Priority: Critical | High | Medium | Low
Estimated Effort: S (< 2h) | M (2–6h) | L (6–16h)
```

---

## 4. Dependency Graph

### 4.1 Epic-Level Dependencies

```
EPIC-1 (Environment) ──→ EPIC-2 (Core Pipeline)
                      ──→ EPIC-3 (AI Pipeline)
EPIC-2 (Core Pipeline) ──→ EPIC-3 (AI Pipeline) [AI Engine consumes ProcessRequest]
EPIC-2 (Core Pipeline) ──→ EPIC-4 (Agent/Admin) [Agent Inbox reads conversation state]
EPIC-3 (AI Pipeline) ──→ EPIC-4 (Agent/Admin) [Escalation feeds Agent Inbox]
EPIC-4 (Agent/Admin) ──→ EPIC-5 (Deployment) [All features complete before hardening]
EPIC-3 (AI Pipeline) ──→ EPIC-5 (Deployment) [AI worker container needs complete code]
```

### 4.2 Task-Level Dependencies (Critical Path Highlighted)

```
INFRA-001 ──→ INFRA-002 ──→ INFRA-004
          ──→ INFRA-003 ──→ INFRA-004
INFRA-004 ──→ CORE-001 ──→ CORE-004 ──→ CORE-005 ──→ CORE-007
                        ──→ CORE-006
CORE-001 ──→ CORE-002 (parallel)
CORE-001 ──→ CORE-003 (parallel)
CORE-005 ──→ AI-005 ──→ AI-007
INFRA-002 ──→ AI-001 (PII Shield needs DB for config)
INFRA-003 ──→ AI-003 (Vault Client needs Redis cache)
AI-001 ──→ AI-002 ──→ AI-005
AI-003 ──→ AI-005
AI-004 ──→ AI-005
CORE-005 ──→ AGENT-001 ──→ AGENT-002
INFRA-002 ──→ AGENT-005 (Compliance needs audit_logs table)
INFRA-002 ──→ AGENT-006 (License needs license_state table)
EPIC-2 + EPIC-3 + EPIC-4 ──→ DEPLOY-001 through DEPLOY-005
```

### 4.3 Blocking Tasks

| Task | Blocks | Reason |
|---|---|---|
| INFRA-001 (Scaffolding) | ALL other tasks | No code can be written without project structure |
| INFRA-002 (DB Schema) | CORE-*, AI-001, AGENT-005, AGENT-006 | All persistence depends on tables existing |
| INFRA-004 (Event Bus) | CORE-001, CORE-004, CORE-007 | All inter-module communication |
| CORE-001 (WhatsApp Adapter) | CORE-004, end-to-end demo | First channel must work for any demo |
| CORE-005 (Conversation Manager) | AI-005, AGENT-001 | AI and Agent both depend on conversation state |
| AI-005 (AI Engine) | CORE-007 (outbound), AGENT-002 (escalation events) | Full pipeline must work for responses |

### 4.4 Parallelizable Groups

**Group A (Week 1–2, after INFRA-001 + INFRA-002):**
- INFRA-003 (Redis) ∥ INFRA-004 (Event Bus) ∥ INFRA-005 (Docker dev)

**Group B (Week 2–3, after INFRA-004):**
- CORE-001 (WhatsApp) ∥ CORE-002 (Web Chat) ∥ CORE-003 (Email)

**Group C (Week 3–4, after CORE-004):**
- CORE-005 (Conversation Manager) ∥ AI-001 (PII Shield) ∥ AI-003 (Vault Client) ∥ AI-004 (LLM Providers)

**Group D (Week 5–6, after CORE-005):**
- AGENT-001 (Agent REST) ∥ AGENT-005 (Compliance) ∥ AGENT-006 (License)

**Group E (Week 7–8):**
- DEPLOY-001 ∥ DEPLOY-002 ∥ DEPLOY-003 ∥ DEPLOY-004 ∥ DEPLOY-005

### 4.5 Circular Dependency Check

✅ No circular dependencies detected. The dependency graph is a DAG (Directed Acyclic Graph) with clear topological ordering:
INFRA → CORE → AI → AGENT → DEPLOY (with some cross-edges that maintain acyclicity).

---

## 5. Execution Phases

### Phase 1: Environment & Project Setup (Week 1)

**Goal:** Fully functional development environment with database, cache, event bus, and project scaffolding.

**Phase Entry Criteria:** Empty repository or fresh clone.
**Phase Exit Criteria:** `docker-compose up` starts all services; migrations run; health endpoint returns 200.

| Order | Task ID | Task Title | Effort |
|---|---|---|---|
| 1 | INFRA-001 | Project Scaffolding & Tooling | L |
| 2 | INFRA-002 | Database Schema & Migrations | L |
| 3 | INFRA-003 | Redis Configuration | M |
| 4 | INFRA-004 | Event Bus Implementation | L |
| 5 | INFRA-005 | Docker Development Environment | L |

**Phase Verification:**
```bash
docker-compose -f docker-compose.dev.yml up
curl http://localhost:8000/health  # Returns 200
pytest tests/unit/test_health.py   # All pass
```

---

### Phase 2: Core Infrastructure — Message Pipeline (Weeks 2–3)

**Goal:** Messages flow from WhatsApp webhook through routing to conversation persistence and outbound delivery.

**Phase Entry Criteria:** Phase 1 complete; event bus operational.
**Phase Exit Criteria:** Inbound WhatsApp message creates conversation, persists message, triggers outbound response (mock AI).

| Order | Task ID | Task Title | Effort |
|---|---|---|---|
| 1 | CORE-001 | Channel Adapter Base & WhatsApp Adapter | L |
| 2 | CORE-002 | Web Chat Adapter | M |
| 3 | CORE-003 | Email Adapter | M |
| 4 | CORE-004 | Message Router & Customer Resolver | L |
| 5 | CORE-005 | Conversation Manager & State Machine | L |
| 6 | CORE-006 | SLA Timer & Enforcement | M |
| 7 | CORE-007 | Outbound Dispatcher | L |

**Phase Verification:**
```bash
# Simulate WhatsApp webhook
curl -X POST http://localhost:8000/api/v1/webhooks/whatsapp \
  -H "X-Hub-Signature-256: sha256=<valid>" \
  -d '{"object":"whatsapp_business_account","entry":[...]}'
# Verify: conversation created in DB, message persisted, outbound event published
```

---

### Phase 3: AI Intelligence Pipeline (Weeks 3–5)

**Goal:** Full AI processing pipeline operational: PII detection → model routing → Vault retrieval → LLM inference → confidence scoring → response delivery.

**Phase Entry Criteria:** Phase 2 complete; messages flow through event bus.
**Phase Exit Criteria:** Customer message triggers AI response grounded in Vault knowledge, with PII detection and model routing working.

| Order | Task ID | Task Title | Effort |
|---|---|---|---|
| 1 | AI-001 | PII Shield | L |
| 2 | AI-002 | Model Router | M |
| 3 | AI-003 | Vault Client | L |
| 4 | AI-004 | LLM Provider Abstraction | L |
| 5 | AI-005 | AI Engine Orchestrator | L |
| 6 | AI-006 | Prompt Builder & Response Formatter | M |
| 7 | AI-007 | Confidence Scorer & Decision Engine | M |

**Phase Verification:**
```bash
# Send message with PII → verify local-only routing
# Send complex message → verify frontier model selection
# Send message → verify Vault knowledge included in response
# Send ambiguous message → verify escalation to human
```

---

### Phase 4: Agent & Admin Interfaces (Weeks 5–7)

**Goal:** Human agents can take over conversations via real-time inbox; admins can configure the system, manage compliance, and validate licenses.

**Phase Entry Criteria:** Phase 2 + 3 complete; conversations and AI pipeline operational.
**Phase Exit Criteria:** Agent can view escalated conversations, take over, respond, and resolve. Admin can complete setup wizard and export data.

| Order | Task ID | Task Title | Effort |
|---|---|---|---|
| 1 | AGENT-001 | Agent Inbox REST API | L |
| 2 | AGENT-002 | Agent WebSocket (Real-time) | L |
| 3 | AGENT-003 | Admin Setup Wizard API | M |
| 4 | AGENT-004 | Admin Configuration & Compliance APIs | M |
| 5 | AGENT-005 | Compliance Engine | L |
| 6 | AGENT-006 | License Manager | M |

**Phase Verification:**
```bash
# Agent login → view escalated conversations → take over → respond → resolve
# Admin → complete setup wizard → verify Vault + WhatsApp + AI connections
# Admin → export customer data → verify GDPR-compliant JSON output
# Admin → request deletion → verify all data removed
```

---

### Phase 5: Deployment & Hardening (Weeks 7–8)

**Goal:** Production-ready Docker images, CI/CD pipeline, comprehensive test suite, observability, and Kubernetes deployment option.

**Phase Entry Criteria:** All features implemented and passing integration tests.
**Phase Exit Criteria:** System deployable via `docker-compose up` (single-node) or `helm install` (Kubernetes); all E2E tests pass; Grafana dashboards show metrics.

| Order | Task ID | Task Title | Effort |
|---|---|---|---|
| 1 | DEPLOY-001 | Production Docker Images | L |
| 2 | DEPLOY-002 | CI/CD Pipeline | L |
| 3 | DEPLOY-003 | End-to-End Test Suite | L |
| 4 | DEPLOY-004 | Observability Stack | L |
| 5 | DEPLOY-005 | Kubernetes Helm Charts | L |

**Phase Verification:**
```bash
# docker-compose up → all services healthy
# helm install desk ./helm → pods running in Kubernetes
# pytest tests/e2e/ → all pass
# curl /metrics → Prometheus format metrics
# Locust load test → 100 msg/s sustained
```

---

## 6. AI-Agent Optimization Layer

### 6.1 Task Suitability Classification

| Task ID | Single-Shot | Iterative | Context Window | Risk Level |
|---|---|---|---|---|
| INFRA-001 | ✓ | | Minimal | Low |
| INFRA-002 | ✓ | | Minimal | Low |
| INFRA-003 | ✓ | | Minimal | Low |
| INFRA-004 | | ✓ | Medium | Medium |
| INFRA-005 | ✓ | | Minimal | Low |
| CORE-001 | | ✓ | Medium | Medium |
| CORE-002 | | ✓ | Medium | Medium |
| CORE-003 | | ✓ | Medium | Medium |
| CORE-004 | | ✓ | Medium | Medium |
| CORE-005 | | ✓ | Large | High |
| CORE-006 | ✓ | | Minimal | Low |
| CORE-007 | | ✓ | Medium | Medium |
| AI-001 | | ✓ | Medium | High |
| AI-002 | | ✓ | Medium | High |
| AI-003 | | ✓ | Medium | Medium |
| AI-004 | | ✓ | Medium | Medium |
| AI-005 | | ✓ | Large | High |
| AI-006 | | ✓ | Medium | Medium |
| AI-007 | | ✓ | Medium | High |
| AGENT-001 | | ✓ | Medium | Medium |
| AGENT-002 | | ✓ | Large | High |
| AGENT-003 | ✓ | | Medium | Low |
| AGENT-004 | | ✓ | Medium | Medium |
| AGENT-005 | | ✓ | Large | High |
| AGENT-006 | | ✓ | Medium | Medium |
| DEPLOY-001 | ✓ | | Minimal | Low |
| DEPLOY-002 | ✓ | | Minimal | Low |
| DEPLOY-003 | | ✓ | Large | Medium |
| DEPLOY-004 | | ✓ | Medium | Medium |
| DEPLOY-005 | ✓ | | Medium | Low |

### 6.2 AI-Agent Execution Guidelines

**Single-Shot Generation Tasks (suitable for one-pass AI generation):**
- INFRA-001: Project scaffolding — deterministic file structure from TSD §17
- INFRA-002: Database models — direct mapping from TSD §4 schemas
- INFRA-003: Redis config — standard connection setup
- INFRA-005: Docker Compose — standard multi-service compose file
- CORE-006: SLA timer — straightforward timer logic
- AGENT-003: Setup wizard — CRUD operations with validation
- DEPLOY-001: Dockerfiles — standard multi-stage builds
- DEPLOY-002: GitHub Actions — standard CI/CD template
- DEPLOY-005: Helm charts — standard Kubernetes manifests

**Iterative Refinement Tasks (require multiple passes):**
- CORE-005: State machine — complex transitions, edge cases, concurrency
- AI-001: PII Shield — Presidio integration, custom patterns, accuracy tuning
- AI-002: Model Router — complex routing logic, circuit breaker integration
- AI-005: AI Engine — orchestrates 5+ sub-components, error handling
- AI-007: Confidence scoring — heuristic design, threshold tuning
- AGENT-002: WebSocket — connection management, reconnection, broadcast
- AGENT-005: Compliance — hash-chained audit, GDPR workflows
- DEPLOY-003: E2E tests — requires running system, mock services

**Risk Mitigation for AI Agents:**
- High-risk tasks should include explicit test cases in the prompt
- Provide the relevant TSD section as context
- Request the agent to produce both implementation AND tests in the same session
- Review output of high-risk tasks before proceeding to dependent tasks

### 6.3 Context Window Requirements

**Minimal (Single File):**
- Configuration files (pyproject.toml, alembic.ini, Dockerfile)
- Simple utility modules (hashing.py, encryption.py)
- Database model files (one table per file)
- Simple API endpoints (health check, CRUD)

**Medium (Module-Level):**
- Channel adapters (base.py + whatsapp.py + tests)
- AI sub-components (pii_shield.py + tests + config)
- REST API modules (inbox_api.py + schemas + tests)
- Event bus implementation (bus.py + redis_streams.py + tests)

**Large (Cross-Service):**
- AI Engine orchestrator (engine.py + pipeline.py + prompt_builder.py + confidence.py + tests)
- Conversation Manager (manager.py + state_machine.py + sla.py + models.py + tests)
- Compliance Engine (engine.py + retention.py + export.py + deletion.py + audit.py + tests)
- Agent WebSocket (websocket.py + inbox_api.py + event subscriptions + tests)
- E2E test suite (multiple test files, mock services, fixtures)

---

## 7. File-Level Mapping

### 7.1 Complete File Ownership Matrix

| File Path | Owner Task | File Type | Created/Modified |
|---|---|---|---|
| `pyproject.toml` | INFRA-001 | TOML | Created |
| `requirements.txt` | INFRA-001 | TXT | Created |
| `alembic.ini` | INFRA-001 | INI | Created |
| `src/desk/__init__.py` | INFRA-001 | PY | Created |
| `src/desk/main.py` | INFRA-001 | PY | Created |
| `src/desk/config.py` | INFRA-001 | PY | Created |
| `src/desk/dependencies.py` | INFRA-001 | PY | Created |
| `alembic/env.py` | INFRA-002 | PY | Created |
| `alembic/versions/001_initial.py` | INFRA-002 | PY | Created |
| `src/desk/models/__init__.py` | INFRA-002 | PY | Created |
| `src/desk/models/base.py` | INFRA-002 | PY | Created |
| `src/desk/models/customer.py` | INFRA-002 | PY | Created |
| `src/desk/models/conversation.py` | INFRA-002 | PY | Created |
| `src/desk/models/message.py` | INFRA-002 | PY | Created |
| `src/desk/models/agent.py` | INFRA-002 | PY | Created |
| `src/desk/models/ai_configuration.py` | INFRA-002 | PY | Created |
| `src/desk/models/audit_log.py` | INFRA-002 | PY | Created |
| `src/desk/models/license_state.py` | INFRA-002 | PY | Created |
| `src/desk/events/__init__.py` | INFRA-004 | PY | Created |
| `src/desk/events/bus.py` | INFRA-004 | PY | Created |
| `src/desk/events/redis_streams.py` | INFRA-004 | PY | Created |
| `src/desk/events/nats.py` | INFRA-004 | PY | Created |
| `src/desk/events/schemas.py` | INFRA-004 | PY | Created |
| `docker-compose.dev.yml` | INFRA-005 | YAML | Created |
| `docker-compose.yml` | INFRA-005 | YAML | Created |
| `.env.example` | INFRA-005 | ENV | Created |
| `src/desk/channels/__init__.py` | CORE-001 | PY | Created |
| `src/desk/channels/base.py` | CORE-001 | PY | Created |
| `src/desk/channels/whatsapp.py` | CORE-001 | PY | Created |
| `src/desk/channels/webchat.py` | CORE-002 | PY | Created |
| `src/desk/channels/email.py` | CORE-003 | PY | Created |
| `src/desk/channels/outbound.py` | CORE-007 | PY | Created |
| `src/desk/router/__init__.py` | CORE-004 | PY | Created |
| `src/desk/router/message_router.py` | CORE-004 | PY | Created |
| `src/desk/router/customer_resolver.py` | CORE-004 | PY | Created |
| `src/desk/conversations/__init__.py` | CORE-005 | PY | Created |
| `src/desk/conversations/manager.py` | CORE-005 | PY | Created |
| `src/desk/conversations/state_machine.py` | CORE-005 | PY | Created |
| `src/desk/conversations/sla.py` | CORE-006 | PY | Created |
| `src/desk/ai/__init__.py` | AI-005 | PY | Created |
| `src/desk/ai/engine.py` | AI-005 | PY | Created |
| `src/desk/ai/pipeline.py` | AI-005 | PY | Created |
| `src/desk/ai/pii_shield.py` | AI-001 | PY | Created |
| `src/desk/ai/model_router.py` | AI-002 | PY | Created |
| `src/desk/ai/vault_client.py` | AI-003 | PY | Created |
| `src/desk/ai/prompt_builder.py` | AI-006 | PY | Created |
| `src/desk/ai/confidence.py` | AI-007 | PY | Created |
| `src/desk/ai/providers/__init__.py` | AI-004 | PY | Created |
| `src/desk/ai/providers/base.py` | AI-004 | PY | Created |
| `src/desk/ai/providers/ollama.py` | AI-004 | PY | Created |
| `src/desk/ai/providers/openai.py` | AI-004 | PY | Created |
| `src/desk/ai/providers/anthropic.py` | AI-004 | PY | Created |
| `src/desk/agents/__init__.py` | AGENT-001 | PY | Created |
| `src/desk/agents/inbox_api.py` | AGENT-001 | PY | Created |
| `src/desk/agents/websocket.py` | AGENT-002 | PY | Created |
| `src/desk/agents/models.py` | AGENT-001 | PY | Created |
| `src/desk/admin/__init__.py` | AGENT-003 | PY | Created |
| `src/desk/admin/setup_api.py` | AGENT-003 | PY | Created |
| `src/desk/admin/config_api.py` | AGENT-004 | PY | Created |
| `src/desk/admin/compliance_api.py` | AGENT-004 | PY | Created |
| `src/desk/admin/license_api.py` | AGENT-006 | PY | Created |
| `src/desk/compliance/__init__.py` | AGENT-005 | PY | Created |
| `src/desk/compliance/engine.py` | AGENT-005 | PY | Created |
| `src/desk/compliance/retention.py` | AGENT-005 | PY | Created |
| `src/desk/compliance/export.py` | AGENT-005 | PY | Created |
| `src/desk/compliance/deletion.py` | AGENT-005 | PY | Created |
| `src/desk/compliance/audit.py` | AGENT-005 | PY | Created |
| `src/desk/license/__init__.py` | AGENT-006 | PY | Created |
| `src/desk/license/manager.py` | AGENT-006 | PY | Created |
| `src/desk/suite/__init__.py` | AGENT-003 | PY | Created |
| `src/desk/suite/auth_client.py` | AGENT-003 | PY | Created |
| `src/desk/suite/billing_client.py` | AGENT-006 | PY | Created |
| `src/desk/schemas/__init__.py` | INFRA-001 | PY | Created |
| `src/desk/schemas/api.py` | INFRA-001 | PY | Created |
| `src/desk/schemas/events.py` | INFRA-004 | PY | Created |
| `src/desk/schemas/channels.py` | CORE-001 | PY | Created |
| `src/desk/utils/__init__.py` | INFRA-001 | PY | Created |
| `src/desk/utils/encryption.py` | INFRA-002 | PY | Created |
| `src/desk/utils/pii_filter.py` | AI-001 | PY | Created |
| `src/desk/utils/hashing.py` | AGENT-005 | PY | Created |
| `Dockerfile.api` | DEPLOY-001 | Dockerfile | Created |
| `Dockerfile.worker` | DEPLOY-001 | Dockerfile | Created |
| `Dockerfile.web` | DEPLOY-001 | Dockerfile | Created |
| `.github/workflows/ci.yml` | DEPLOY-002 | YAML | Created |
| `.github/workflows/cd.yml` | DEPLOY-002 | YAML | Created |
| `tests/unit/` | DEPLOY-003 | PY | Created |
| `tests/integration/` | DEPLOY-003 | PY | Created |
| `tests/e2e/` | DEPLOY-003 | PY | Created |
| `helm/Chart.yaml` | DEPLOY-005 | YAML | Created |
| `helm/values.yaml` | DEPLOY-005 | YAML | Created |
| `helm/templates/` | DEPLOY-005 | YAML | Created |

### 7.2 Test File Mapping

| Test File | Tests For | Type |
|---|---|---|
| `tests/unit/test_models.py` | INFRA-002 | Unit |
| `tests/unit/test_event_bus.py` | INFRA-004 | Unit |
| `tests/unit/test_whatsapp_adapter.py` | CORE-001 | Unit |
| `tests/unit/test_webchat_adapter.py` | CORE-002 | Unit |
| `tests/unit/test_email_adapter.py` | CORE-003 | Unit |
| `tests/unit/test_message_router.py` | CORE-004 | Unit |
| `tests/unit/test_customer_resolver.py` | CORE-004 | Unit |
| `tests/unit/test_conversation_manager.py` | CORE-005 | Unit |
| `tests/unit/test_state_machine.py` | CORE-005 | Unit |
| `tests/unit/test_sla.py` | CORE-006 | Unit |
| `tests/unit/test_outbound_dispatcher.py` | CORE-007 | Unit |
| `tests/unit/test_pii_shield.py` | AI-001 | Unit |
| `tests/unit/test_model_router.py` | AI-002 | Unit |
| `tests/unit/test_vault_client.py` | AI-003 | Unit |
| `tests/unit/test_llm_providers.py` | AI-004 | Unit |
| `tests/unit/test_ai_engine.py` | AI-005 | Unit |
| `tests/unit/test_prompt_builder.py` | AI-006 | Unit |
| `tests/unit/test_confidence.py` | AI-007 | Unit |
| `tests/unit/test_inbox_api.py` | AGENT-001 | Unit |
| `tests/unit/test_agent_websocket.py` | AGENT-002 | Unit |
| `tests/unit/test_setup_api.py` | AGENT-003 | Unit |
| `tests/unit/test_compliance_engine.py` | AGENT-005 | Unit |
| `tests/unit/test_license_manager.py` | AGENT-006 | Unit |
| `tests/integration/test_message_pipeline.py` | CORE-* | Integration |
| `tests/integration/test_ai_pipeline.py` | AI-* | Integration |
| `tests/integration/test_agent_flow.py` | AGENT-* | Integration |
| `tests/e2e/test_whatsapp_flow.py` | Full system | E2E |
| `tests/e2e/test_takeover_flow.py` | Full system | E2E |
| `tests/e2e/test_pii_routing.py` | Full system | E2E |
| `tests/e2e/test_compliance_flow.py` | Full system | E2E |

### 7.3 Conflict Check

✅ No file is owned by multiple tasks. Each file has exactly one owner task.
✅ Test files are co-owned with their implementation tasks for unit tests; integration/E2E tests belong to DEPLOY-003.

---

## 8. Test Task Mapping

### 8.1 Unit Test Specifications

#### INFRA-002 Tests (`tests/unit/test_models.py`)
- **Input:** SQLAlchemy model instantiation with valid/invalid data
- **Expected:** Models serialize correctly; constraints enforced; relationships resolve
- **Cases:** Customer with JSONB channel_identifiers; Conversation state enum validation; Message with PII flags; AuditLog hash chain integrity

#### INFRA-004 Tests (`tests/unit/test_event_bus.py`)
- **Input:** Event publish/consume operations
- **Expected:** Events published to correct stream; consumers receive in order; dead-letter on failure
- **Cases:** Publish inbound.message; consume with partition key; retry on failure; DLQ after max retries

#### CORE-001 Tests (`tests/unit/test_whatsapp_adapter.py`)
- **Input:** Meta webhook payloads (valid/invalid signatures, various message types)
- **Expected:** Valid payloads normalized to InboundMessage; invalid signatures rejected with 401
- **Cases:** Text message; image message; interactive response; duplicate message_id dedup; signature verification fail

#### CORE-004 Tests (`tests/unit/test_message_router.py`, `test_customer_resolver.py`)
- **Input:** InboundMessage events with various customer identifiers
- **Expected:** Existing customers resolved from cache; new customers created; conversations loaded/created
- **Cases:** Cache hit; cache miss → DB lookup; new customer creation; closed conversation → new conversation; escalated → skip AI

#### CORE-005 Tests (`tests/unit/test_conversation_manager.py`, `test_state_machine.py`)
- **Input:** State transition requests with various preconditions
- **Expected:** Valid transitions succeed; invalid transitions rejected with error; events published
- **Cases:** new→active; active→pending (24h timeout); active→escalated (low confidence); escalated→active (takeover); pending→closed (no reply); invalid: closed→active

#### AI-001 Tests (`tests/unit/test_pii_shield.py`)
- **Input:** Text with various PII types (names, phones, emails, SSNs, credit cards)
- **Expected:** PII detected with correct types; redacted text uses placeholders; routing directive correct
- **Cases:** No PII → NO_RESTRICTION; phone detected → LOCAL_MODEL_ONLY; PII + admin override → REDACTED_FRONTIER_OK; custom pattern match; Presidio confidence threshold

#### AI-002 Tests (`tests/unit/test_model_router.py`)
- **Input:** PII directive + complexity score + conversation context
- **Expected:** Correct model selected; fallback chain generated; circuit breaker respected
- **Cases:** LOCAL_MODEL_ONLY → local; REDACTED_FRONTIER_OK → frontier with redacted; high complexity → frontier; circuit breaker OPEN → fallback; all models down → escalate

#### AI-005 Tests (`tests/unit/test_ai_engine.py`)
- **Input:** ProcessRequest with various configurations
- **Expected:** Full pipeline executes; correct model called; Vault results included; response published or escalation triggered
- **Cases:** Happy path (confidence ≥ threshold); low confidence → escalate; Vault failure → proceed without knowledge; model timeout → fallback; PII + local model path

#### AI-007 Tests (`tests/unit/test_confidence.py`)
- **Input:** Model outputs with various characteristics (logprobs, refusal language, grounding)
- **Expected:** Confidence score calculated correctly; threshold comparison triggers correct action
- **Cases:** High logprobs → high confidence; refusal language → low confidence; no Vault grounding → reduced confidence; exact threshold boundary

#### AGENT-001 Tests (`tests/unit/test_inbox_api.py`)
- **Input:** HTTP requests to agent endpoints (list, detail, takeover, respond, resolve)
- **Expected:** Correct responses; authorization enforced; state transitions correct
- **Cases:** List with filters; pagination; takeover success; takeover conflict (already assigned); send message; resolve conversation

#### AGENT-005 Tests (`tests/unit/test_compliance_engine.py`)
- **Input:** Export/delete requests; retention enforcement triggers
- **Expected:** Data exported in correct format; deletion removes all customer data; audit log hash chain valid
- **Cases:** Export by WhatsApp number; delete all data; retention cleanup (old conversations); hash chain integrity verification

#### AGENT-006 Tests (`tests/unit/test_license_manager.py`)
- **Input:** License validation scenarios (valid, expired, grace period, invalid)
- **Expected:** Feature gates enforced correctly; grace period allows paid features; invalid license blocks paid features
- **Cases:** Valid paid license → all features; expired < 14 days → grace period; expired > 14 days → free tier; invalid signature → blocked; offline validation

### 8.2 Integration Test Specifications

#### `tests/integration/test_message_pipeline.py`
- **Scope:** Full inbound → route → persist → outbound flow (mock AI)
- **Infrastructure:** Docker Compose with PostgreSQL + Redis
- **Test Cases:**
  1. WhatsApp webhook → conversation created → message persisted → outbound event published
  2. Duplicate webhook → only one message persisted (dedup)
  3. Multiple messages rapid fire → all persisted in order
  4. Web chat message → session created → conversation linked
  5. Customer returns → existing conversation resumed (not new)

#### `tests/integration/test_ai_pipeline.py`
- **Scope:** ProcessRequest → PII → Model Router → Vault → LLM → Response
- **Infrastructure:** Mock Vault server, mock LLM endpoint, real Redis + PostgreSQL
- **Test Cases:**
  1. Clean message → local model → Vault results → response delivered
  2. PII message → local model only → redacted text used → response delivered
  3. Complex message → frontier model → response delivered
  4. Low confidence → escalation event published → conversation state → escalated
  5. Vault unavailable → AI proceeds without knowledge + disclaimer
  6. Model timeout → fallback to next model in chain

#### `tests/integration/test_agent_flow.py`
- **Scope:** AI escalation → agent takeover → response → resolution
- **Infrastructure:** Real PostgreSQL + Redis; mock LLM returning low confidence
- **Test Cases:**
  1. AI escalates → agent sees in inbox → takes over → AI disabled → agent responds → resolves
  2. Two agents try to take over same conversation → 409 conflict for second
  3. Agent resolves → AI re-enabled for future conversations
  4. WebSocket receives real-time updates during takeover flow

### 8.3 E2E Test Specifications

#### `tests/e2e/test_whatsapp_flow.py`
- **Setup:** Full Docker Compose deployment; mock WhatsApp API; mock LLM
- **Flow:** Send webhook → receive AI response via mock WhatsApp API
- **Assertions:** Response delivered; conversation in DB; audit log entry; metrics incremented

#### `tests/e2e/test_takeover_flow.py`
- **Setup:** Full deployment; mock LLM configured for low confidence
- **Flow:** Customer message → AI escalates → agent takes over via API → agent responds → resolves
- **Assertions:** State transitions correct; WebSocket events received; final state = resolved

#### `tests/e2e/test_pii_routing.py`
- **Setup:** Full deployment; PII Shield enabled; frontier allowed with redaction = false
- **Flow:** Send message with phone number → verify routed to local model only
- **Assertions:** PII detected; routing directive = LOCAL_MODEL_ONLY; frontier model NOT called; response still delivered

#### `tests/e2e/test_compliance_flow.py`
- **Setup:** Full deployment; conversations exist with customer data
- **Flow:** Admin exports data → verifies content; admin deletes data → verifies removal
- **Assertions:** Export contains all customer messages; deletion removes from all tables; audit log records both operations

---

## 9. Definition of Done (Global)

### 9.1 Code Completion Criteria

- [ ] All 30 tasks marked complete with verifiable outputs
- [ ] All API endpoints implemented per TSD §5 contracts (request/response format, status codes, error format)
- [ ] All data models match TSD §4 schema definitions (fields, types, constraints, indexes)
- [ ] All business logic follows TSD §6 specifications (pipeline steps, state transitions, routing rules)
- [ ] No TODO/FIXME/HACK comments in production code
- [ ] All public functions have docstrings (Google style)
- [ ] Type hints on all function signatures (mypy strict passes)

### 9.2 Testing Criteria

- [ ] Unit test coverage ≥ 80% for business logic modules (AI Engine, PII Shield, Model Router, Conversation Manager)
- [ ] All unit tests pass: `pytest tests/unit/ --cov=src/desk --cov-fail-under=80`
- [ ] All integration tests pass: `pytest tests/integration/`
- [ ] All E2E tests pass: `pytest tests/e2e/`
- [ ] Load test sustains 100 messages/second for 5 minutes (Locust)
- [ ] No flaky tests (all tests pass 3 consecutive runs)

### 9.3 Data Integrity Criteria

- [ ] PostgreSQL schema matches TSD §4 exactly (all tables, columns, indexes, constraints)
- [ ] Alembic migrations run cleanly from scratch: `alembic upgrade head`
- [ ] Audit log hash chain is unbroken (verification script passes)
- [ ] PII fields encrypted at rest (AES-256-GCM)
- [ ] No data leakage in logs (PII filter tested with known PII strings)

### 9.4 API Contract Criteria

- [ ] All endpoints return correct HTTP status codes per TSD §5.5
- [ ] Error responses follow standard format: `{"error": {"code": "...", "message": "...", "details": {}}}`
- [ ] Pagination follows standard format: `page`, `page_size`, `total`, `total_pages`
- [ ] Authentication enforced on all protected endpoints (OIDC token validation)
- [ ] Rate limiting configured (429 responses when exceeded)
- [ ] OpenAPI schema auto-generated and accurate (`/docs` endpoint)

### 9.5 Deployment Criteria

- [ ] `docker-compose up` starts all services with zero manual configuration (using .env.example defaults)
- [ ] Health endpoint returns 200 with all checks passing
- [ ] All containers run as non-root users
- [ ] No secrets in Docker images (environment variables only)
- [ ] Helm chart deploys successfully to Kubernetes cluster
- [ ] CI/CD pipeline: lint → type-check → test → build → push → deploy (fully automated)

### 9.6 Observability Criteria

- [ ] `/metrics` endpoint returns Prometheus-format metrics (all categories from TSD §16)
- [ ] Structured JSON logging with PII filter active
- [ ] Correlation IDs (trace_id) propagated through full pipeline
- [ ] OpenTelemetry traces exported (configurable OTLP endpoint)
- [ ] Pre-configured Grafana alerts load successfully

### 9.7 Security Criteria

- [ ] WhatsApp webhook signature verification (HMAC-SHA256)
- [ ] All API inputs validated via Pydantic (strict types, length limits)
- [ ] SQL injection prevented (parameterized queries via SQLAlchemy)
- [ ] XSS prevented (output encoding in React frontend)
- [ ] TLS 1.3 for all external communication
- [ ] Frontier API keys encrypted at rest (AES-256)
- [ ] License validation on startup and every 24h
- [ ] Security scan (Trivy) passes with no critical/high vulnerabilities

---

## 10. Risk & Bottleneck Identification

### 10.1 High-Complexity Tasks

| Task | Complexity Source | Impact | Mitigation |
|---|---|---|---|
| CORE-005 (Conversation Manager) | State machine with 6 states, 8 transitions, concurrent access, SLA timers | Blocks AI pipeline and Agent inbox | Build incrementally: states first, then transitions, then concurrency, then SLA |
| AI-001 (PII Shield) | Presidio integration, custom patterns, accuracy tuning, performance | Affects every message; false positives block frontier models | Start with Presidio defaults; add custom patterns iteratively; build test suite with known PII samples |
| AI-002 (Model Router) | Complex routing logic (4 branches), circuit breaker, fallback chains | Determines cost and quality of every AI response | Implement routing as pure function first; add circuit breaker later; test with routing decision matrix |
| AI-005 (AI Engine) | Orchestrates 5+ sub-components; error handling at each step; streaming | Central to product value; any bug breaks the pipeline | Build pipeline as sequential steps first; add parallelism (PII + Vault) later; mock all dependencies |
| AI-007 (Confidence Scorer) | Heuristic design without ground truth; threshold tuning | Determines escalation rate (too high = poor UX; too low = high cost) | Start with simple heuristic; instrument with real data; plan A/B testing post-launch |
| AGENT-002 (Agent WebSocket) | Connection management, reconnection, multi-node broadcast, event filtering | Real-time UX depends on this; dropped events confuse agents | Use Redis pub/sub for multi-node; implement heartbeat; test with simulated network partitions |
| AGENT-005 (Compliance Engine) | Hash-chained audit log; GDPR workflows; data export/deletion across multiple tables | Legal requirement; errors could mean non-compliance | Implement hash chain with verification script; test export with known data; deletion test verifies zero traces |

### 10.2 External System Dependencies

| Dependency | Risk | Probability of Failure | Mitigation |
|---|---|---|---|
| WhatsApp Business API (Meta) | Account verification delay; API changes; rate limits | Medium | Mock adapter from Day 1; abstract behind ChannelAdapter interface; BSP alternative (Twilio/360dialog) |
| OpenAI API | Pricing changes; rate limits; service outages | Low-Medium | Circuit breaker; fallback to local model; cache common responses |
| Anthropic API | Same as OpenAI | Low-Medium | Same mitigation; multi-provider abstraction |
| ODW.ai Vault API | API contract changes; service downtime | Medium | Version-pinned client; Redis cache (10-min TTL); graceful degradation (AI without knowledge) |
| ODW.ai Auth (OIDC) | Service downtime; token format changes | Low | Reject unauthenticated requests; cache token validation (5-min TTL) |
| ODW.ai Billing API | Service downtime; license format changes | Low | Offline validation (embedded RSA key); 14-day grace period |
| Ollama/vLLM (local) | Model loading failures; GPU memory issues; hardware dependency | Medium | Health check on startup; fallback to frontier model; CPU-quantized model option |

### 10.3 Bottleneck Analysis

**Bottleneck 1: LLM Inference Latency (3–8s)**
- **Impact:** Customer wait time; perceived system slowness
- **Detection:** `desk_ai_inference_duration_seconds` metric; P95 > 10s alert
- **Mitigation:**
  - Prefer local model (lower latency than frontier API calls)
  - Implement streaming where supported (tokens arrive progressively)
  - Parallel workers (multiple AI consumers from processing queue)
  - Cache common questions (Vault cache + response cache)

**Bottleneck 2: PostgreSQL Write Throughput**
- **Impact:** Message persistence latency; audit log writes
- **Detection:** `pg_stat_statements`; connection pool utilization
- **Mitigation:**
  - PgBouncer connection pooling
  - Batch audit log writes (100ms buffer window)
  - Async message persistence (write-behind with Redis queue)
  - Read replicas for Agent Inbox queries

**Bottleneck 3: Vault Query Latency (cold: 500ms–1s)**
- **Impact:** Adds to total response time; affects customer experience
- **Detection:** `desk_vault_query_duration_seconds` metric
- **Mitigation:**
  - Redis cache (10-min TTL, >40% hit rate target)
  - Prefetch top-50 common queries (cron every 30 min)
  - Parallel execution: PII detection + Vault query run simultaneously

**Bottleneck 4: WebSocket Connection Scaling**
- **Impact:** Agent inbox stops receiving real-time updates
- **Detection:** Connected agent count; dropped message rate
- **Mitigation:**
  - Redis pub/sub for multi-node broadcast
  - Horizontal scaling of desk-api containers
  - Connection limit monitoring (~10K per node)

### 10.4 Risk Mitigation Strategies

**Strategy 1: Mocking (for external dependencies)**
- Implement mock adapters for ALL external services from Day 1
- Mock WhatsApp API: returns success/failure with configurable latency
- Mock LLM endpoints: return canned responses with configurable confidence
- Mock Vault API: return pre-indexed documents
- Mock Billing API: return configurable license states
- All mocks controlled via environment variables (`USE_MOCK_WHATSAPP=true`)

**Strategy 2: Parallel Scaffolding**
- Scaffold all modules simultaneously in Week 1 (empty files with interfaces)
- Define all interfaces (ChannelAdapter, ModelProvider, KnowledgeProvider) before implementations
- This allows parallel development without blocking on dependencies

**Strategy 3: Incremental Delivery**
- Each task produces a working, testable increment
- Demo-able after Phase 2: messages flow from WhatsApp to response (mock AI)
- Demo-able after Phase 3: AI responses grounded in knowledge base
- Demo-able after Phase 4: full agent workflow operational
- Production-ready after Phase 5: hardened, tested, observable

**Strategy 4: Feature Flags**
- PII Shield: can be disabled via configuration (`pii_shield_enabled: false`)
- Frontier models: can be disabled (local-only mode)
- Vault integration: can operate in degraded mode (no knowledge, disclaimer only)
- WhatsApp: can use web chat as primary channel during setup

---

## 11. Output Requirements

### 11.1 Detailed Task Specifications

---

#### EPIC 1: Environment & Project Setup

---

##### Task INFRA-001: Project Scaffolding & Tooling Configuration

**ID:** INFRA-001
**Title:** Project Scaffolding & Tooling Configuration
**Description:** Initialize the Python project structure with FastAPI application entry point, configuration management, dependency declarations, and development tooling (linting, type checking, testing).
**Inputs:** TSD §3.1 (Backend Stack), TSD §17 (File Structure), TSD §18 (Coding Standards)
**Output:** Complete project directory structure with all configuration files; FastAPI app that starts and returns health check.

**Subtasks:**

**INFRA-001a: Create Project Directory Structure**
- **Description:** Create all directories per TSD §17 file structure
- **Output:** Directory tree matching TSD §17 layout
- **Files:** All `__init__.py` files in src/desk/ subdirectories
- **Acceptance:** `find src/desk -name __init__.py` returns all expected modules
- **Effort:** S

**INFRA-001b: Configure pyproject.toml & requirements.txt**
- **Description:** Define project metadata, dependencies (FastAPI, SQLAlchemy, httpx, Pydantic, structlog, presidio, langchain, etc.), dev dependencies (pytest, mypy, ruff), and build configuration
- **Output:** `pyproject.toml` with all dependencies; `requirements.txt` generated
- **Acceptance:** `pip install -r requirements.txt` succeeds; all TSD §3.1 technologies included
- **Dependencies:** INFRA-001a
- **Effort:** S

**INFRA-001c: Create FastAPI Application Entry Point**
- **Description:** Create `src/desk/main.py` with FastAPI app instance, CORS middleware, router includes, startup/shutdown events, and health endpoint
- **Output:** `src/desk/main.py` — app starts on `uvicorn src.desk.main:app`
- **Acceptance:** `curl http://localhost:8000/health` returns `{"status": "healthy"}` (minimal)
- **Dependencies:** INFRA-001b
- **Effort:** M

**INFRA-001d: Implement Configuration Management (pydantic-settings)**
- **Description:** Create `src/desk/config.py` with Settings class using pydantic-settings; load from environment variables per TSD §10; include all required variables (DATABASE_URL, REDIS_URL, etc.)
- **Output:** `src/desk/config.py` with typed, validated settings
- **Acceptance:** Settings load from env vars; validation errors on missing required vars; defaults match TSD §10 dev examples
- **Dependencies:** INFRA-001b
- **Effort:** M

**INFRA-001e: Create Pydantic Schema Definitions**
- **Description:** Create `src/desk/schemas/api.py` with request/response models for all API endpoints per TSD §5; create `src/desk/schemas/channels.py` for channel-specific schemas (InboundMessage, OutboundMessage)
- **Output:** Schema files with all Pydantic models
- **Acceptance:** All TSD §5 request/response bodies represented as Pydantic models; validation works
- **Dependencies:** INFRA-001b
- **Effort:** M

**INFRA-001f: Configure Development Tooling**
- **Description:** Set up ruff (linting), mypy (type checking), pytest (testing) configuration in pyproject.toml; create `.env.example` with all required variables
- **Output:** Tooling configuration in pyproject.toml; `.env.example` file
- **Acceptance:** `ruff check src/` passes; `mypy src/` passes; `pytest --collect-only` works
- **Dependencies:** INFRA-001b
- **Effort:** S

**INFRA-001g: Create FastAPI Dependency Injection Module**
- **Description:** Create `src/desk/dependencies.py` with FastAPI Depends functions for database session, Redis client, event bus, settings, and auth verification
- **Output:** `src/desk/dependencies.py` with all dependency providers
- **Acceptance:** Dependencies injectable in route handlers; database session yields and closes properly
- **Dependencies:** INFRA-001c, INFRA-001d
- **Effort:** M

---

##### Task INFRA-002: Database Schema & Migrations

**ID:** INFRA-002
**Title:** Database Schema & Migrations
**Description:** Implement all SQLAlchemy models per TSD §4, configure Alembic for migrations, and create the initial migration with all tables, indexes, and constraints.
**Inputs:** TSD §4.1–4.7 (Entity Definitions), TSD §4.8 (Migration Strategy)
**Output:** All SQLAlchemy model files; initial Alembic migration; models create correct schema when migration runs.

**Subtasks:**

**INFRA-002a: Create SQLAlchemy Base & Mixins**
- **Description:** Create `src/desk/models/base.py` with SQLAlchemy declarative base, TimestampMixin (created_at, updated_at), and UUID primary key mixin
- **Output:** `src/desk/models/base.py`
- **Acceptance:** Base class usable by all models; mixins provide created_at/updated_at auto-update
- **Effort:** S

**INFRA-002b: Implement Customer Model**
- **Description:** Create `src/desk/models/customer.py` per TSD §4.1 — UUID PK, display_name, channel_identifiers (JSONB with GIN index), metadata (JSONB), timestamps
- **Output:** `src/desk/models/customer.py`
- **Acceptance:** Model matches TSD §4.1 schema exactly; GIN index on channel_identifiers; relationship to conversations defined
- **Effort:** S

**INFRA-002c: Implement Conversation Model**
- **Description:** Create `src/desk/models/conversation.py` per TSD §4.2 — all fields, composite indexes, unique constraint on (channel, channel_conversation_id), relationships to customer/messages/agent
- **Output:** `src/desk/models/conversation.py`
- **Acceptance:** All indexes from TSD §4.2 created; status enum validated; FK relationships correct
- **Effort:** S

**INFRA-002d: Implement Message Model**
- **Description:** Create `src/desk/models/message.py` per TSD §4.3 — all fields including PII flags, metadata JSONB, unique constraint on (conversation_id, channel_message_id)
- **Output:** `src/desk/models/message.py`
- **Acceptance:** Partial index on sender_type; unique dedup constraint; content/content_redacted fields
- **Effort:** S

**INFRA-002e: Implement Agent, AI Configuration, Audit Log, License State Models**
- **Description:** Create remaining model files per TSD §4.4–4.7 — agents (with user_id FK), ai_configurations (with encrypted API key BYTEA), audit_logs (with hash chain fields), license_state
- **Output:** `src/desk/models/agent.py`, `ai_configuration.py`, `audit_log.py`, `license_state.py`
- **Acceptance:** All fields match TSD schemas; audit_logs has previous_hash + hash fields; ai_configurations has frontier_api_key_encrypted BYTEA
- **Effort:** M

**INFRA-002f: Implement Field-Level Encryption Utility**
- **Description:** Create `src/desk/utils/encryption.py` with AES-256-GCM encrypt/decrypt functions for PII fields and API keys; key sourced from environment variable
- **Output:** `src/desk/utils/encryption.py`
- **Acceptance:** Encrypt → decrypt roundtrip preserves data; different plaintext produces different ciphertext; tampered ciphertext detected
- **Effort:** M

**INFRA-002g: Configure Alembic & Create Initial Migration**
- **Description:** Set up `alembic.ini` and `alembic/env.py` to auto-detect model changes; generate initial migration with all tables, indexes, constraints
- **Output:** `alembic.ini`, `alembic/env.py`, `alembic/versions/001_initial.py`
- **Acceptance:** `alembic upgrade head` on empty database creates all tables; `alembic downgrade base` drops all; schema matches TSD §4 exactly
- **Dependencies:** INFRA-002a through INFRA-002f
- **Effort:** M

**INFRA-002h: Write Model Unit Tests**
- **Description:** Create `tests/unit/test_models.py` testing model instantiation, validation, serialization, and relationship resolution
- **Output:** `tests/unit/test_models.py`
- **Acceptance:** All models instantiate with valid data; constraints reject invalid data; JSONB fields serialize/deserialize correctly
- **Dependencies:** INFRA-002g
- **Effort:** M

---

##### Task INFRA-003: Redis Configuration & Connection Management

**ID:** INFRA-003
**Title:** Redis Configuration & Connection Management
**Description:** Implement Redis connection pool, cache abstraction layer with TTL support, and key pattern helpers for all cache types defined in TSD §7.
**Inputs:** TSD §7 (State Management & Data Flow — Caching Layers), TSD §3.4 (Data Layer)
**Output:** Redis client module with connection pooling, cache get/set/delete with TTL, key pattern generators.

**Subtasks:**

**INFRA-003a: Implement Redis Connection Manager**
- **Description:** Create async Redis connection pool using `redis.asyncio`; configure connection parameters from Settings; implement health check
- **Output:** Redis connection module (part of dependencies or utils)
- **Acceptance:** Connection pool created on startup; health check returns ok/fail; connection released on shutdown
- **Effort:** S

**INFRA-003b: Implement Cache Abstraction Layer**
- **Description:** Create generic cache interface with get/set/delete operations; JSON serialization; TTL support; cache miss returns None
- **Output:** Cache utility class/module
- **Acceptance:** Set with TTL → get before TTL returns value; get after TTL returns None; delete removes key
- **Effort:** S

**INFRA-003c: Implement Cache Key Pattern Generators**
- **Description:** Create helper functions for all cache key patterns from TSD §7: `customer:{channel}:{hash}`, `vault:{collection}:{query_hash}`, `context:{conversation_id}`, `ai_config:{deployment_id}`
- **Output:** Key generator functions
- **Acceptance:** Keys match TSD §7 patterns exactly; identifier hashing uses SHA-256
- **Effort:** S

---

##### Task INFRA-004: Event Bus Implementation (Redis Streams)

**ID:** INFRA-004
**Title:** Event Bus Implementation (Redis Streams)
**Description:** Implement the event bus abstraction with Redis Streams backend, supporting publish/consume with partition keys, consumer groups, dead-letter queue, and at-least-once delivery guarantees.
**Inputs:** TSD §2.13 (Event Bus), TSD §8 (Background Jobs)
**Output:** Event bus module with Redis Streams implementation; event schema definitions; consumer group management.

**Subtasks:**

**INFRA-004a: Define Event Schemas**
- **Description:** Create `src/desk/events/schemas.py` with Pydantic models for all event types from TSD §2.13: inbound.message, outbound.message, conversation.state_changed, conversation.agent_assigned, ai.decision, audit.event, sla.breach
- **Output:** `src/desk/events/schemas.py`
- **Acceptance:** All 7 event types defined; each has correct payload structure; serialization to/from JSON works
- **Effort:** M

**INFRA-004b: Implement Event Bus Abstract Interface**
- **Description:** Create `src/desk/events/bus.py` with abstract EventBus class defining publish(), subscribe(), acknowledge(), dead_letter() methods
- **Output:** `src/desk/events/bus.py`
- **Acceptance:** Abstract interface defined; concrete implementations can extend it
- **Effort:** S

**INFRA-004c: Implement Redis Streams Backend**
- **Description:** Create `src/desk/events/redis_streams.py` implementing EventBus using Redis Streams; support consumer groups, partition keys (conversation_id), at-least-once delivery, acknowledgment
- **Output:** `src/desk/events/redis_streams.py`
- **Acceptance:** Publish adds to stream; consumer group receives messages; ack removes from pending; unacked messages redelivered
- **Dependencies:** INFRA-004a, INFRA-004b
- **Effort:** L

**INFRA-004d: Implement Dead-Letter Queue**
- **Description:** Add DLQ support: messages failing max retries (3x) move to DLQ stream; admin API to view DLQ depth and reprocess
- **Output:** DLQ functionality in redis_streams.py
- **Acceptance:** Failed messages move to DLQ after 3 retries; DLQ depth queryable; messages reprocessable
- **Dependencies:** INFRA-004c
- **Effort:** M

**INFRA-004e: Implement NATS JetStream Backend (Stub)**
- **Description:** Create `src/desk/events/nats.py` with stub implementation for Kubernetes deployments; raises NotImplementedError for now (to be completed in future sprint)
- **Output:** `src/desk/events/nats.py`
- **Acceptance:** File exists; class extends EventBus; methods raise NotImplementedError with clear message
- **Effort:** S

**INFRA-004f: Write Event Bus Unit Tests**
- **Description:** Create `tests/unit/test_event_bus.py` testing publish/consume/ack/DLQ with real Redis (testcontainers or Docker)
- **Output:** `tests/unit/test_event_bus.py`
- **Acceptance:** All event types publish/consume correctly; partition key ordering maintained; DLQ works after max retries
- **Dependencies:** INFRA-004c, INFRA-004d
- **Effort:** M

---

##### Task INFRA-005: Docker Development Environment

**ID:** INFRA-005
**Title:** Docker Development Environment
**Description:** Create Docker Compose configuration for local development with PostgreSQL, Redis, MinIO, and the desk-api service; include volume mounts for hot-reload.
**Inputs:** TSD §3.4 (Data Layer), TSD §3.5 (DevOps Tooling), TSD §15 (Deployment)
**Output:** `docker-compose.dev.yml` with all services; `.env.example` with defaults.

**Subtasks:**

**INFRA-005a: Create Development Docker Compose**
- **Description:** Create `docker-compose.dev.yml` with services: postgres (16+), redis (7+), minio (latest), desk-api (build from Dockerfile.api), with volume mounts, health checks, and dependency ordering
- **Output:** `docker-compose.dev.yml`
- **Acceptance:** `docker-compose -f docker-compose.dev.yml up` starts all services; PostgreSQL accessible on 5432; Redis on 6379; desk-api on 8000
- **Effort:** M

**INFRA-005b: Create Environment Example File**
- **Description:** Create `.env.example` with all required environment variables per TSD §10, using development defaults
- **Output:** `.env.example`
- **Acceptance:** All TSD §10 variables present; dev defaults match examples; copy to `.env` works with docker-compose
- **Effort:** S

**INFRA-005c: Create Development Dockerfile**
- **Description:** Create `Dockerfile.api` for development with hot-reload (uvicorn --reload); install dependencies; copy source; expose port 8000
- **Output:** `Dockerfile.api` (dev version)
- **Acceptance:** `docker build -t desk-api:dev .` succeeds; container starts and serves health endpoint
- **Effort:** M

**INFRA-005d: Verify Full Development Stack**
- **Description:** Test that `docker-compose up` starts everything; run migrations; verify health endpoint; verify Redis connectivity; verify PostgreSQL connectivity
- **Output:** Verified working development environment
- **Acceptance:** All services healthy; migrations run; health endpoint returns all checks "ok"
- **Dependencies:** INFRA-005a, INFRA-005b, INFRA-005c, INFRA-002g
- **Effort:** M

---

#### EPIC 2: Core Message Pipeline

---

##### Task CORE-001a: Channel Adapter Base & WhatsApp Business API Adapter

**ID:** CORE-001a
**Title:** Channel Adapter Base & WhatsApp Business API Adapter
**Description:** Implement the ChannelAdapter abstract interface and the WhatsApp Business API adapter including webhook receipt (POST), verification (GET), HMAC signature validation, message normalization to InboundMessage, and 24h window tracking.
**Inputs:** TSD §2.1 (Channel Gateway), TSD §5.1.1–5.1.2 (WhatsApp Webhook APIs), TSD §6.1 Step 1
**Output:** Channel adapter interface; WhatsApp Business API adapter with webhook endpoints; InboundMessage normalization.

**Subtasks:**

**CORE-001a-1: Define ChannelAdapter Abstract Interface**
- **Description:** Create `src/desk/channels/base.py` with abstract class defining: connect(), disconnect(), receive(), send(), health_check() methods; InboundMessage and OutboundMessage data classes; ChannelConfig schema
- **Output:** `src/desk/channels/base.py`
- **Acceptance:** Abstract interface covers all channel operations; concrete adapters can implement it
- **Effort:** S

**CORE-001a-2: Implement WhatsApp Webhook Verification (GET)**
- **Description:** Create GET endpoint at `/api/v1/webhooks/whatsapp` that verifies Meta's hub.mode, hub.verify_token, and returns hub.challenge
- **Output:** GET webhook verification endpoint
- **Acceptance:** Valid verify_token → returns challenge string (200); invalid token → 403
- **Effort:** S

**CORE-001a-3: Implement WhatsApp HMAC Signature Verification**
- **Description:** Implement HMAC-SHA256 signature verification for incoming POST webhooks using X-Hub-Signature-256 header and configured app secret
- **Output:** Signature verification function
- **Acceptance:** Valid signature passes; invalid signature returns 401 with INVALID_SIGNATURE error; missing header returns 401
- **Effort:** S

**CORE-001a-4: Implement WhatsApp Message Parsing & Normalization**
- **Description:** Parse Meta WhatsApp Cloud API webhook payload into canonical InboundMessage format; handle text messages, image messages, interactive responses; extract sender identifier, conversation ID, content, media URLs
- **Output:** WhatsApp message parser function
- **Acceptance:** Text message → InboundMessage with content; image message → InboundMessage with media_urls; all fields populated per InboundMessage schema
- **Effort:** M

**CORE-001a-5: Implement WhatsApp Webhook POST Endpoint**
- **Description:** Create POST endpoint at `/api/v1/webhooks/whatsapp` that verifies signature, parses messages, publishes inbound.message events, returns 200 within 5 seconds
- **Output:** POST webhook endpoint registered in FastAPI router
- **Acceptance:** Valid webhook → 200 with `{"status": "received", "message_count": N}`; invalid signature → 401; event published to bus
- **Dependencies:** CORE-001a-2, CORE-001a-3, CORE-001a-4, INFRA-004
- **Effort:** M

**CORE-001a-6: Implement WhatsApp 24h Window Tracking**
- **Description:** Track WhatsApp 24-hour conversation window per phone number; determine if outbound messages can be free-form or require template; store window expiry in conversation metadata
- **Output:** Window tracking logic in WhatsApp adapter
- **Acceptance:** Window starts on customer message; expires after 24h; outbound dispatcher checks window before sending
- **Effort:** M

**CORE-001a-7: Write WhatsApp Business API Adapter Unit Tests**
- **Description:** Create `tests/unit/test_whatsapp_business_adapter.py` with tests for signature verification, message parsing (text, image, interactive), deduplication, webhook endpoint behavior
- **Output:** `tests/unit/test_whatsapp_business_adapter.py`
- **Acceptance:** ≥15 test cases covering happy path, edge cases, error cases; all pass
- **Dependencies:** CORE-001a-5
- **Effort:** M

---

##### Task CORE-001b: WhatsApp Baileys Bridge Adapter

**ID:** CORE-001b
**Title:** WhatsApp Baileys Bridge Adapter
**Description:** Implement the WhatsApp Baileys Bridge adapter including Node.js sidecar setup, QR code pairing flow, session state persistence, auto-reconnection, and message normalization between Baileys and canonical format.
**Inputs:** TSD §2.1 (Channel Gateway), TSD §2.1.6 (WhatsApp Baileys Adapter API), TSD §2.1.7 (Database Schema)
**Output:** Node.js Baileys sidecar; Python Baileys adapter; QR code pairing API; session management.

**Subtasks:**

**CORE-001b-1: Set up Node.js Sidecar Container for Baileys Bridge**
- **Description:** Create `services/baileys-bridge/` directory with Node.js application using Baileys library; Dockerfile for sidecar container; package.json with baileys dependency
- **Output:** Node.js sidecar application scaffold
- **Acceptance:** Container builds successfully; baileys library installed; basic WebSocket server starts
- **Effort:** M

**CORE-001b-2: Implement Baileys WebSocket Client with Auto-Reconnect**
- **Description:** Implement Baileys client in Node.js sidecar with WebSocket connection to WhatsApp Web protocol; exponential backoff reconnection logic; connection state management
- **Output:** Baileys WebSocket client with reconnection
- **Acceptance:** Connects to WhatsApp Web; auto-reconnects on connection loss with exponential backoff (1s, 5s, 30s, max 5min)
- **Effort:** L

**CORE-001b-3: Implement QR Code Generation and Pairing Flow**
- **Description:** Create REST API endpoint in Node.js sidecar to generate QR code for WhatsApp pairing; return QR code as data URL or pairing code; handle pairing completion event
- **Output:** QR code generation endpoint (`POST /pair`)
- **Acceptance:** Returns QR code data URL; pairing completes when user scans; session established
- **Effort:** M

**CORE-001b-4: Implement Session State Persistence in Redis**
- **Description:** Store WhatsApp Baileys session state (auth credentials, chat history) in Redis with encryption; persist across container restarts; implement session expiry (30 days)
- **Output:** Redis session storage with encryption
- **Acceptance:** Session persists across restarts; expires after 30 days; credentials encrypted at rest
- **Effort:** M

**CORE-001b-5: Implement Python WhatsAppBaileysAdapter**
- **Description:** Create `src/desk/channels/whatsapp_baileys.py` implementing ChannelAdapter interface; calls Node.js sidecar via internal REST/WebSocket; normalizes messages to InboundMessage format
- **Output:** Python Baileys adapter
- **Acceptance:** Implements ChannelAdapter interface; receives messages from sidecar; publishes to event bus
- **Dependencies:** CORE-001b-1, CORE-001b-2, INFRA-006
- **Effort:** M

**CORE-001b-6: Implement Message Normalization (Inbound/Outbound)**
- **Description:** Normalize Baileys message format to Desk's canonical InboundMessage/OutboundMessage; handle text, image, audio, video, document messages; extract metadata
- **Output:** Message normalization functions
- **Acceptance:** All message types normalized correctly; metadata preserved; media URLs extracted
- **Effort:** M

**CORE-001b-7: Implement Reconnection Logic with Exponential Backoff**
- **Description:** Implement reconnection logic in Python adapter when Node.js sidecar is unavailable; exponential backoff; admin notification on max retries exceeded
- **Output:** Reconnection logic with backoff
- **Acceptance:** Retries with exponential backoff; notifies admin after 10 failed attempts; logs all reconnection attempts
- **Effort:** S

**CORE-001b-8: Implement Session Expiry and Refresh Mechanism**
- **Description:** Check session expiry (30 days); notify admin 7 days before expiry; provide refresh endpoint to extend session without re-pairing
- **Output:** Session expiry handling
- **Acceptance:** Admin notified before expiry; session refreshes without re-pairing; expired session requires re-pairing
- **Effort:** S

**CORE-001b-9: Write Baileys Adapter Integration Tests**
- **Description:** Create `tests/integration/test_whatsapp_baileys_adapter.py` with mock Baileys sidecar; test pairing flow, message receipt, reconnection, session expiry
- **Output:** Integration tests
- **Acceptance:** ≥10 test cases; mock sidecar simulates WhatsApp Web; all pass
- **Dependencies:** CORE-001b-5, CORE-001b-6
- **Effort:** M

**CORE-001b-10: End-to-End Test: Send/Receive WhatsApp Message via Baileys**
- **Description:** Create E2E test that pairs Baileys bridge (using test WhatsApp number), sends message, receives response, verifies message flow through entire pipeline
- **Output:** E2E test
- **Acceptance:** Message sent via Baileys; processed by AI; response sent back; conversation persisted
- **Dependencies:** CORE-001b-9, DEPLOY-003
- **Effort:** L

---

##### Task CORE-002: Web Chat Adapter (WebSocket)

**ID:** CORE-002
**Title:** Web Chat Adapter (WebSocket)
**Description:** Implement the web chat WebSocket adapter including session management, embed script serving, message exchange protocol, and connection lifecycle.
**Inputs:** TSD §2.1 (WebChatAdapter), TSD §5.1.3 (Web Chat WebSocket)
**Output:** WebSocket endpoint for web chat; session token management; embed script.

**Subtasks:**

**CORE-002a: Implement WebSocket Connection Handler**
- **Description:** Create WebSocket endpoint at `/api/v1/webhooks/chat`; handle connection, authentication (session token), message receipt, and disconnection
- **Output:** WebSocket handler in `src/desk/channels/webchat.py`
- **Acceptance:** Client connects with session token; sends chat_message; receives ai_response; connection closes cleanly
- **Effort:** M

**CORE-002b: Implement Session Token Management**
- **Description:** Generate and validate session tokens for web chat; store in Redis with TTL; create new session on first connection
- **Output:** Session management functions
- **Acceptance:** New session created on first connect; existing session validated; expired session rejected
- **Effort:** S

**CORE-002c: Implement Message Normalization for Web Chat**
- **Description:** Convert WebSocket chat_message payloads to InboundMessage format; convert OutboundMessage to WebSocket response format
- **Output:** Web chat message parser/formatter
- **Acceptance:** chat_message → InboundMessage; OutboundMessage → ai_response WebSocket payload
- **Effort:** S

**CORE-002d: Create Embeddable Widget Script**
- **Description:** Create `frontend/public/widget.js` — lightweight JavaScript snippet that operators embed on their website; creates chat iframe/widget; connects to WebSocket endpoint
- **Output:** `frontend/public/widget.js`
- **Acceptance:** Script loads on any website; creates chat widget; sends/receives messages via WebSocket
- **Effort:** M

---

##### Task CORE-003: Email Adapter (IMAP/SMTP)

**ID:** CORE-003
**Title:** Email Adapter (IMAP/SMTP)
**Description:** Implement the email channel adapter with IMAP polling for inbound emails, MIME parsing, SMTP relay for outbound, and threading via In-Reply-To/References headers.
**Inputs:** TSD §2.1 (EmailAdapter), TSD §9 (External Integrations)
**Output:** IMAP fetch loop; MIME parser; SMTP sender; email-to-InboundMessage conversion.

**Subtasks:**

**CORE-003a: Implement IMAP Fetch Loop**
- **Description:** Create background task that polls IMAP server every 30 seconds; fetches unseen emails; marks as seen after processing; handles connection errors gracefully
- **Output:** IMAP polling function in `src/desk/channels/email.py`
- **Acceptance:** Fetches new emails; processes them; marks as seen; reconnects on failure
- **Effort:** M

**CORE-003b: Implement MIME Parsing & Normalization**
- **Description:** Parse email MIME structure; extract text body (plain/html), attachments; convert to InboundMessage format; use In-Reply-To/References for thread identification
- **Output:** Email MIME parser
- **Acceptance:** Plain text email → InboundMessage; HTML email → text extracted; attachments → media_urls; threading via headers
- **Effort:** M

**CORE-003c: Implement SMTP Outbound Sender**
- **Description:** Send outbound messages via SMTP; format as email with proper From/To/Subject/In-Reply-To headers; handle HTML and plain text
- **Output:** SMTP send function
- **Acceptance:** OutboundMessage → email sent via SMTP; threading headers preserved; delivery confirmation logged
- **Effort:** M

---

##### Task CORE-004: Message Router & Customer Resolver

**ID:** CORE-004
**Title:** Message Router & Customer Resolver
**Description:** Implement the message routing module that consumes inbound.message events, resolves or creates customer profiles (Redis cache → PostgreSQL fallback), loads or creates conversations, checks conversation state, and dispatches to AI pipeline or agent queue.
**Inputs:** TSD §2.2 (Message Router), TSD §6.1 Step 2
**Output:** MessageRouter consumer; CustomerResolver with cache; PipelineDispatcher.

**Subtasks:**

**CORE-004a: Implement Customer Resolver**
- **Description:** Create `src/desk/router/customer_resolver.py` — lookup customer by channel identifier: check Redis cache (`customer:{channel}:{hash}`) → query PostgreSQL `customers.channel_identifiers` (JSONB GIN) → create new customer if not found → cache result
- **Output:** CustomerResolver class
- **Acceptance:** Cache hit returns customer without DB query; cache miss queries DB; new customer created and cached; hash uses SHA-256 of identifier
- **Effort:** M

**CORE-004b: Implement Conversation Loading/Creation**
- **Description:** Load existing conversation by (channel, channel_conversation_id) or create new; handle edge cases: closed conversation → new conversation for returning customer; pending → active transition
- **Output:** Conversation loading/creation logic in message_router.py
- **Acceptance:** Existing conversation loaded; new conversation created with status=new; closed → new conversation; pending → active
- **Effort:** M

**CORE-004c: Implement Pipeline Dispatch Logic**
- **Description:** Route based on conversation state: escalated+assigned → agent queue (skip AI); active+ai_enabled → AI pipeline; new → AI pipeline; closed → error
- **Output:** PipelineDispatcher logic
- **Acceptance:** Correct routing for each state; ProcessRequest published to processing queue for AI path
- **Effort:** M

**CORE-004d: Implement Message Router Event Consumer**
- **Description:** Create event consumer that subscribes to `inbound.message` stream; orchestrates customer resolution → conversation loading → message persistence → SLA timer start → pipeline dispatch
- **Output:** MessageRouter consumer registered with event bus
- **Acceptance:** Consumes inbound.message; full flow executes; ProcessRequest published; message persisted to DB
- **Dependencies:** CORE-004a, CORE-004b, CORE-004c, INFRA-004
- **Effort:** L

**CORE-004e: Implement Message Deduplication**
- **Description:** Check for duplicate messages using channel_message_id before processing; use unique constraint on (conversation_id, channel_message_id)
- **Output:** Deduplication check in message router
- **Acceptance:** Duplicate webhook delivery → only one message processed; second attempt returns early
- **Effort:** S

**CORE-004f: Write Message Router Unit Tests**
- **Description:** Create `tests/unit/test_message_router.py` and `test_customer_resolver.py` with tests for cache hit/miss, customer creation, conversation loading, state-based routing, deduplication
- **Output:** Test files
- **Acceptance:** ≥20 test cases; all pass; mock Redis and PostgreSQL
- **Dependencies:** CORE-004d
- **Effort:** M

---

##### Task CORE-005: Conversation Manager & State Machine

**ID:** CORE-005
**Title:** Conversation Manager & State Machine
**Description:** Implement the conversation state machine (6 states, 8 transitions), message persistence with deduplication, multi-turn context management, and conversation CRUD operations.
**Inputs:** TSD §2.3 (Conversation Manager), TSD §6.1–6.2 (Business Logic)
**Output:** ConversationManager; StateMachine; MessageStore; ContextManager.

**Subtasks:**

**CORE-005a: Implement Conversation State Machine**
- **Description:** Create `src/desk/conversations/state_machine.py` with all valid transitions per TSD §2.3: new→active, active→pending, active→escalated, escalated→active, active→resolved, resolved→closed, pending→active, pending→closed. Invalid transitions raise error.
- **Output:** StateMachine class with transition method
- **Acceptance:** All 8 valid transitions succeed; invalid transitions (e.g., closed→active) raise StateTransitionError; events published on transition
- **Effort:** M

**CORE-005b: Implement Message Store**
- **Description:** Create message persistence with deduplication (channel_message_id unique constraint); append-only; store PII metadata; batch insert support
- **Output:** MessageStore class
- **Acceptance:** Messages persisted with all fields; duplicate channel_message_id rejected; batch insert works
- **Effort:** M

**CORE-005c: Implement Context Manager**
- **Description:** Maintain sliding window of recent messages for AI context; load from PostgreSQL or Redis cache; configurable window size (default: last 10 turns)
- **Output:** ContextManager class
- **Acceptance:** Returns last N messages for conversation; cache hit avoids DB query; cache invalidated on new message
- **Effort:** M

**CORE-005d: Implement Conversation Manager Orchestrator**
- **Description:** Create `src/desk/conversations/manager.py` that coordinates state machine, message store, and context manager; provides high-level operations: create_conversation, add_message, transition_state, get_conversation
- **Output:** ConversationManager class
- **Acceptance:** Full lifecycle works: create → add messages → transition → resolve → close
- **Dependencies:** CORE-005a, CORE-005b, CORE-005c
- **Effort:** L

**CORE-005e: Handle Concurrent State Transitions**
- **Description:** Implement optimistic locking or SELECT FOR UPDATE to prevent race conditions when multiple workers try to transition the same conversation
- **Output:** Concurrency protection in ConversationManager
- **Acceptance:** Two simultaneous takeover attempts → one succeeds, one gets 409 Conflict; no lost updates
- **Effort:** M

**CORE-005f: Write Conversation Manager Unit Tests**
- **Description:** Create `tests/unit/test_conversation_manager.py` and `test_state_machine.py` with comprehensive tests for all transitions, edge cases, concurrent access
- **Output:** Test files
- **Acceptance:** ≥25 test cases; all state transitions tested; concurrency test passes
- **Dependencies:** CORE-005d, CORE-005e
- **Effort:** L

---

##### Task CORE-006: SLA Timer & Enforcement

**ID:** CORE-006
**Title:** SLA Timer & Enforcement
**Description:** Implement SLA tracking for first-response time and resolution time; background job that checks for breaches every 60 seconds; publish sla.breach events.
**Inputs:** TSD §2.3 (SLATimer), TSD §8 (Background Jobs — SLA timer check)
**Output:** SLA timer logic; background cron job; breach event publishing.

**Subtasks:**

**CORE-006a: Implement SLA Timer Logic**
- **Description:** Create `src/desk/conversations/sla.py` — set first_response_due and resolution_due on conversation creation; check breach status; calculate remaining time
- **Output:** SLATimer class
- **Acceptance:** Timers set correctly on conversation creation; breach detected when current_time > due; remaining time calculated
- **Effort:** M

**CORE-006b: Implement SLA Background Check Job**
- **Description:** Create cron job (every 60s) that scans active/escalated conversations; identifies breached SLAs; publishes sla.breach events; emits sla_warning via WebSocket to agents
- **Output:** SLA check background job
- **Acceptance:** Job runs every 60s; breached conversations detected; events published; agents notified
- **Dependencies:** CORE-006a, INFRA-004
- **Effort:** M

---

##### Task CORE-007: Outbound Dispatcher

**ID:** CORE-007
**Title:** Outbound Dispatcher
**Description:** Implement the outbound message delivery system that consumes outbound.message events, formats for target channel, delivers via channel API, and handles retries with exponential backoff.
**Inputs:** TSD §2.1 (OutboundDispatcher), TSD §6.1 Step 4
**Output:** OutboundDispatcher consumer; channel-specific formatting; retry logic.

**Subtasks:**

**CORE-007a: Implement Outbound Event Consumer**
- **Description:** Subscribe to `outbound.message` stream; deserialize OutboundMessage; route to appropriate channel adapter for delivery
- **Output:** OutboundDispatcher consumer
- **Acceptance:** Consumes outbound events; routes to correct channel; delivery attempted
- **Effort:** M

**CORE-007b: Implement Channel-Specific Formatting**
- **Description:** Format OutboundMessage for each channel: WhatsApp (text API, template if outside window), Web Chat (WebSocket push), Email (SMTP with threading headers)
- **Output:** Channel formatting functions
- **Acceptance:** WhatsApp format correct; web chat WebSocket push works; email formatted correctly
- **Effort:** M

**CORE-007c: Implement Retry Logic with Exponential Backoff**
- **Description:** On delivery failure: retry 3x with exponential backoff (1s, 5s, 30s); after all retries fail → move to dead-letter queue; notify admin after 1 hour
- **Output:** Retry wrapper around delivery
- **Acceptance:** First retry after 1s; second after 5s; third after 30s; DLQ after all fail; admin notification sent
- **Effort:** M

**CORE-007d: Implement Delivery Confirmation & Logging**
- **Description:** Log delivery success/failure; update message metadata with delivery status; publish audit event
- **Output:** Delivery confirmation logic
- **Acceptance:** Successful delivery logged; failed delivery logged with error; audit trail updated
- **Effort:** S

---

#### EPIC 3: AI Intelligence Pipeline

---

##### Task AI-001: PII Shield (Detection & Redaction)

**ID:** AI-001
**Title:** PII Shield (Detection & Redaction)
**Description:** Implement PII detection using Microsoft Presidio with custom pattern support, PII redaction with placeholder replacement, and routing directive generation based on PII presence and admin policy.
**Inputs:** TSD §2.5 (PII Shield), TSD §6.4 (PII Detection and Routing Decision)
**Output:** PIIDetector; PIIRedactor; RoutingPolicy; integrated PII Shield module.

**Subtasks:**

**AI-001a: Integrate Presidio Analyzer**
- **Description:** Set up Microsoft Presidio with NER models; configure entity recognizers for all PII types from TSD §2.5 (PERSON, PHONE_NUMBER, EMAIL_ADDRESS, STREET_ADDRESS, DATE_OF_BIRTH, MEDICAL_LICENSE, CREDIT_CARD, IBAN, US_SSN, PASSPORT, NATIONAL_ID); set confidence threshold to 0.85
- **Output:** Presidio analyzer instance configured
- **Acceptance:** Detects all listed PII types; confidence threshold filters low-confidence matches; performance acceptable (<100ms per message)
- **Effort:** M

**AI-001b: Implement Custom Pattern Support**
- **Description:** Load operator-defined regex patterns from ai_configurations.pii_shield_custom_patterns; integrate with Presidio as custom recognizers; support patterns for patient IDs, policy numbers, etc.
- **Output:** Custom pattern loader and recognizer
- **Acceptance:** Custom patterns detected alongside Presidio entities; patterns loaded from DB config; patterns updateable without restart
- **Effort:** M

**AI-001c: Implement PII Redaction**
- **Description:** Replace detected PII spans with type placeholders (e.g., `[PERSON]`, `[PHONE_NUMBER]`, `[EMAIL_ADDRESS]`); preserve message structure; handle overlapping entities
- **Output:** PIIRedactor class
- **Acceptance:** "My name is John and phone is 555-1234" → "My name is [PERSON] and phone is [PHONE_NUMBER]"; overlapping entities handled correctly
- **Effort:** M

**AI-001d: Implement Routing Policy**
- **Description:** Determine routing directive based on PII detection result and admin configuration: no PII → NO_RESTRICTION; PII + frontier_allowed_with_redaction → REDACTED_FRONTIER_OK; PII + not allowed → LOCAL_MODEL_ONLY
- **Output:** RoutingPolicy class
- **Acceptance:** All three directives generated correctly based on inputs; admin policy respected
- **Effort:** S

**AI-001e: Implement Log PII Filter**
- **Description:** Create `src/desk/utils/pii_filter.py` — structlog processor that redacts PII from all log output before emission; prevents PII leakage in logs
- **Output:** `src/desk/utils/pii_filter.py`
- **Acceptance:** Log output containing phone numbers, emails, names → redacted; filter applies to all log levels
- **Effort:** M

**AI-001f: Integrate PII Shield Module**
- **Description:** Create `src/desk/ai/pii_shield.py` that combines detector + redactor + routing policy into single `analyze(text, config) → PIIResult` interface
- **Output:** `src/desk/ai/pii_shield.py`
- **Acceptance:** Single function call returns {pii_detected, pii_types, redacted_text, routing_directive}; disabled via config skips analysis
- **Dependencies:** AI-001a, AI-001b, AI-001c, AI-001d
- **Effort:** M

**AI-001g: Write PII Shield Unit Tests**
- **Description:** Create `tests/unit/test_pii_shield.py` with test cases for each PII type, custom patterns, redaction accuracy, routing directives, disabled mode
- **Output:** `tests/unit/test_pii_shield.py`
- **Acceptance:** ≥20 test cases; all PII types tested; redaction verified character-by-character; routing directives correct
- **Dependencies:** AI-001f
- **Effort:** M

---

##### Task AI-002: Model Router (Selection & Fallback)

**ID:** AI-002
**Title:** Model Router (Selection & Fallback)
**Description:** Implement model selection logic based on PII directive, complexity scoring, and admin routing policy. Include circuit breaker integration and fallback chain resolution.
**Inputs:** TSD §2.6 (Model Router), TSD §6.1 Step 3b–3c
**Output:** ComplexityScorer; PolicyEvaluator; FallbackManager; ModelRouter module.

**Subtasks:**

**AI-002a: Implement Complexity Scorer**
- **Description:** Create heuristic complexity scoring (0.0–1.0) per TSD §6.1 Step 3b: message_length/500 (cap 0.3) + question marks (+0.2) + context depth >5 turns (+0.2) + media (+0.1) + no Vault results (+0.2); cap at 1.0
- **Output:** ComplexityScorer class
- **Acceptance:** Score calculated correctly for various inputs; cap at 1.0; each factor contributes correctly
- **Effort:** M

**AI-002b: Implement Policy Evaluator**
- **Description:** Apply routing rules per TSD §6.1 Step 3c: PII directive + admin policy → target model selection; implement all 4 routing branches
- **Output:** PolicyEvaluator class
- **Acceptance:** All 4 branches produce correct target model; admin policy overrides applied
- **Effort:** M

**AI-002c: Implement Circuit Breaker**
- **Description:** Per-model-endpoint circuit breaker: CLOSED (normal) → OPEN (after N failures in time window) → HALF_OPEN (test one request); prevent routing to unhealthy models
- **Output:** CircuitBreaker class
- **Acceptance:** Opens after 3 failures in 60s; half-open after 30s cooldown; closes on successful test; per-endpoint state
- **Effort:** M

**AI-002d: Implement Fallback Chain Resolution**
- **Description:** Given target model + circuit breaker state, resolve fallback chain: try target → if OPEN try next → if all OPEN escalate to human
- **Output:** FallbackManager class
- **Acceptance:** Returns ordered list of available models; respects circuit breaker state; final fallback is always escalate
- **Effort:** M

**AI-002e: Integrate Model Router Module**
- **Description:** Create `src/desk/ai/model_router.py` combining scorer + evaluator + fallback into `route(pii_directive, complexity_score, context, config) → RoutingDecision`
- **Output:** `src/desk/ai/model_router.py`
- **Acceptance:** Single function returns {model_endpoint, model_name, fallback_chain, use_redacted_text}
- **Dependencies:** AI-002a, AI-002b, AI-002c, AI-002d
- **Effort:** M

**AI-002f: Write Model Router Unit Tests**
- **Description:** Create `tests/unit/test_model_router.py` testing all routing branches, complexity scoring, circuit breaker states, fallback chains
- **Output:** `tests/unit/test_model_router.py`
- **Acceptance:** ≥15 test cases; routing matrix fully covered; circuit breaker transitions tested
- **Dependencies:** AI-002e
- **Effort:** M

---

##### Task AI-003: Vault Client (Knowledge Retrieval & Caching)

**ID:** AI-003
**Title:** Vault Client (Knowledge Retrieval & Caching)
**Description:** Implement the Vault API client for knowledge base retrieval with Redis caching, result ranking, and graceful degradation when Vault is unavailable.
**Inputs:** TSD §2.7 (Vault Client), TSD §6.1 Step 3d, TSD §9 (External Integrations — Vault)
**Output:** VaultAPIClient; CacheManager; ResultRanker; integrated VaultClient module.

**Subtasks:**

**AI-003a: Implement Vault HTTP Client**
- **Description:** Create async HTTP client (httpx) for Vault retrieval API: `POST {vault_url}/api/v1/collections/{collection_id}/retrieve` with body `{"query": text, "top_k": 5}`; authenticate with Bearer token; handle timeouts (10s)
- **Output:** VaultAPIClient class
- **Acceptance:** Correct HTTP request format; response parsed to document list; timeout handled; auth header included
- **Effort:** M

**AI-003b: Implement Redis Cache for Vault Results**
- **Description:** Cache Vault query results in Redis with key pattern `vault:{collection_id}:{query_hash}` and TTL 10 minutes; check cache before HTTP call; store on cache miss
- **Output:** Cache integration in VaultClient
- **Acceptance:** Cache hit returns stored results without HTTP call; cache miss → HTTP call → store in cache; TTL respected
- **Effort:** M

**AI-003c: Implement Result Ranking & Filtering**
- **Description:** Filter Vault results: only include chunks with relevance_score > 0.5; sort by score descending; limit to top_k results
- **Output:** ResultRanker class
- **Acceptance:** Low-relevance chunks filtered; results sorted by score; top_k limit applied
- **Effort:** S

**AI-003d: Implement Graceful Degradation**
- **Description:** When Vault API is unavailable: log warning; return empty document list; AI proceeds with general knowledge + disclaimer ("I may not have the most up-to-date information...")
- **Output:** Degradation handling in VaultClient
- **Acceptance:** Vault timeout → empty results + warning logged; AI pipeline continues without knowledge
- **Effort:** S

**AI-003e: Integrate Vault Client Module**
- **Description:** Create `src/desk/ai/vault_client.py` combining HTTP client + cache + ranking into `retrieve(query, collection_id, top_k) → RetrievalResult`
- **Output:** `src/desk/ai/vault_client.py`
- **Acceptance:** Single function returns {documents: [{content, score, source_id, metadata}]}
- **Dependencies:** AI-003a, AI-003b, AI-003c, AI-003d
- **Effort:** M

**AI-003f: Write Vault Client Unit Tests**
- **Description:** Create `tests/unit/test_vault_client.py` with mock Vault server; test cache hit/miss, filtering, degradation, timeout handling
- **Output:** `tests/unit/test_vault_client.py`
- **Acceptance:** ≥12 test cases; mock server returns canned responses; cache behavior verified
- **Dependencies:** AI-003e
- **Effort:** M

---

##### Task AI-004: LLM Provider Abstraction & Implementations

**ID:** AI-004
**Title:** LLM Provider Abstraction & Implementations
**Description:** Implement the model provider interface and concrete implementations for Ollama/vLLM (local), OpenAI, and Anthropic. Support streaming, token counting, and consistent response format.
**Inputs:** TSD §3.3 (AI/ML Stack), TSD §6.1 Step 3e, TSD §9 (External Integrations — LLM APIs)
**Output:** ModelProvider interface; OllamaProvider; OpenAIProvider; AnthropicProvider.

**Subtasks:**

**AI-004a: Define ModelProvider Abstract Interface**
- **Description:** Create `src/desk/ai/providers/base.py` with abstract class: `complete(messages, model, temperature, max_tokens) → CompletionResult`; `complete_stream(...)` for streaming; CompletionResult includes content, usage (tokens), logprobs (optional)
- **Output:** `src/desk/ai/providers/base.py`
- **Acceptance:** Interface covers all provider operations; consistent return type across providers
- **Effort:** S

**AI-004b: Implement Ollama/vLLM Provider**
- **Description:** Create `src/desk/ai/providers/ollama.py` — HTTP client for Ollama REST API (`POST /api/chat`); support streaming; handle model loading errors; configurable endpoint
- **Output:** `src/desk/ai/providers/ollama.py`
- **Acceptance:** Sends correct request format; parses response; streaming works; timeout handled; connection error handled
- **Effort:** M

**AI-004c: Implement OpenAI Provider**
- **Description:** Create `src/desk/ai/providers/openai.py` — HTTP client for OpenAI Chat Completions API; support streaming; extract logprobs if available; handle rate limits (429)
- **Output:** `src/desk/ai/providers/openai.py`
- **Acceptance:** Correct API format; logprobs extracted; rate limit → retry with backoff; streaming works
- **Effort:** M

**AI-004d: Implement Anthropic Provider**
- **Description:** Create `src/desk/ai/providers/anthropic.py` — HTTP client for Anthropic Messages API; different request format (system separate from messages); handle x-api-key auth
- **Output:** `src/desk/ai/providers/anthropic.py`
- **Acceptance:** Correct API format (system as separate param); auth header correct; response parsed to CompletionResult
- **Effort:** M

**AI-004e: Implement Provider Registry**
- **Description:** Create factory/registry that instantiates correct provider based on configuration (local_model_endpoint → Ollama; frontier_provider=openai → OpenAI; frontier_provider=anthropic → Anthropic)
- **Output:** Provider registry/factory
- **Acceptance:** Correct provider instantiated for each config; invalid provider raises error
- **Effort:** S

**AI-004f: Write LLM Provider Unit Tests**
- **Description:** Create `tests/unit/test_llm_providers.py` with mock HTTP endpoints; test each provider's request format, response parsing, error handling, streaming
- **Output:** `tests/unit/test_llm_providers.py`
- **Acceptance:** ≥15 test cases; each provider tested; mock responses match real API format
- **Dependencies:** AI-004b, AI-004c, AI-004d
- **Effort:** M

---

##### Task AI-005: AI Engine Orchestrator (Pipeline)

**ID:** AI-005
**Title:** AI Engine Orchestrator (Pipeline)
**Description:** Implement the main AI Engine that orchestrates the full RAG pipeline: consume ProcessRequest → PII Shield → Model Router → Vault Client → Prompt Builder → LLM Inference → Confidence Scorer → Response/Escalation.
**Inputs:** TSD §2.4 (AI Engine), TSD §6.1 Step 3 (full pipeline)
**Output:** AI Engine orchestrator; pipeline step coordination; error handling at each step.

**Subtasks:**

**AI-005a: Implement Pipeline Orchestrator**
- **Description:** Create `src/desk/ai/engine.py` with PipelineOrchestrator that executes steps 3a–3f sequentially; each step receives output of previous; handles errors at each step with fallback behavior
- **Output:** PipelineOrchestrator class
- **Acceptance:** Full pipeline executes end-to-end; each step receives correct input; errors handled per TSD §6.1 failure handling
- **Effort:** L

**AI-005b: Implement ProcessRequest Consumer**
- **Description:** Create event consumer that subscribes to processing queue; deserializes ProcessRequest; invokes PipelineOrchestrator; handles result (publish outbound or escalation)
- **Output:** AI Engine event consumer
- **Acceptance:** Consumes ProcessRequest; pipeline runs; result published correctly
- **Dependencies:** AI-005a, INFRA-004
- **Effort:** M

**AI-005c: Implement Parallel Execution (PII + Vault)**
- **Description:** Optimize: run PII Shield and Vault Client in parallel (they're independent); join results before Model Router (which needs PII directive)
- **Output:** Parallel execution in pipeline
- **Acceptance:** PII and Vault run concurrently; total latency reduced; results joined correctly
- **Effort:** M

**AI-005d: Implement Error Handling & Fallback**
- **Description:** Per TSD §6.1 failure handling: PII Shield failure → fail-open; Vault failure → proceed without knowledge; model timeout → circuit breaker + fallback; all models down → escalate
- **Output:** Error handling throughout pipeline
- **Acceptance:** Each failure mode handled correctly; system never crashes; degraded service continues
- **Effort:** M

**AI-005e: Implement Audit Logging for AI Decisions**
- **Description:** Log every AI decision to audit trail: model used, confidence score, routing decision, Vault sources, PII detected, escalation reason
- **Output:** AI decision audit logging
- **Acceptance:** Every inference logged; all metadata captured; audit log queryable
- **Effort:** M

**AI-005f: Write AI Engine Unit Tests**
- **Description:** Create `tests/unit/test_ai_engine.py` with mocked sub-components; test happy path, each failure mode, parallel execution, audit logging
- **Output:** `tests/unit/test_ai_engine.py`
- **Acceptance:** ≥15 test cases; all failure modes tested; mock PII/Vault/LLM
- **Dependencies:** AI-005a
- **Effort:** L

---

##### Task AI-006: Prompt Builder & Response Formatter

**ID:** AI-006
**Title:** Prompt Builder & Response Formatter
**Description:** Implement prompt construction (system + knowledge + context + user message) and response formatting for channel-specific delivery (WhatsApp buttons, web chat markdown, etc.).
**Inputs:** TSD §2.4 (PromptBuilder, ResponseFormatter), TSD §6.1 Step 3e
**Output:** PromptBuilder; ResponseFormatter.

**Subtasks:**

**AI-006a: Implement Prompt Builder**
- **Description:** Create `src/desk/ai/prompt_builder.py` — construct LLM prompt from: system_prompt (from config), knowledge (formatted Vault documents with source attribution), context (last N messages), customer metadata, user message (or redacted version)
- **Output:** PromptBuilder class
- **Acceptance:** Prompt includes all sections; Vault sources attributed; context truncated to last 10 turns; redacted text used when routing requires
- **Effort:** M

**AI-006b: Implement Token Budget Management**
- **Description:** Manage prompt size within model context window: truncate conversation context; compress system prompt; select highest-relevance Vault chunks; estimate token count
- **Output:** Token budget logic in PromptBuilder
- **Acceptance:** Prompt stays within model's context window; most important content preserved; token count estimated
- **Effort:** M

**AI-006c: Implement Response Formatter**
- **Description:** Format AI output for channel-specific delivery: WhatsApp (text, interactive buttons if applicable), Web Chat (markdown supported), Email (HTML formatting)
- **Output:** ResponseFormatter class
- **Acceptance:** WhatsApp format correct (no markdown if unsupported); web chat preserves markdown; email formatted as HTML
- **Effort:** M

---

##### Task AI-007: Confidence Scorer & Decision Engine

**ID:** AI-007
**Title:** Confidence Scorer & Decision Engine
**Description:** Implement confidence scoring (using logprobs or heuristic) and the decision engine that determines whether to deliver AI response or escalate to human.
**Inputs:** TSD §2.4 (ConfidenceScorer), TSD §6.1 Step 3f
**Output:** ConfidenceScorer; DecisionEngine.

**Subtasks:**

**AI-007a: Implement Logprob-Based Confidence**
- **Description:** When model provides logprobs: calculate average token probability across response; convert to 0.0–1.0 confidence score
- **Output:** Logprob confidence calculator
- **Acceptance:** Average logprob calculated correctly; converted to confidence score; handles missing logprobs
- **Effort:** M

**AI-007b: Implement Heuristic Confidence**
- **Description:** When logprobs unavailable: calculate confidence from Vault source relevance (avg top 3 × 0.4) + response coherence (no refusal/hedging × 0.3) + factual grounding (references retrieved docs × 0.3)
- **Output:** Heuristic confidence calculator
- **Acceptance:** Score calculated correctly; refusal language detected; grounding check works
- **Effort:** M

**AI-007c: Implement Decision Engine**
- **Description:** Compare confidence against conversation.confidence_threshold: ≥ threshold → format response + publish outbound; < threshold → escalate (transition state, publish events, send auto-reply)
- **Output:** DecisionEngine class
- **Acceptance:** High confidence → response delivered; low confidence → escalation event + state transition + auto-reply
- **Effort:** M

**AI-007d: Write Confidence Scorer Unit Tests**
- **Description:** Create `tests/unit/test_confidence.py` testing logprob path, heuristic path, threshold boundary, refusal detection, grounding check
- **Output:** `tests/unit/test_confidence.py`
- **Acceptance:** ≥12 test cases; boundary conditions tested; decision outcomes verified
- **Dependencies:** AI-007a, AI-007b, AI-007c
- **Effort:** M

---

#### EPIC 4: Agent & Admin Interfaces

---

##### Task AGENT-001: Agent Inbox REST API

**ID:** AGENT-001
**Title:** Agent Inbox REST API
**Description:** Implement all agent-facing REST endpoints: list conversations (with filters/pagination), get conversation detail, take over conversation, send response, resolve conversation. All with OIDC authentication.
**Inputs:** TSD §2.8 (Agent Inbox), TSD §5.2 (Agent Inbox APIs)
**Output:** Agent REST API router with all endpoints.

**Subtasks:**

**AGENT-001a: Implement List Conversations Endpoint**
- **Description:** `GET /api/v1/agent/conversations` — filter by status, channel, assigned_to_me; pagination (page, page_size); sorting (updated_at, created_at); return customer info, last message, SLA status
- **Output:** List conversations endpoint
- **Acceptance:** Response matches TSD §5.2.1 format; filters work; pagination correct; SLA breach status included
- **Effort:** M

**AGENT-001b: Implement Get Conversation Detail Endpoint**
- **Description:** `GET /api/v1/agent/conversations/{id}` — return full conversation with all messages, customer info, SLA status, assigned agent
- **Output:** Conversation detail endpoint
- **Acceptance:** Response matches TSD §5.2.2; all messages included; metadata preserved
- **Effort:** S

**AGENT-001c: Implement Take Over Endpoint**
- **Description:** `POST /api/v1/agent/conversations/{id}/takeover` — verify escalated+unassigned; set assigned_agent; disable AI; transition state; return 409 if already assigned
- **Output:** Takeover endpoint
- **Acceptance:** Success → 200 with updated conversation; already assigned → 409 CONVERSATION_ALREADY_ASSIGNED; AI disabled
- **Effort:** M

**AGENT-001d: Implement Agent Send Response Endpoint**
- **Description:** `POST /api/v1/agent/conversations/{id}/messages` — persist agent message; publish outbound.message; return 201
- **Output:** Agent send endpoint
- **Acceptance:** Message persisted with sender_type=agent; outbound event published; 201 returned
- **Effort:** S

**AGENT-001e: Implement Resolve Conversation Endpoint**
- **Description:** `POST /api/v1/agent/conversations/{id}/resolve` — transition to resolved; re-enable AI; clear assigned_agent; log audit
- **Output:** Resolve endpoint
- **Acceptance:** State → resolved; AI re-enabled; agent cleared; audit logged
- **Effort:** S

**AGENT-001f: Implement OIDC Authentication for Agent Endpoints**
- **Description:** Validate OIDC tokens on all agent endpoints; extract agent identity; check role (agent or admin); return 401/403 on auth failure
- **Output:** Auth dependency for agent routes
- **Acceptance:** Valid token → request proceeds; invalid token → 401; insufficient role → 403
- **Effort:** M

**AGENT-001g: Write Agent Inbox API Unit Tests**
- **Description:** Create `tests/unit/test_inbox_api.py` testing all endpoints with auth, filters, pagination, state transitions, error cases
- **Output:** `tests/unit/test_inbox_api.py`
- **Acceptance:** ≥20 test cases; all endpoints tested; auth enforcement verified
- **Dependencies:** AGENT-001a through AGENT-001f
- **Effort:** M

---

##### Task AGENT-002: Agent WebSocket (Real-time Updates)

**ID:** AGENT-002
**Title:** Agent WebSocket (Real-time Updates)
**Description:** Implement WebSocket endpoint for real-time agent inbox updates: new messages, conversation state changes, SLA warnings. Support multi-node broadcast via Redis pub/sub.
**Inputs:** TSD §2.8 (WebSocketManager), TSD §5.2.6 (Agent WebSocket)
**Output:** WebSocket endpoint; connection manager; Redis pub/sub broadcast.

**Subtasks:**

**AGENT-002a: Implement WebSocket Connection Manager**
- **Description:** Create `src/desk/agents/websocket.py` — manage agent WebSocket connections; track online agents; handle connect/disconnect; heartbeat/ping-pong
- **Output:** WebSocketManager class
- **Acceptance:** Agents connect/disconnect cleanly; online status tracked; heartbeat keeps connections alive
- **Effort:** M

**AGENT-002b: Implement Real-time Event Broadcasting**
- **Description:** Subscribe to conversation events (new_message, conversation_updated, sla_warning) from event bus; broadcast to connected agents via WebSocket; filter by relevance (assigned agent or all escalated)
- **Output:** Event → WebSocket broadcast logic
- **Acceptance:** New message → agent receives new_message event; state change → conversation_updated; SLA warning → sla_warning with seconds_remaining
- **Effort:** M

**AGENT-002c: Implement Multi-Node Broadcast via Redis Pub/Sub**
- **Description:** For multi-container deployments: use Redis pub/sub to broadcast WebSocket events across all desk-api instances; agent connected to any instance receives all events
- **Output:** Redis pub/sub integration
- **Acceptance:** Event published on one node → all nodes broadcast to their connected agents; no duplicate events
- **Effort:** M

**AGENT-002d: Implement Reconnection Handling**
- **Description:** Support client reconnection with last-event-id; replay missed events since disconnection; prevent event loss during brief network interruptions
- **Output:** Reconnection logic
- **Acceptance:** Client reconnects → receives missed events; no duplicates; no gaps
- **Effort:** M

**AGENT-002e: Write Agent WebSocket Unit Tests**
- **Description:** Create `tests/unit/test_agent_websocket.py` testing connection lifecycle, event broadcasting, multi-node, reconnection
- **Output:** `tests/unit/test_agent_websocket.py`
- **Acceptance:** ≥10 test cases; connection management tested; event delivery verified
- **Dependencies:** AGENT-002a, AGENT-002b
- **Effort:** M

---

##### Task AGENT-003: Admin Setup Wizard API

**ID:** AGENT-003
**Title:** Admin Setup Wizard API
**Description:** Implement the guided setup wizard that allows operators to configure Vault connection, AI models, WhatsApp credentials, and PII Shield settings in a single flow with connection verification.
**Inputs:** TSD §2.9 (SetupWizardAPI), TSD §5.3.1 (Setup Wizard — Complete Setup)
**Output:** Setup wizard endpoint; connection verification; configuration persistence.

**Subtasks:**

**AGENT-003a: Implement Setup Complete Endpoint**
- **Description:** `POST /api/v1/admin/setup/complete` — accept vault, ai, whatsapp, pii_shield configuration; validate all inputs; persist to ai_configurations; return deployment status
- **Output:** Setup complete endpoint
- **Acceptance:** Request matches TSD §5.3.1 format; configuration persisted; response includes check results
- **Effort:** M

**AGENT-003b: Implement Connection Verification Checks**
- **Description:** Verify each integration on setup: Vault (HTTP GET to vault_url), AI model (ping endpoint), WhatsApp (verify webhook with Meta); return status per check
- **Output:** Connection verification functions
- **Acceptance:** Each check returns "ok" or error with details; setup fails if critical checks fail
- **Effort:** M

**AGENT-003c: Implement ODW.ai Auth Client (OIDC)**
- **Description:** Create `src/desk/suite/auth_client.py` — OIDC token validation; user info retrieval; admin role verification
- **Output:** AuthClient class
- **Acceptance:** Token validated against OIDC provider; user roles extracted; admin role check works
- **Effort:** M

**AGENT-003d: Write Setup Wizard Unit Tests**
- **Description:** Create `tests/unit/test_setup_api.py` testing setup flow, connection verification (mock), validation errors
- **Output:** `tests/unit/test_setup_api.py`
- **Acceptance:** ≥10 test cases; happy path + each connection failure tested
- **Dependencies:** AGENT-003a, AGENT-003b
- **Effort:** M

---

##### Task AGENT-004: Admin Configuration & Compliance APIs

**ID:** AGENT-004
**Title:** Admin Configuration & Compliance APIs
**Description:** Implement admin endpoints for AI configuration updates, data export (GDPR Article 20), data deletion (GDPR Article 17), and compliance report generation.
**Inputs:** TSD §2.9 (ConfigAPI, ComplianceAPI), TSD §5.3.2–5.3.4
**Output:** Config API endpoints; Compliance API endpoints.

**Subtasks:**

**AGENT-004a: Implement AI Configuration Update Endpoint**
- **Description:** `PATCH /api/v1/admin/ai/configuration` — partial update of ai_configurations; validate fields; invalidate cache on update
- **Output:** Config update endpoint
- **Acceptance:** Partial updates work; validation enforced; cache invalidated; response returns updated config
- **Effort:** M

**AGENT-004b: Implement Data Export Endpoint**
- **Description:** `POST /api/v1/admin/compliance/export` — accept customer identifier + channel + format; queue export job; return export_id + status; generate JSON/CSV file
- **Output:** Export endpoint
- **Acceptance:** Request matches TSD §5.3.3; export_id returned; 202 Accepted; job processes asynchronously
- **Effort:** M

**AGENT-004c: Implement Data Deletion Endpoint**
- **Description:** `POST /api/v1/admin/compliance/delete` — accept customer identifier + channel + scope; queue deletion job; remove all customer data; log to audit
- **Output:** Deletion endpoint
- **Acceptance:** Request matches TSD §5.3.4; deletion_id returned; 202 Accepted; all data removed after processing
- **Effort:** M

**AGENT-004d: Write Admin API Unit Tests**
- **Description:** Create tests for config update, export, deletion endpoints
- **Output:** Test files
- **Acceptance:** ≥12 test cases; validation errors tested; async job behavior tested
- **Dependencies:** AGENT-004a, AGENT-004b, AGENT-004c
- **Effort:** M

---

##### Task AGENT-005: Compliance Engine (Retention, Export, Deletion, Audit)

**ID:** AGENT-005
**Title:** Compliance Engine (Retention, Export, Deletion, Audit)
**Description:** Implement the full compliance engine: data retention enforcement (cron), per-customer data export, right-to-erasure deletion, and tamper-evident hash-chained audit log.
**Inputs:** TSD §2.10 (Compliance Engine), TSD §4.6 (audit_logs)
**Output:** ComplianceEngine; RetentionManager; ExportService; DeletionService; AuditLogWriter.

**Subtasks:**

**AGENT-005a: Implement Audit Log Writer (Hash-Chained)**
- **Description:** Create `src/desk/compliance/audit.py` — append-only audit log; each record includes SHA-256 hash of (this_record + previous_hash); create chain from first record; verification function
- **Output:** AuditLogWriter class + verification script
- **Acceptance:** Records written with correct hash chain; any modification breaks chain; verification function detects tampering
- **Effort:** L

**AGENT-005b: Implement Hash Chain Utility**
- **Description:** Create `src/desk/utils/hashing.py` — SHA-256 hash function for audit records; consistent serialization for hashing
- **Output:** `src/desk/utils/hashing.py`
- **Acceptance:** Same input → same hash; different input → different hash; deterministic serialization
- **Effort:** S

**AGENT-005c: Implement Retention Manager**
- **Description:** Create `src/desk/compliance/retention.py` — daily cron job (02:00) that deletes conversations/messages past retention period; configurable retention duration; soft-delete then hard-delete
- **Output:** RetentionManager class + cron job
- **Acceptance:** Old data deleted; recent data preserved; retention period configurable; deletion logged to audit
- **Effort:** M

**AGENT-005d: Implement Export Service**
- **Description:** Create `src/desk/compliance/export.py` — gather all data for a customer (conversations, messages, metadata); format as JSON or CSV; upload to S3/MinIO; return download link
- **Output:** ExportService class
- **Acceptance:** All customer data included in export; JSON/CSV formats correct; file uploaded to S3; download link returned
- **Effort:** M

**AGENT-005e: Implement Deletion Service**
- **Description:** Create `src/desk/compliance/deletion.py` — delete all data for a customer across all tables (messages, conversations, customer record); verify zero traces remain; log to audit
- **Output:** DeletionService class
- **Acceptance:** All customer data removed from all tables; verification query returns zero results; audit log records deletion
- **Effort:** M

**AGENT-005f: Implement Compliance Report Generator**
- **Description:** Generate compliance summary reports: data processing activities, retention status, deletion log, audit summary; output as JSON or PDF
- **Output:** ReportGenerator class
- **Acceptance:** Report includes all required sections; data accurate; format correct
- **Effort:** M

**AGENT-005g: Write Compliance Engine Unit Tests**
- **Description:** Create `tests/unit/test_compliance_engine.py` testing hash chain, retention, export, deletion, report generation
- **Output:** `tests/unit/test_compliance_engine.py`
- **Acceptance:** ≥15 test cases; hash chain integrity verified; export contains all data; deletion removes all data
- **Dependencies:** AGENT-005a through AGENT-005f
- **Effort:** L

---

##### Task AGENT-006: License Manager (Validation & Feature Gates)

**ID:** AGENT-006
**Title:** License Manager (Validation & Feature Gates)
**Description:** Implement license validation (online + offline), feature gate enforcement between free/paid tiers, grace period handling, and periodic re-validation.
**Inputs:** TSD §2.11 (License Manager), TSD §6.3 (License Validation Flow)
**Output:** LicenseManager; online/offline validation; feature gate checks.

**Subtasks:**

**AGENT-006a: Implement Online License Validation**
- **Description:** POST to ODW.ai Billing API `/api/v1/licenses/validate`; update local license_state; handle API errors gracefully
- **Output:** Online validation function
- **Acceptance:** Valid license → state updated; invalid → state set to invalid; API error → retry
- **Effort:** M

**AGENT-006b: Implement Offline License Validation**
- **Description:** Verify license key signature using embedded RSA public key; check expiry date; support air-gapped deployments
- **Output:** Offline validation function
- **Acceptance:** Valid signature + not expired → active; expired → grace period; invalid signature → invalid
- **Effort:** M

**AGENT-006c: Implement Feature Gate Enforcement**
- **Description:** Check license_state.features[feature_name] on every feature access; return 403 with tier message if denied; implement all gates from TSD §2.11 table
- **Output:** Feature gate decorator/middleware
- **Acceptance:** Free tier → WhatsApp blocked; paid → all features; gate check < 1ms (cached)
- **Effort:** M

**AGENT-006d: Implement Grace Period Handling**
- **Description:** If license expired < 14 days: allow paid features with warnings; if > 14 days: downgrade to free; notify admin via dashboard banner
- **Output:** Grace period logic
- **Acceptance:** < 14 days → paid features + warning; > 14 days → free features; admin notified
- **Effort:** M

**AGENT-006e: Implement Periodic Re-validation Cron**
- **Description:** Cron job every 24h: re-validate license (online preferred, offline fallback); update state; log result
- **Output:** License re-validation cron job
- **Acceptance:** Runs every 24h; state updated; failures logged
- **Effort:** S

**AGENT-006f: Implement Billing Client**
- **Description:** Create `src/desk/suite/billing_client.py` — HTTP client for ODW.ai Billing API; license validation; feature entitlement checks
- **Output:** BillingClient class
- **Acceptance:** Correct API calls; response parsed; errors handled
- **Effort:** S

**AGENT-006g: Write License Manager Unit Tests**
- **Description:** Create `tests/unit/test_license_manager.py` testing online/offline validation, feature gates, grace period, cron behavior
- **Output:** `tests/unit/test_license_manager.py`
- **Acceptance:** ≥12 test cases; all license states tested; feature gates verified
- **Dependencies:** AGENT-006a through AGENT-006f
- **Effort:** M

---

#### EPIC 5: Deployment & Hardening

---

##### Task DEPLOY-001: Production Docker Images & Multi-stage Builds

**ID:** DEPLOY-001
**Title:** Production Docker Images & Multi-stage Builds
**Description:** Create production-optimized Dockerfiles for desk-api, desk-worker-ai, and desk-web with multi-stage builds, non-root users, minimal image sizes, and health checks.
**Inputs:** TSD §15 (Deployment & Build Instructions)
**Output:** Production Dockerfiles for all three containers.

**Subtasks:**

**DEPLOY-001a: Create Production API Dockerfile**
- **Description:** Multi-stage build: Python 3.11-slim base; install dependencies; copy source; non-root user; health check; minimal layers
- **Output:** `Dockerfile.api`
- **Acceptance:** Image < 500MB; non-root user; health check passes; starts with uvicorn
- **Effort:** M

**DEPLOY-001b: Create AI Worker Dockerfile**
- **Description:** Separate Dockerfile for desk-worker-ai (same base, different entry point — event consumer instead of HTTP server)
- **Output:** `Dockerfile.worker`
- **Acceptance:** Worker starts and consumes from event bus; no HTTP server exposed
- **Effort:** S

**DEPLOY-001c: Create Frontend Dockerfile**
- **Description:** Multi-stage: Node 20-alpine (build) → Nginx-alpine (serve); build React app; copy dist to nginx; serve static files
- **Output:** `Dockerfile.web`
- **Acceptance:** Frontend builds; nginx serves static files; image < 100MB
- **Effort:** M

**DEPLOY-001d: Create Production Docker Compose**
- **Description:** Create `docker-compose.yml` for production: all services (postgres, redis, minio, desk-api, desk-worker-ai, desk-scheduler, desk-web, traefik); proper networking; secrets via env vars; restart policies
- **Output:** `docker-compose.yml`
- **Acceptance:** `docker-compose up` starts full production stack; all services healthy; traefik routes correctly
- **Effort:** L

---

##### Task DEPLOY-002: CI/CD Pipeline (GitHub Actions)

**ID:** DEPLOY-002
**Title:** CI/CD Pipeline (GitHub Actions)
**Description:** Create GitHub Actions workflows for CI (lint, type-check, test, security scan, build) and CD (deploy to staging, smoke tests, manual approval, rolling production update).
**Inputs:** TSD §15 (CI/CD)
**Output:** GitHub Actions workflow files.

**Subtasks:**

**DEPLOY-002a: Create CI Workflow**
- **Description:** `.github/workflows/ci.yml`: lint (ruff) → type-check (mypy) → unit tests → integration tests → security scan (Trivy) → build images → push to GHCR
- **Output:** `.github/workflows/ci.yml`
- **Acceptance:** Pipeline runs on every PR; all steps pass; images tagged with semver + git SHA
- **Effort:** M

**DEPLOY-002b: Create CD Workflow**
- **Description:** `.github/workflows/cd.yml`: deploy to staging → smoke tests → manual approval → rolling update to production
- **Output:** `.github/workflows/cd.yml`
- **Acceptance:** Triggered on merge to main; staging deploy automatic; production requires approval; rolling update zero-downtime
- **Effort:** M

**DEPLOY-002c: Create Test Docker Compose for CI**
- **Description:** Docker Compose file specifically for CI: includes test database, test Redis, mock services; optimized for fast test execution
- **Output:** `docker-compose.test.yml`
- **Acceptance:** CI tests run against real PostgreSQL + Redis; completes in < 5 minutes
- **Effort:** M

---

##### Task DEPLOY-003: End-to-End Test Suite

**ID:** DEPLOY-003
**Title:** End-to-End Test Suite
**Description:** Create comprehensive E2E tests that validate the full system: WhatsApp flow, agent takeover, PII routing, compliance operations. Include mock services and load testing configuration.
**Inputs:** TSD §14 (Testing Strategy)
**Output:** E2E test files; mock services; Locust load test config.

**Subtasks:**

**DEPLOY-003a: Create E2E Test Infrastructure**
- **Description:** Set up test fixtures: Docker Compose for E2E; mock WhatsApp API; mock LLM; mock Vault; test data seeding
- **Output:** E2E test infrastructure (conftest.py, fixtures, mock services)
- **Acceptance:** Full system starts for testing; mock services configurable; test data seeded
- **Effort:** L

**DEPLOY-003b: Implement WhatsApp Flow E2E Test**
- **Description:** `tests/e2e/test_whatsapp_flow.py`: send webhook → verify AI response delivered → verify DB state → verify audit log → verify metrics
- **Output:** WhatsApp E2E test
- **Acceptance:** Full flow passes; all assertions verified
- **Effort:** M

**DEPLOY-003c: Implement Takeover Flow E2E Test**
- **Description:** `tests/e2e/test_takeover_flow.py`: AI escalates → agent takes over → responds → resolves → verify state transitions
- **Output:** Takeover E2E test
- **Acceptance:** Full flow passes; state transitions correct
- **Effort:** M

**DEPLOY-003d: Implement PII Routing E2E Test**
- **Description:** `tests/e2e/test_pii_routing.py`: send PII message → verify local-only routing → verify frontier NOT called
- **Output:** PII routing E2E test
- **Acceptance:** PII detected; local model used; frontier not called
- **Effort:** M

**DEPLOY-003e: Create Locust Load Test Configuration**
- **Description:** Locust test file simulating 100 msg/s; measure latency percentiles; verify no errors under load
- **Output:** `tests/e2e/locustfile.py`
- **Acceptance:** Sustains 100 msg/s for 5 minutes; P95 latency < 10s; error rate < 1%
- **Effort:** M

---

##### Task DEPLOY-004: Observability (Metrics, Logging, Tracing)

**ID:** DEPLOY-004
**Title:** Observability (Metrics, Logging, Tracing)
**Description:** Implement Prometheus metrics endpoint, structured logging with PII filter, OpenTelemetry tracing, and health check endpoints per TSD §16.
**Inputs:** TSD §16 (Observability Hooks), TSD §5.4 (Health & Metrics)
**Output:** Metrics endpoint; structured logging config; OpenTelemetry integration; health endpoints.

**Subtasks:**

**DEPLOY-004a: Implement Prometheus Metrics**
- **Description:** Create `/metrics` endpoint with all metric categories from TSD §16: inbound, AI processing, routing, outbound, cache, queue, system metrics
- **Output:** Metrics endpoint + metric instrumentations throughout codebase
- **Acceptance:** All listed metrics exposed; Prometheus format correct; values update in real-time
- **Effort:** L

**DEPLOY-004b: Configure Structured Logging**
- **Description:** Configure structlog with JSON output; add PII filter processor; add trace_id correlation; configure log levels per environment
- **Output:** Logging configuration
- **Acceptance:** JSON format; PII redacted; trace_id on every entry; DEBUG in dev, INFO in prod
- **Effort:** M

**DEPLOY-004c: Integrate OpenTelemetry Tracing**
- **Description:** Add OpenTelemetry SDK; create spans for: webhook receipt → routing → PII detection → Vault query → model inference → outbound delivery; configurable OTLP export
- **Output:** Tracing integration
- **Acceptance:** Spans created for full pipeline; trace_id correlates with logs; OTLP export configurable
- **Effort:** M

**DEPLOY-004d: Implement Health Check Endpoints**
- **Description:** Create `/health` (overall), `/health/ready` (Kubernetes readiness), `/health/live` (Kubernetes liveness) with dependency checks (DB, Redis, Vault, model, license)
- **Output:** Health check endpoints
- **Acceptance:** /health returns all check statuses; 200 when healthy; 503 when degraded; ready/live separate
- **Effort:** M

---

##### Task DEPLOY-005: Kubernetes Helm Charts

**ID:** DEPLOY-005
**Title:** Kubernetes Helm Charts
**Description:** Create Helm chart for Kubernetes deployment with all services, configurable values, resource limits, ingress, and service mesh compatibility.
**Inputs:** TSD §3.5 (DevOps Tooling), TSD §15 (Deployment)
**Output:** Complete Helm chart.

**Subtasks:**

**DEPLOY-005a: Create Helm Chart Structure**
- **Description:** Create `helm/Chart.yaml`, `helm/values.yaml`, and template files for all deployments, services, configmaps, secrets, ingress
- **Output:** Helm chart directory structure
- **Acceptance:** `helm lint` passes; `helm template` renders valid Kubernetes manifests
- **Effort:** M

**DEPLOY-005b: Create Deployment Templates**
- **Description:** Templates for desk-api, desk-worker-ai, desk-scheduler, desk-web deployments with resource limits, health checks, environment variables from ConfigMap/Secret
- **Output:** Deployment templates
- **Acceptance:** All services deployable; resource limits set; health checks configured
- **Effort:** M

**DEPLOY-005c: Create Supporting Templates**
- **Description:** Service, ConfigMap, Secret, Ingress, HPA (horizontal pod autoscaler), PodDisruptionBudget templates
- **Output:** Supporting templates
- **Acceptance:** Services expose correct ports; secrets managed; ingress routes correctly; HPA scales on CPU
- **Effort:** M

**DEPLOY-005d: Create NATS JetStream Template (Optional)**
- **Description:** Optional NATS JetStream deployment for Kubernetes event bus (alternative to Redis Streams); enabled via values.yaml
- **Output:** NATS template (conditional)
- **Acceptance:** NATS deploys when enabled; event bus switches to NATS backend
- **Effort:** M

---

## Summary Statistics

| Metric | Value |
|---|---|
| Total Epics | 5 |
| Total Tasks | 30 |
| Total Subtasks | ~122 |
| Critical Priority Tasks | 18 |
| High Priority Tasks | 8 |
| Medium Priority Tasks | 4 |
| Large Effort Tasks | 14 |
| Medium Effort Tasks | 12 |
| Small Effort Tasks | 4 |
| AI-Agent Suitable (Single-Shot) | 9 tasks |
| AI-Agent Suitable (Iterative) | 21 tasks |
| Total Files Created | ~95 |
| Total Test Files | ~30 |
| Estimated Timeline | 8 weeks |
| Team Size | 5–7 engineers |

---

**End of Task Breakdown Knowledge Base**
