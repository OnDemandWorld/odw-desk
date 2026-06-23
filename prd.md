# Product Requirements Document: ODW.ai Desk

**Product:** Desk — Self-Hosted, WhatsApp-First AI Customer Support Agent
**Author:** ODW.ai Product Team
**Version:** 1.2
**Date:** 2026-06-24
**Status:** Draft

---

## 1. Product Overview

### 1.1 Vision

Desk is a self-hosted, WhatsApp-first AI customer-support agent that gives businesses full sovereignty over their customer conversation data while delivering intelligent, automated support. It is positioned as a module within the ODW.ai suite — not a standalone competitor to Chatwoot or Intercom — and differentiates through deep integration with Vault (the suite's knowledge base) and a model-agnostic architecture that lets operators run support locally for privacy-sensitive contexts or route to frontier models for harder queries.

### 1.2 Problem Statement

Customer support conversations contain sensitive PII: names, phone numbers, order details, health information, financial data, and legal context. Regulated businesses (healthcare, legal, fintech, government contractors) face a painful trade-off:

- **Cloud SaaS solutions** (Intercom, Zendesk AI, Ada) offer polished UX and advanced features but require sending all customer conversation data to third-party servers — often in jurisdictions that conflict with data-residency requirements (GDPR, HIPAA, PDPA, LGPD).
- **Open-source alternatives** (Chatwoot, Botpress) offer self-hosting but lack WhatsApp-first design, deep knowledge-base integration, and model-agnostic routing. WhatsApp — the dominant support channel in most of the world outside the US — remains genuinely underserved in the self-hosted/open-source space.
- **WhatsApp integration friction** — Existing solutions require Meta Business verification for WhatsApp integration, creating weeks of delay for SMBs and developers who want quick setup. No self-hosted solution offers both official Business API (for regulated enterprise compliance) AND bridge-based WhatsApp (for rapid deployment without Meta verification).

No existing product combines: (a) self-hosted data sovereignty, (b) WhatsApp as the primary channel with dual-path integration, (c) deep integration with a private knowledge base, and (d) model-agnostic AI routing.

### 1.3 Solution

Desk provides:

- **Self-hosted deployment** — all conversation data, customer profiles, and knowledge-base queries stay in the operator's own database and infrastructure.
- **Dual-path WhatsApp integration** — native WhatsApp Business API connector for enterprise compliance OR Baileys bridge adapter for quick-start deployments without Meta verification. Operators choose based on their compliance needs and setup speed requirements.
- **Channel-agnostic adapter architecture** — pluggable channel adapter system enabling future expansion to Telegram, Discord, Slack, Signal, iMessage, and other channels as optional modules.
- **Vault integration** — Desk answers customer questions by querying the operator's own Vault knowledge base, not a third-party vector store or generic LLM training data.
- **Model-agnostic AI layer** — operators can run local models (e.g., Llama, Mistral) for privacy-sensitive queries, route to frontier models (GPT-4, Claude) for complex queries, or use hybrid routing based on confidence thresholds.
- **Suite positioning** — Desk is one module in the ODW.ai suite (alongside Vault, etc.), sharing auth, data models, and UI patterns. This is not a standalone Chatwoot competitor.

### 1.4 Target Market

- **Primary:** SMBs (10–500 employees) in regulated or data-residency-sensitive contexts — healthcare clinics, legal firms, fintech startups, government contractors, education institutions, and businesses in regions with strict data-localization laws (EU, Brazil, India, Southeast Asia).
- **Secondary:** Developer-led companies and agencies that want to white-label or deeply customize their support stack without vendor lock-in.
- **Tertiary:** Enterprise teams evaluating sovereign AI alternatives to cloud SaaS for specific departments or use cases.

### 1.5 Competitive Landscape

| Competitor | Model | WhatsApp Support | Self-Hosted | Knowledge Base Integration | Model Agnostic |
|---|---|---|---|---|---|
| **Intercom** | Cloud SaaS | Limited | No | Proprietary | No |
| **Zendesk AI** | Cloud SaaS | Yes (add-on) | No | Proprietary | No |
| **Ada** | Cloud SaaS | Yes | No | Proprietary | No |
| **Chatwoot** | Open-source | Yes (community) | Yes | Basic | Limited |
| **Botpress** | Open-source | Yes | Yes | Basic | Yes |
| **Tidio** | Cloud SaaS | No | No | Proprietary | No |
| **Desk (ODW.ai)** | Self-hosted + paid tier | **Yes (native, first-class)** | **Yes** | **Deep (Vault)** | **Yes** |

### 1.6 Key Differentiators

1. **WhatsApp-first, not WhatsApp-also.** Most open-source tools bolt WhatsApp on as an afterthought. Desk designs the conversation flow, message templates, and agent handoff around WhatsApp's constraints and strengths.
2. **Dual-path WhatsApp: enterprise OR quick-start.** Operators choose between official WhatsApp Business API (for regulated enterprise compliance) OR zero-friction Baileys bridge (for rapid deployment without Meta verification). No other self-hosted solution offers both paths.
3. **Sovereignty as a feature, not a compromise.** Data never leaves the operator's infrastructure unless they explicitly configure a frontier-model route. This is a first-class architectural decision, not a self-hosting afterthought.
4. **Vault-native knowledge retrieval.** Desk doesn't require operators to re-upload their documentation to a third-party vector store. It queries Vault directly, using the same knowledge base the rest of the ODW.ai suite uses.
5. **Model-agnostic by design.** Operators choose where inference happens per conversation, per query, or per confidence threshold — local for PII-heavy queries, frontier for complex reasoning.
6. **Channel-agnostic adapter architecture.** Pluggable channel adapter system enables future expansion to Telegram, Discord, Slack, Signal, iMessage without architectural changes. WhatsApp is the primary implementation; other channels are optional modules.
7. **Suite integration, not standalone.** Desk shares auth, user management, billing, and UI patterns with the rest of ODW.ai. Operators who already use Vault get Desk working in minutes, not days.
8. **Brand Persona, not generic bot.** Desk is a front-desk agent that *represents the business*. Operators configure a brand voice (tone, vocabulary, formality, do's/don'ts) and response policies so a restaurant taking bookings sounds like that restaurant, and a law firm sounds like that firm. Persona is configurable out of the box and can be reinforced with optional local-model fine-tuning for operators who want maximum consistency.

---

## 2. Goals & Success Metrics

### 2.1 Product Goals

| # | Goal | Timeframe |
|---|---|---|
| G1 | Launch a self-hosted AI customer-support agent that keeps all conversation data in the operator's own infrastructure | MVP (Q3 2026) |
| G2 | Deliver first-class WhatsApp support that is genuinely better than bolted-on integrations in Chatwoot/Botpress | MVP (Q3 2026) |
| G3 | Integrate deeply with Vault so operators can answer from their own knowledge base without re-uploading docs | MVP (Q3 2026) |
| G4 | Provide model-agnostic routing so operators can run locally for privacy or route to frontier models for quality | v1.1 (Q4 2026) |
| G5 | Establish a sustainable freemium model: free core for self-hosted chatbot + basic channels, paid tier for WhatsApp Business connector, multi-agent routing, compliance features, and SLA support | v1.0 (Q3 2026) |
| G6 | Position Desk as a module of the ODW.ai suite, not a standalone product | Ongoing |

### 2.2 Success Metrics

#### North Star Metric
**Weekly Active Conversations Handled by AI** — number of customer conversations per week where Desk's AI resolves or meaningfully advances the conversation without human agent takeover.

#### Leading Indicators

| Metric | Target (6 months post-launch) | Rationale |
|---|---|---|
| Self-hosted deployments | 500+ | Validates market demand for sovereign support |
| WhatsApp conversations / week / deployment | 200+ | Validates WhatsApp-first positioning |
| AI resolution rate (no human handoff) | ≥60% | Validates AI quality and Vault integration |
| Time-to-first-value (Baileys bridge deployment) | <30 minutes | Validates zero-friction setup for SMBs/developers |
| Time-to-first-value (Business API deployment) | <2 hours | Validates ease of setup for enterprise |
| Paid conversion rate (free → paid) | ≥8% | Validates paid tier value |
| Monthly churn (paid) | <5% | Validates stickiness |
| NPS | ≥40 | Validates product-market fit |
| PII-leak incidents (to third-party models) | 0 | Validates sovereignty promise |

#### Lagging Indicators

| Metric | Target (12 months post-launch) |
|---|---|
| Annual Recurring Revenue (ARR) from paid tier | $1.5M+ |
| Number of regulated-industry customers | 50+ |
| Average revenue per paid account | $250/month |
| Suite cross-sell rate (Desk customers also using Vault) | ≥70% |

### 2.3 Anti-Goals (Things We Will Not Optimize For)

- **Competing with Intercom/Zendesk on feature breadth.** We will not build 200 integrations, a visual flow builder, or a full CRM. We focus on AI-first support with sovereignty.
- **Being a general-purpose chatbot framework.** Desk is for customer support, not marketing bots, lead-gen funnels, or internal tooling.
- **Supporting every channel equally.** WhatsApp is first-class; web chat and email are second-class; SMS, Instagram, and LINE are out of scope for v1.
- **Replacing human agents.** Desk augments human support teams; it does not aim for 100% automation.

---

## 3. Scope Definition

### 3.1 In Scope (MVP — v1.0)

**Channels**

*MVP Channels (v1.0):*
- WhatsApp Business API (native connector, first-class, enterprise tier)
- WhatsApp Baileys Bridge (native connector, first-class, quick-start tier) — connects via WhatsApp Web protocol without Meta Business verification
- Web chat widget (embeddable, second-class)
- Email (inbound/outbound, second-class)

*Future Optional Channels (v1.1+):*
- Telegram bot (optional module)
- Discord bot (optional module)
- Slack app (optional module)
- Signal messenger (optional module)
- iMessage bridge (optional module)

**AI & Knowledge**
- Vault integration for knowledge retrieval (RAG over operator's own docs)
- Model-agnostic inference: local model support (Ollama, vLLM) + frontier model routing (OpenAI, Anthropic)
- Confidence-based routing: local model handles high-confidence queries, escalates to frontier or human
- Conversation memory and context management
- Multi-turn conversation handling

**Agent & Workflow**
- Single-agent mode (one AI persona per deployment)
- Human handoff with context transfer
- Agent inbox for human review of AI-handled conversations
- Basic conversation tagging and categorization
- SLA tracking (first-response time, resolution time)

**Data & Sovereignty**
- All conversation data stored in operator's own PostgreSQL database
- Encryption at rest and in transit
- Data export and deletion APIs
- Audit log of all AI decisions and data access
- PII detection and redaction (configurable per deployment)

**Deployment & Operations**
- Docker Compose deployment (single-command setup)
- Kubernetes Helm chart
- Self-hosted dashboard (React-based admin UI)
- Health checks and basic monitoring
- Backup and restore tooling

**Business Model**
- Free tier: self-hosted chatbot, web chat + email channels, single agent, basic Vault integration
- Paid tier: WhatsApp Business connector, multi-agent routing, advanced compliance (audit exports, data-retention policies), SLA-backed support, priority bug fixes

### 3.2 Out of Scope (v1.0)

**Channels**
- SMS / MMS
- Instagram Direct, Facebook Messenger
- LINE, WeChat (may be considered for v2 based on market demand)
- Voice / IVR
- In-app mobile SDK
- Official Meta BSP (Business Solution Provider) partnership — Desk uses direct Business API or Baileys bridge, not BSP reseller model

**AI & Knowledge**
- Visual conversation-flow builder (no-code bot design)
- Multi-language support beyond English + one additional language (stretch goal)
- Custom model fine-tuning within Desk (operators fine-tune externally, then plug in)
- Generative actions (e.g., "create a refund" — Desk answers questions, does not execute transactions in v1)

**Agent & Workflow**
- Multi-agent routing (different AI personas for different topics) — paid tier, v1.1
- Team collaboration features (internal notes, @mentions, collision detection)
- CRM integration (Salesforce, HubSpot)
- Ticketing system (Desk is conversation-first, not ticket-first)
- Automated outbound campaigns

**Data & Sovereignty**
- Multi-tenant SaaS hosting (Desk is self-hosted only; ODW.ai does not offer a managed Desk cloud)
- Cross-deployment data sharing
- Blockchain-based audit trails

**Deployment & Operations**
- Managed hosting / SaaS offering
- Mobile admin app
- White-labeling / multi-tenant agency mode

### 3.3 Scope for v1.1 (Post-MVP)

- Multi-agent routing (different AI personas per topic/department)
- Telegram channel support
- Advanced compliance features (data-retention policies, automated PII redaction schedules, compliance report generation)
- Multi-language support (Spanish, Portuguese, French, Arabic)
- Generative actions (execute simple transactions via API)
- Mobile admin app (read-only, for monitoring)
- White-labeling for agency partners

---

## 4. User Personas

### 4.1 Primary Personas

#### Persona 1: Maria — The Regulated-Business Operations Manager

**Demographics**
- Age: 34–45
- Role: Operations Manager or Customer Support Lead
- Company: 20–200 employees, healthcare clinic, legal firm, or fintech startup
- Location: EU, Brazil, or Southeast Asia (regions with strict data-residency laws)

**Goals**
- Reduce customer support response time from hours to minutes
- Ensure all customer conversation data stays within the company's infrastructure (GDPR, HIPAA, LGPD compliance)
- Avoid vendor lock-in with cloud SaaS that could change pricing, terms, or data policies
- Provide 24/7 support without hiring night-shift staff

**Frustrations**
- Current cloud SaaS (Intercom, Zendesk) requires sending customer PII to US servers — legal team flagged this as a compliance risk
- Chatwoot's WhatsApp integration is community-maintained and breaks frequently
- Existing AI chatbots require uploading documentation to third-party servers
- Setting up self-hosted tools takes weeks of DevOps work

**Technical Sophistication**
- Moderate. Can use Docker, understands APIs, but is not a developer. Relies on IT team or external consultants for infrastructure.

**Success Criteria for Maria**
- Deploys Desk in under a day with IT team's help
- WhatsApp conversations are handled by AI with <5% error rate
- Legal team signs off on data-residency compliance
- Customer satisfaction scores improve by 20%+

---

#### Persona 2: Raj — The Developer-Led Startup CTO

**Demographics**
- Age: 28–38
- Role: CTO or Head of Engineering
- Company: 10–50 employees, developer tools, SaaS, or AI startup
- Location: Global (US, India, Europe)

**Goals**
- Build a support stack that can be deeply customized and extended
- Avoid paying per-seat pricing that scales linearly with headcount
- Own the entire stack: data, models, infrastructure
- Integrate support conversations with internal tools (CRM, analytics, product telemetry)

**Frustrations**
- Cloud SaaS pricing is unpredictable and expensive at scale
- Open-source tools (Chatwoot, Botpress) are fragmented — WhatsApp support is bolted on, knowledge-base integration is shallow
- Vendor lock-in makes it hard to migrate or customize
- AI features are black boxes — can't inspect or tune model behavior

**Technical Sophistication**
- High. Comfortable with Docker, Kubernetes, APIs, Python/TypeScript. Can read source code and contribute PRs.

**Success Criteria for Raj**
- Deploys Desk via Docker Compose in under 30 minutes
- Can swap models (local Llama → GPT-4) via config file, no code changes
- API is clean and well-documented — can build custom integrations in a day
- Source code is readable and contribution-friendly

---

#### Persona 3: Aisha — The Customer Support Agent

**Demographics**
- Age: 22–35
- Role: Customer Support Agent or Team Lead
- Company: Same as Maria's company (regulated SMB)
- Location: Same as Maria's company

**Goals**
- Handle customer conversations efficiently without context-switching between tools
- See AI-suggested responses and customer context (previous conversations, purchase history) in one place
- Escalate complex conversations to specialists without losing context
- Meet SLA targets (first response <5 min, resolution <24 hours)

**Frustrations**
- Current tools require copying customer info between systems
- AI chatbots give wrong answers and agents have to correct them, wasting time
- No visibility into which conversations the AI handled vs. which need human review
- WhatsApp conversations are hard to track alongside email and web chat

**Technical Sophistication**
- Low to moderate. Uses web apps daily but does not configure infrastructure or write code.

**Success Criteria for Aisha**
- Agent inbox is fast, intuitive, and shows all channels in one view
- AI handles 60%+ of conversations without errors — agents only review edge cases
- Context transfer from AI to human is seamless — no "please repeat your question"
- Can see conversation history, customer tags, and AI confidence scores at a glance

---

### 4.2 Secondary Personas

#### Persona 4: Carlos — The End Customer

**Demographics**
- Age: 18–65
- Role: Customer of Maria's company
- Location: Global (primarily regions where WhatsApp is dominant)

**Goals**
- Get fast, accurate answers to support questions
- Communicate in the channel they already use (WhatsApp)
- Not repeat themselves when escalated to a human agent
- Trust that their personal information is handled securely

**Frustrations**
- Chatbots give generic, unhelpful answers
- Long wait times for human agents
- Having to re-explain context when transferred
- Unclear whether they're talking to a bot or a human

**Success Criteria for Carlos**
- Gets accurate answers within 30 seconds on WhatsApp
- Can't tell the difference between AI and human responses (or doesn't care)
- Escalation to human is smooth and fast
- Feels confident their data is private

---

#### Persona 5: Dev — The ODW.ai Suite Administrator

**Demographics**
- Age: 30–45
- Role: IT Administrator or Platform Engineer
- Company: Already uses ODW.ai suite (Vault, possibly other modules)
- Location: Global

**Goals**
- Add Desk to existing ODW.ai deployment without duplicating auth, user management, or infrastructure
- Manage all ODW.ai modules from a single admin dashboard
- Monitor AI performance, costs, and compliance across modules
- Enforce company-wide policies (data retention, model usage, access control)

**Frustrations**
- Each tool in the stack has its own auth, admin UI, and data model
- Hard to get a unified view of AI usage and costs across modules
- Compliance audits require pulling data from multiple systems

**Success Criteria for Dev**
- Adds Desk to existing ODW.ai deployment in under 1 hour
- Single sign-on works across all modules
- Can see Desk metrics alongside Vault metrics in unified dashboard
- Compliance reports pull data from all modules automatically

---

## 5. User Journeys & Flows

### 5.1 Journey 1: First-Time Deployment (Maria / Raj)

**Goal:** Deploy Desk and handle the first WhatsApp conversation.

**Steps:**
1. Maria/Raj visits ODW.ai website, navigates to Desk product page.
2. Reads overview, sees self-hosted deployment options (Docker Compose, Kubernetes).
3. Downloads deployment package or clones GitHub repo.
4. Runs `docker compose up` (or `helm install` for Kubernetes).
5. Accesses admin dashboard at `https://desk.company.com`.
6. Completes initial setup wizard:
   - Creates admin account
   - Connects Vault (provides Vault URL + API key, or uses local Vault if co-deployed)
   - Uploads knowledge base documents (or points to existing Vault collection)
   - Configures AI model (selects local model via Ollama, or provides OpenAI/Anthropic API key)
7. Connects WhatsApp Business API:
   - Enters WhatsApp Business Account phone number
   - Provides Meta Business API credentials (or uses ODW.ai's WhatsApp Business Solution Provider integration — paid tier)
   - Verifies phone number via SMS code
   - Configures message templates (greeting, out-of-office, escalation)
8. Connects web chat widget (optional):
   - Copies embed snippet
   - Pastes into company website
9. Tests conversation:
   - Sends test message via WhatsApp
   - Sees conversation appear in agent inbox
   - Reviews AI response, approves or edits
10. Goes live:
    - Enables auto-response mode
    - Monitors first 24 hours of conversations
    - Adjusts confidence thresholds and knowledge base as needed

**Success Criteria:** First AI-handled WhatsApp conversation within 2 hours of starting deployment.

---

### 5.2 Journey 2: Customer Support Conversation (Carlos → Desk AI → Aisha)

**Goal:** Customer gets accurate answer; if AI can't handle it, seamless handoff to human.

**Steps:**
1. Carlos sends WhatsApp message: "Hi, I need to reschedule my appointment for next week."
2. Desk receives message via WhatsApp Business API.
3. Desk performs PII detection: identifies appointment context, checks if customer is known (matches phone number to customer database).
4. Desk queries Vault for appointment-rescheduling policy and procedure.
5. Desk generates response: "Hi Carlos! I can help you reschedule. What day next week works best for you?"
6. Desk sends response via WhatsApp.
7. Carlos replies: "Tuesday afternoon, if possible."
8. Desk queries Vault for available slots (or checks if appointment scheduling is a generative action — out of scope for v1, so Desk responds with procedure).
9. Desk responds: "I have Tuesday at 2:00 PM and 4:30 PM available. Which works better?"
10. Carlos replies: "2:00 PM please."
11. Desk attempts to execute appointment change (out of scope for v1 — generative actions not supported).
12. Desk recognizes limitation, escalates to human agent:
    - Sends Carlos: "Let me connect you with our team to confirm your appointment. One moment!"
    - Creates handoff ticket with full conversation context
    - Notifies Aisha via agent inbox
13. Aisha sees conversation in inbox, reviews context, confirms appointment:
    - Sends Carlos: "Hi Carlos, I've rescheduled your appointment to Tuesday at 2:00 PM. You'll get a confirmation shortly!"
14. Conversation marked as resolved.

**Success Criteria:** Carlos gets a response within 30 seconds; handoff to human takes <2 minutes; no context is lost in transfer.

---

### 5.3 Journey 3: Human Agent Reviews AI-Handled Conversations (Aisha)

**Goal:** Agent reviews AI-handled conversations, corrects errors, provides feedback.

**Steps:**
1. Aisha logs into agent inbox at start of shift.
2. Sees dashboard: 47 conversations handled by AI overnight, 3 flagged for review (low confidence), 2 escalated by AI.
3. Opens flagged conversation: customer asked about refund policy, AI gave generic answer.
4. Aisha reviews conversation, sees AI confidence score was 42% (below 60% threshold).
5. Aisha edits AI response, sends corrected version to customer (if conversation is still active) or marks as "needs follow-up."
6. Aisha provides feedback: tags AI response as "incorrect — refund policy has changed, updating knowledge base."
7. Aisha opens Vault, updates refund policy document.
8. Aisha returns to inbox, reviews next flagged conversation.
9. Aisha checks escalated conversations: reads context, takes over, resolves.
10. End of shift: Aisha reviews metrics — AI handled 85% of conversations, average response time 12 seconds, customer satisfaction 4.3/5.

**Success Criteria:** Agent can review, correct, and provide feedback on AI responses in under 5 minutes per conversation.

---

### 5.4 Journey 4: Model Routing Decision (Desk AI — Internal)

**Goal:** Desk routes each query to the appropriate model based on privacy, complexity, and cost.

**Steps:**
1. Desk receives customer message.
2. Desk performs PII detection: message contains customer name, phone number, and health information.
3. Desk checks routing policy (configured by admin):
   - If PII detected → route to local model (no data leaves infrastructure)
   - If no PII and complexity score < 0.7 → route to local model
   - If no PII and complexity score ≥ 0.7 → route to frontier model (GPT-4, Claude)
4. Desk routes message to local model (Ollama running Llama 3).
5. Local model generates response.
6. Desk performs quality check (confidence score, hallucination detection).
7. If confidence < threshold, Desk re-routes to frontier model (with PII redacted).
8. Desk sends final response to customer.
9. Desk logs routing decision, model used, latency, cost, and confidence score.

**Success Criteria:** PII never reaches frontier model unless explicitly allowed by admin; routing adds <500ms latency; cost per conversation < $0.05.

---

### 5.5 Journey 5: Compliance Audit (Maria / Dev)

**Goal:** Generate compliance report for legal/regulatory audit.

**Steps:**
1. Maria receives notice of GDPR compliance audit.
2. Maria logs into Desk admin dashboard, navigates to Compliance section.
3. Selects date range (last 12 months).
4. Generates report:
   - Total conversations: 12,340
   - Conversations with PII: 8,920
   - PII routed to local model: 8,915
   - PII routed to frontier model (with redaction): 5
   - Data access requests fulfilled: 23
   - Data deletion requests fulfilled: 12
   - Audit log entries: 45,670
5. Maria exports report as PDF and CSV.
6. Maria provides report to auditor.
7. Auditor requests raw audit log for specific customer: Maria exports conversation history + access log for that customer.
8. Audit completed successfully.

**Success Criteria:** Compliance report generated in under 5 minutes; all required data points available; auditor has no follow-up questions.

---

## 6. Functional Requirements

### 6.1 Channel Management

| ID | Requirement | Priority | Notes |
|---|---|---|---|
| FR-CM-01 | System must accept inbound messages from WhatsApp Business API | P0 | MVP |
| FR-CM-02 | System must send outbound messages via WhatsApp Business API | P0 | MVP |
| FR-CM-03 | System must support WhatsApp message templates (pre-approved by Meta) | P0 | MVP (Business API only) |
| FR-CM-04 | System must handle WhatsApp media messages (images, documents, audio) | P1 | MVP (basic) |
| FR-CM-05 | System must accept inbound messages from web chat widget | P0 | MVP |
| FR-CM-06 | System must provide embeddable web chat widget (JavaScript snippet) | P0 | MVP |
| FR-CM-07 | System must accept inbound emails and route to conversation thread | P1 | MVP |
| FR-CM-08 | System must send outbound emails from conversation thread | P1 | MVP |
| FR-CM-09 | System must unify conversations across channels (single customer timeline) | P0 | MVP |
| FR-CM-10 | System must support WhatsApp interactive messages (buttons, lists) | P2 | v1.1 (Business API only) |
| FR-CM-11 | System must accept inbound messages from WhatsApp Baileys Bridge | P0 | MVP |
| FR-CM-12 | System must send outbound messages via WhatsApp Baileys Bridge | P0 | MVP |
| FR-CM-13 | System must provide QR code pairing flow for WhatsApp Baileys Bridge setup | P0 | MVP |
| FR-CM-14 | System must persist WhatsApp Baileys session state across container restarts | P0 | MVP |
| FR-CM-15 | System must auto-reconnect WhatsApp Baileys Bridge on connection loss | P0 | MVP |
| FR-CM-16 | System must provide channel adapter plugin interface for future channel expansion | P0 | MVP |
| FR-CM-17 | System must support channel adapter configuration via admin dashboard | P0 | MVP |
| FR-CM-18 | System must monitor channel adapter health and notify on connection failures | P1 | MVP |

### 6.2 AI & Knowledge Retrieval

| ID | Requirement | Priority | Notes |
|---|---|---|---|
| FR-AI-01 | System must retrieve relevant knowledge from Vault via RAG | P0 | MVP |
| FR-AI-02 | System must generate responses using configured LLM | P0 | MVP |
| FR-AI-03 | System must support local model inference (Ollama, vLLM) | P0 | MVP |
| FR-AI-04 | System must support frontier model inference (OpenAI, Anthropic) | P0 | MVP |
| FR-AI-05 | System must route queries based on PII detection and complexity | P0 | MVP |
| FR-AI-06 | System must maintain conversation context across multi-turn exchanges | P0 | MVP |
| FR-AI-07 | System must calculate confidence score for each AI response | P0 | MVP |
| FR-AI-08 | System must escalate to human when confidence < configurable threshold | P0 | MVP |
| FR-AI-09 | System must detect and redact PII before sending to frontier models | P0 | MVP |
| FR-AI-10 | System must support custom system prompts per deployment | P1 | MVP |
| FR-AI-11 | System must support conversation summarization for long threads | P2 | v1.1 |
| FR-AI-12 | System must support multi-agent routing (different personas per topic) | P2 | v1.1 (paid) |

### 6.3 Agent Inbox & Workflow

| ID | Requirement | Priority | Notes |
|---|---|---|---|
| FR-AW-01 | System must provide agent inbox showing all conversations across channels | P0 | MVP |
| FR-AW-02 | System must allow human agents to take over AI-handled conversations | P0 | MVP |
| FR-AW-03 | System must preserve full conversation context during handoff | P0 | MVP |
| FR-AW-04 | System must allow agents to edit AI responses before sending | P0 | MVP |
| FR-AW-05 | System must tag conversations by category (billing, technical, etc.) | P1 | MVP |
| FR-AW-06 | System must track SLA metrics (first response time, resolution time) | P1 | MVP |
| FR-AW-07 | System must notify agents of new escalations via email/webhook | P1 | MVP |
| FR-AW-08 | System must allow agents to provide feedback on AI responses | P1 | MVP |
| FR-AW-09 | System must support conversation assignment to specific agents | P2 | v1.1 |
| FR-AW-10 | System must support internal notes (not visible to customer) | P2 | v1.1 |

### 6.4 Data & Sovereignty

| ID | Requirement | Priority | Notes |
|---|---|---|---|
| FR-DS-01 | System must store all conversation data in operator's own PostgreSQL database | P0 | MVP |
| FR-DS-02 | System must encrypt data at rest (AES-256) | P0 | MVP |
| FR-DS-03 | System must encrypt data in transit (TLS 1.3) | P0 | MVP |
| FR-DS-04 | System must provide data export API (JSON, CSV) | P0 | MVP |
| FR-DS-05 | System must provide data deletion API (GDPR right-to-erasure) | P0 | MVP |
| FR-DS-06 | System must maintain audit log of all AI decisions and data access | P0 | MVP |
| FR-DS-07 | System must detect PII in customer messages | P0 | MVP |
| FR-DS-08 | System must redact PII before sending to external models | P0 | MVP |
| FR-DS-09 | System must support configurable data retention policies | P2 | v1.1 (paid) |
| FR-DS-10 | System must support automated PII redaction on a schedule | P2 | v1.1 (paid) |
| FR-DS-11 | System must generate compliance reports (GDPR, HIPAA, LGPD) | P2 | v1.1 (paid) |

### 6.5 Deployment & Operations

| ID | Requirement | Priority | Notes |
|---|---|---|---|
| FR-DO-01 | System must deploy via Docker Compose (single command) | P0 | MVP |
| FR-DO-02 | System must provide Kubernetes Helm chart | P1 | MVP |
| FR-DO-03 | System must provide admin dashboard (React-based web UI) | P0 | MVP |
| FR-DO-04 | System must provide health check endpoints | P0 | MVP |
| FR-DO-05 | System must provide backup and restore tooling | P1 | MVP |
| FR-DO-06 | System must support horizontal scaling (stateless application tier) | P1 | MVP |
| FR-DO-07 | System must provide Prometheus metrics endpoint | P2 | v1.1 |
| FR-DO-08 | System must support blue-green deployments | P2 | v1.1 |

### 6.6 Suite Integration

| ID | Requirement | Priority | Notes |
|---|---|---|---|
| FR-SI-01 | System must integrate with ODW.ai Vault for knowledge retrieval | P0 | MVP |
| FR-SI-02 | System must support ODW.ai single sign-on (SSO) | P1 | MVP |
| FR-SI-03 | System must share user management with ODW.ai suite | P1 | MVP |
| FR-SI-04 | System must integrate with ODW.ai unified admin dashboard | P2 | v1.1 |
| FR-SI-05 | System must support ODW.ai billing and licensing integration | P0 | MVP |

### 6.7 Business Model & Licensing

| ID | Requirement | Priority | Notes |
|---|---|---|---|
| FR-BM-01 | System must enforce feature gating between free and paid tiers | P0 | MVP |
| FR-BM-02 | Free tier must include: self-hosted chatbot, web chat + email, single agent, basic Vault, basic Brand Persona (prompt-based) | P0 | MVP |
| FR-BM-03 | Paid tier must include: WhatsApp Business connector, multi-agent routing, compliance features, SLA support, Response Policy & Guardrails (competitor/pricing/legal rules, post-generation checks), fine-tuned local persona adapters (LoRA/QLoRA), disclaimer automation, per-channel persona overrides | P0 | MVP |
| FR-BM-04 | System must validate license key on startup and periodically | P0 | MVP |
| FR-BM-05 | System must provide grace period (7 days) if license expires | P1 | MVP |
| FR-BM-06 | System must support offline license validation (air-gapped deployments) | P2 | v1.1 |

### 6.8 Brand Persona & Voice

| ID | Requirement | Priority | Notes |
|---|---|---|---|
| FR-BP-01 | System must let operators define a Brand Persona (tone, formality, vocabulary, emoji policy, language style, signature phrases) via admin dashboard | P0 | MVP — prompt-based |
| FR-BP-02 | System must inject the active Brand Persona into every AI generation (system prompt composition) | P0 | MVP |
| FR-BP-03 | System must support few-shot style examples (operator-provided "good response" samples) to steer tone | P1 | MVP |
| FR-BP-04 | System must support per-channel persona overrides (e.g., shorter on WhatsApp, formal on email) | P2 | v1.1 |
| FR-BP-05 | System must allow operators to preview/test persona against sample messages before going live | P1 | MVP |
| FR-BP-06 | System must support loading a fine-tuned local model adapter (LoRA/QLoRA) as the persona backend | P2 | v1.1 (paid) |
| FR-BP-07 | System must allow switching between prompt-based persona and fine-tuned-adapter persona via config, with no code change | P2 | v1.1 (paid) |
| FR-BP-08 | System must version Brand Persona configurations and allow rollback | P2 | v1.1 |

### 6.9 Response Policy & Guardrails

| ID | Requirement | Priority | Notes |
|---|---|---|---|
| FR-RP-01 | System must support configurable topic-based response rules (e.g., competitor mention, pricing, legal/medical disclaimers) | P0 | MVP — paid tier |
| FR-RP-02 | System must detect policy-triggering intents in inbound messages (classifier or rule/keyword based) | P0 | MVP |
| FR-RP-03 | System must support templated/canned responses bound to specific intents (e.g., competitor → redirect template) | P0 | MVP |
| FR-RP-04 | System must perform a post-generation check that flags or blocks responses violating active policies | P1 | MVP |
| FR-RP-05 | System must log every policy trigger, action taken (template/redirect/block/allow), and matched rule in the audit log | P0 | MVP — ties to FR-DS-06 |
| FR-RP-06 | System must let operators set the fallback behavior when no Vault doc is found, including a "never use general model knowledge for restricted topics" mode | P0 | MVP — supersedes/qualifies US-AI-01(c) |
| FR-RP-07 | System must support disclaimer injection (auto-append legal/medical disclaimers to matching responses) | P2 | v1.1 (paid) |
| FR-RP-08 | System must allow guardrail policies to route to human handoff instead of auto-responding | P1 | MVP — ties to FR-AI-08 |

---

## 7. User Stories & Acceptance Criteria

### 7.1 Channel Management

**US-CM-01: WhatsApp Inbound Messages**
_As a customer, I want to send support messages via WhatsApp so that I can get help in the channel I already use._

**Acceptance Criteria:**
- Given a customer sends a WhatsApp message, when the message is received by the WhatsApp Business API, then Desk creates a conversation thread (or appends to existing thread) within 2 seconds.
- Given a customer sends a WhatsApp message with media (image, document), when the message is received, then Desk downloads and stores the media in the operator's database.
- Given a customer sends a WhatsApp message outside business hours, when the message is received, then Desk sends an auto-reply template (configurable by admin).

---

**US-CM-02: WhatsApp Outbound Messages**
_As a Desk AI or human agent, I want to send responses via WhatsApp so that customers receive answers in their preferred channel._

**Acceptance Criteria:**
- Given Desk AI generates a response, when the response is approved (auto or manual), then the response is sent via WhatsApp Business API within 1 second.
- Given a human agent types a response in the agent inbox, when the agent clicks "Send," then the response is sent via WhatsApp within 1 second.
- Given a response exceeds WhatsApp's character limit (1024 chars for text), when the response is sent, then Desk splits the message into multiple parts and sends them in order.

---

**US-CM-03: Web Chat Widget**
_As a website visitor, I want to chat with support via a widget on the company website so that I can get help without leaving the page._

**Acceptance Criteria:**
- Given a website visitor clicks the chat widget, when the widget loads, then the visitor can send text messages and receive AI responses in real-time.
- Given a visitor sends a message, when the AI is generating a response, then the widget shows a "typing..." indicator.
- Given a visitor refreshes the page, when the widget reloads, then the conversation history is preserved (linked to browser session or customer phone number).

---

**US-CM-04: Email Channel**
_As a customer, I want to send support emails and receive replies in the same thread so that I can communicate asynchronously._

**Acceptance Criteria:**
- Given a customer sends an email to support@company.com, when the email is received, then Desk creates a conversation thread and extracts the email body (ignoring signatures, disclaimers).
- Given Desk AI generates a response, when the response is sent via email, then the email is formatted as a reply to the original thread (preserving subject line and threading).
- Given a customer replies to the email thread, when the reply is received, then Desk appends the reply to the existing conversation.

---

**US-CM-05: WhatsApp Baileys Bridge Setup**
_As a Desk operator, I want to connect WhatsApp via Baileys bridge without Meta Business verification so that I can start handling WhatsApp conversations in minutes, not weeks._

**Acceptance Criteria:**
- Given an operator navigates to Channel Settings in the admin dashboard, when the operator selects "WhatsApp (Baileys Bridge)," then a QR code is displayed for pairing.
- Given the operator scans the QR code with their WhatsApp mobile app (Linked Devices), when the pairing completes, then Desk confirms the connection and displays the paired phone number.
- Given the WhatsApp Baileys bridge is connected, when a customer sends a WhatsApp message, then Desk receives the message within 2 seconds and creates a conversation thread.
- Given the WhatsApp Baileys bridge loses connection (network issue, WhatsApp app unlinked), when the connection drops, then Desk automatically attempts to reconnect with exponential backoff.
- Given the WhatsApp Baileys session expires (30 days), when the session is about to expire, then Desk notifies the admin to re-pair before expiration.

---

**US-CM-06: WhatsApp Baileys Bridge Outbound Messages**
_As a Desk AI or human agent, I want to send responses via WhatsApp Baileys bridge so that customers receive answers without requiring Meta Business API setup._

**Acceptance Criteria:**
- Given Desk AI generates a response, when the response is approved (auto or manual), then the response is sent via WhatsApp Baileys bridge within 1 second.
- Given a human agent types a response in the agent inbox, when the agent clicks "Send," then the response is sent via WhatsApp Baileys bridge within 1 second.
- Given the WhatsApp Baileys bridge is disconnected, when Desk attempts to send a message, then the message is queued and sent when the connection is restored (with notification to admin).

---

**US-CM-07: Channel Adapter Configuration**
_As a Desk operator, I want to configure channel adapters via the admin dashboard so that I can manage which channels are active and how they connect._

**Acceptance Criteria:**
- Given an admin logs into the admin dashboard, when the admin navigates to "Channels," then the admin sees a list of all configured channel adapters with their status (connected, disconnected, error).
- Given an admin clicks "Add Channel," when the admin selects a channel type (WhatsApp Business, WhatsApp Baileys, Web Chat, Email), then the admin is presented with a configuration form specific to that channel.
- Given an admin configures a channel adapter, when the admin clicks "Enable," then the channel adapter connects and begins accepting messages.
- Given an admin disables a channel adapter, when the admin clicks "Disable," then the channel adapter stops accepting new messages but preserves existing conversations.
- Given a channel adapter encounters an error (authentication failure, connection timeout), when the error occurs, then the admin dashboard displays the error message and suggested resolution steps.

---

### 7.2 AI & Knowledge Retrieval

**US-AI-01: Vault Knowledge Retrieval**
_As a Desk operator, I want Desk to answer customer questions using my company's knowledge base so that responses are accurate and on-brand._

**Acceptance Criteria:**
- Given a customer asks a question, when Desk queries Vault, then Desk retrieves the top-K most relevant documents (K configurable, default 5).
- Given Vault returns relevant documents, when Desk generates a response, then the response is grounded in the retrieved documents (no hallucination of facts not in the knowledge base).
- Given Vault returns no relevant documents, when Desk generates a response, then Desk's behavior is governed by the active Response Policy: by default it says "I don't have that information, let me connect you with our team," and only uses the LLM's general knowledge if the admin has explicitly enabled general-knowledge fallback **and** the topic is not on the restricted-topics list (FR-RP-01/FR-RP-06).

---

**US-AI-02: Local Model Inference**
_As a Desk operator, I want to run AI inference locally so that customer data never leaves my infrastructure._

**Acceptance Criteria:**
- Given an admin configures a local model (Ollama, vLLM), when Desk receives a query, then Desk can route the query to the local model and receive a response.
- Given the local model is unavailable (down, overloaded), when Desk receives a query, then Desk falls back to the configured frontier model (if allowed by routing policy) or escalates to human.
- Given a local model is configured, when Desk routes a query to it, then the query and response are logged with model name, latency, and token count.

---

**US-AI-03: Frontier Model Inference**
_As a Desk operator, I want to route complex queries to a frontier model so that customers get high-quality answers for difficult questions._

**Acceptance Criteria:**
- Given an admin configures a frontier model (OpenAI, Anthropic), when Desk receives a query routed to the frontier model, then Desk sends the query (with PII redacted, if required) and receives a response.
- Given the frontier model API is unavailable, when Desk receives a query, then Desk falls back to the local model or escalates to human.
- Given a query is routed to a frontier model, when the response is received, then Desk logs the model name, latency, token count, and cost.

---

**US-AI-04: Model Routing**
_As a Desk operator, I want queries to be routed to the appropriate model based on privacy and complexity so that I balance data sovereignty with response quality._

**Acceptance Criteria:**
- Given a customer message contains PII, when Desk performs routing, then the message is routed to the local model (never to a frontier model, unless admin explicitly allows it with redaction).
- Given a customer message does not contain PII and the complexity score is < 0.7, when Desk performs routing, then the message is routed to the local model.
- Given a customer message does not contain PII and the complexity score is ≥ 0.7, when Desk performs routing, then the message is routed to the frontier model.
- Given an admin changes the routing policy, when the next query is received, then Desk uses the updated policy.

---

**US-AI-05: Confidence-Based Escalation**
_As a customer, I want to be connected to a human agent when the AI is unsure of the answer so that I get accurate help._

**Acceptance Criteria:**
- Given Desk AI generates a response with confidence < 60% (configurable), when the response is ready, then Desk escalates the conversation to a human agent instead of sending the response.
- Given a conversation is escalated, when the human agent takes over, then the agent sees the full conversation history and the AI's low-confidence response (marked as "not sent").
- Given a conversation is escalated, when the customer is waiting, then the customer receives a message: "Let me connect you with our team. One moment!"

---

### 7.3 Agent Inbox & Workflow

**US-AW-01: Agent Inbox**
_As a human agent, I want to see all conversations in one inbox so that I can manage support efficiently._

**Acceptance Criteria:**
- Given an agent logs into the inbox, when the inbox loads, then the agent sees all active conversations across all channels (WhatsApp, web chat, email).
- Given a conversation is flagged for review (low confidence, customer complaint, etc.), when the inbox loads, then the flagged conversation appears at the top with a visual indicator.
- Given an agent clicks a conversation, when the conversation loads, then the agent sees the full message history, customer profile, tags, and AI confidence scores.

---

**US-AW-02: Human Takeover**
_As a human agent, I want to take over an AI-handled conversation so that I can resolve complex issues._

**Acceptance Criteria:**
- Given an AI-handled conversation is escalated, when the agent clicks "Take Over," then the agent becomes the assigned responder and the AI stops auto-responding.
- Given an agent takes over, when the agent sends a message, then the message is sent as the human agent (not as the AI).
- Given an agent resolves the conversation, when the agent clicks "Resolve," then the conversation is marked as resolved and the AI can resume auto-responding if a new message arrives.

---

**US-AW-03: AI Response Feedback**
_As a human agent, I want to provide feedback on AI responses so that the AI improves over time._

**Acceptance Criteria:**
- Given an agent reviews an AI response, when the agent clicks "Incorrect," then the agent can provide a reason (e.g., "outdated info," "wrong tone," "hallucination").
- Given an agent provides feedback, when the feedback is submitted, then the feedback is logged and linked to the conversation and AI response.
- Given an admin reviews feedback, when the admin navigates to the Feedback dashboard, then the admin sees aggregated feedback (accuracy rate, common error types).

---

### 7.4 Data & Sovereignty

**US-DS-01: Data Export**
_As a Desk operator, I want to export all conversation data so that I can migrate to another system or fulfill data requests._

**Acceptance Criteria:**
- Given an admin requests a data export, when the export is generated, then the export includes all conversations, customer profiles, and audit logs in JSON or CSV format.
- Given an admin requests a data export for a specific customer, when the export is generated, then the export includes only that customer's data.
- Given a data export is requested, when the export is ready, then the admin receives a download link (expires after 24 hours).

---

**US-DS-02: Data Deletion**
_As a Desk operator, I want to delete customer data so that I can comply with GDPR right-to-erasure requests._

**Acceptance Criteria:**
- Given an admin requests deletion of a customer's data, when the deletion is executed, then all conversation history, customer profile, and audit logs for that customer are permanently deleted.
- Given a customer's data is deleted, when the admin checks the database, then no trace of the customer's data remains (except anonymized analytics, if configured).
- Given a deletion request is made, when the deletion is complete, then the admin receives a confirmation with a deletion certificate (timestamp, data deleted, verification hash).

---

**US-DS-03: Audit Log**
_As a Desk operator, I want to see an audit log of all AI decisions and data access so that I can demonstrate compliance._

**Acceptance Criteria:**
- Given a conversation is handled by AI, when the admin views the audit log, then the log entry includes: timestamp, customer ID, message content (redacted if PII), model used, confidence score, routing decision, and response content.
- Given an agent accesses a conversation, when the admin views the audit log, then the log entry includes: timestamp, agent ID, conversation ID, and action taken.
- Given an admin exports the audit log, when the export is generated, then the export includes all log entries for the specified date range in JSON or CSV format.

---

### 7.5 Deployment & Operations

**US-DO-01: Docker Compose Deployment**
_As a Desk operator, I want to deploy Desk with a single command so that I can get started quickly._

**Acceptance Criteria:**
- Given an operator runs `docker compose up`, when the containers start, then Desk is accessible at `http://localhost:3000` within 2 minutes.
- Given Desk is deployed via Docker Compose, when the operator checks the health endpoint, then the endpoint returns `{"status": "healthy"}`.
- Given an operator wants to upgrade Desk, when the operator runs `docker compose pull && docker compose up -d`, then Desk is upgraded to the latest version without data loss.

---

**US-DO-02: Kubernetes Deployment**
_As a Desk operator, I want to deploy Desk on Kubernetes so that I can scale and manage it with my existing infrastructure._

**Acceptance Criteria:**
- Given an operator runs `helm install desk ./helm/desk`, when the pods start, then Desk is accessible via the configured ingress within 5 minutes.
- Given Desk is deployed on Kubernetes, when the operator checks pod status, then all pods are in `Running` state.
- Given an operator wants to scale Desk, when the operator increases the replica count, then new pods start and handle traffic within 1 minute.

---

### 7.6 Suite Integration

**US-SI-01: Vault Integration**
_As a Desk operator, I want Desk to query my existing Vault knowledge base so that I don't have to re-upload documentation._

**Acceptance Criteria:**
- Given an operator configures Vault integration (provides Vault URL + API key), when Desk receives a query, then Desk queries Vault and retrieves relevant documents.
- Given Vault is co-deployed with Desk (same Docker Compose file), when the operator runs the setup wizard, then Vault is auto-detected and no API key is required.
- Given Vault returns documents, when Desk generates a response, then the response cites the source documents (visible to agents in the inbox, not to customers).

---

**US-SI-02: Single Sign-On**
_As a Desk operator, I want to use the same login for Desk and other ODW.ai modules so that I don't have to manage multiple accounts._

**Acceptance Criteria:**
- Given an operator logs into ODW.ai suite, when the operator navigates to Desk, then the operator is automatically logged in (no separate login required).
- Given an operator's role is "Agent" in ODW.ai suite, when the operator accesses Desk, then the operator has agent-level permissions (can access inbox, cannot access admin settings).
- Given an operator's role is "Admin" in ODW.ai suite, when the operator accesses Desk, then the operator has admin-level permissions (can access all settings).

---

### 7.7 Brand Persona & Voice

**US-BP-01: Brand Persona Configuration**
_As an operator, I want to configure how Desk speaks so it represents my business's voice._

**Acceptance Criteria:**
- Given an operator navigates to the Brand Persona settings in the admin dashboard, when the operator configures persona fields (tone, formality, vocabulary, emoji policy, signature phrases), then the configuration is saved and validated.
- Given a Brand Persona is configured, when Desk generates a response, then the persona is injected into the system prompt and applied to all AI generations.
- Given an operator wants to test the persona, when the operator uses the preview/test tool with sample messages, then Desk generates responses reflecting the configured persona without affecting live conversations.
- Given an operator updates the Brand Persona, when the next customer message arrives, then the updated persona takes effect immediately without requiring a redeploy or restart.

---

**US-BP-02: Fine-Tuned Persona Backend (LoRA/QLoRA)**
_As a technical operator, I want to plug in a LoRA-fine-tuned local model so my small model consistently follows our tone._

**Acceptance Criteria:**
- Given an operator configures a LoRA adapter path (local or S3 URI), when Desk starts up, then the adapter is validated (base model match, integrity check) and loaded.
- Given a LoRA adapter is configured and loaded, when Desk performs inference, then the adapter-backed model is used for persona-aware generation.
- Given the LoRA adapter fails to load (missing file, base model mismatch, corruption), when Desk attempts inference, then Desk falls back to prompt-based persona with the base model and logs the failure.
- Given a response is generated using a LoRA adapter, when the audit log is written, then the log entry records `persona_backend_used: 'lora_adapter'` and the adapter version/URI.

---

### 7.8 Response Policy & Guardrails

**US-RP-01: Competitor Redirect**
_As an operator, I want competitor mentions handled by an approved redirect rather than factual competitor info._

**Acceptance Criteria:**
- Given a customer message mentions a competitor (configured in Response Policy), when the Policy Engine pre-hook runs, then the competitor intent is detected.
- Given a competitor intent is detected, when the Policy Engine evaluates actions, then the configured redirect/template response is served instead of generating a general-knowledge response about the competitor.
- Given a competitor redirect is served, when the response is sent, then no factual competitor information from the LLM's general knowledge is emitted.
- Given a policy action is taken, when the audit log is written, then the log entry records the policy trigger, matched rule, and action taken.

---

**US-RP-02: Disclaimer / Sensitive Topic Handling**
_As a regulated operator, I want legal/medical responses to carry required disclaimers or escalate to a human._

**Acceptance Criteria:**
- Given a customer message matches a sensitive topic intent (legal, medical, financial advice), when the Policy Engine evaluates the message, then the configured action is applied (append disclaimer, inject context, or escalate to human).
- Given a disclaimer action is configured, when a matching response is generated, then the disclaimer is automatically appended to the response before sending.
- Given an escalate-to-human action is configured, when a matching message is detected, then the conversation is escalated to a human agent with the policy trigger reason logged.
- Given a policy action is taken, when the audit log is written, then the log entry records the policy trigger, action taken, and any disclaimer text appended.

---

## 8. Non-Functional Requirements (NFRs)

### 8.1 Performance

| ID | Requirement | Target | Measurement |
|---|---|---|---|
| NFR-P-01 | AI response latency (end-to-end, from customer message to AI response sent) | <5 seconds (local model), <8 seconds (frontier model) | P95 latency |
| NFR-P-02 | Agent inbox load time | <2 seconds | P95 latency |
| NFR-P-03 | Web chat widget load time | <1 second | P95 latency |
| NFR-P-04 | Concurrent conversations supported per deployment | 1,000+ | Load test |
| NFR-P-05 | Message throughput | 100 messages/second | Load test |
| NFR-P-06 | Database query latency (conversation lookup) | <100ms | P95 latency |
| NFR-P-07 | Vault query latency (knowledge retrieval) | <500ms | P95 latency |

### 8.2 Scalability

| ID | Requirement | Target |
|---|---|---|
| NFR-S-01 | Horizontal scaling of application tier | Stateless; can scale to 10+ replicas |
| NFR-S-02 | Database scaling | PostgreSQL with read replicas; support for connection pooling (PgBouncer) |
| NFR-S-03 | Message queue scaling | Redis or RabbitMQ; can handle 10,000+ messages/minute |
| NFR-S-04 | Storage scaling | Object storage (S3-compatible) for media files; no hard limit on conversation history |
| NFR-S-05 | Multi-tenancy (future) | Architecture must support multi-tenancy in v2 (not MVP, but design for it) |

### 8.3 Reliability & Availability

| ID | Requirement | Target |
|---|---|---|
| NFR-R-01 | Uptime SLA (for paid tier, self-hosted) | 99.5% (operator-managed, but Desk provides tooling to achieve this) |
| NFR-R-02 | Zero-downtime deployments | Supported via blue-green or rolling updates |
| NFR-R-03 | Graceful degradation | If AI is unavailable, conversations are queued and agents are notified; no data loss |
| NFR-R-04 | Data durability | 99.999% (via PostgreSQL replication and backups) |
| NFR-R-05 | Recovery time objective (RTO) | <1 hour |
| NFR-R-06 | Recovery point objective (RPO) | <5 minutes (via continuous WAL archiving) |

### 8.4 Security

| ID | Requirement | Target |
|---|---|---|
| NFR-SEC-01 | Encryption at rest | AES-256 for database, S3-compatible storage |
| NFR-SEC-02 | Encryption in transit | TLS 1.3 for all external and internal communication |
| NFR-SEC-03 | Authentication | OAuth 2.0 / OIDC for admin and agent login; API keys for programmatic access |
| NFR-SEC-04 | Authorization | Role-based access control (RBAC): Admin, Agent, Read-Only |
| NFR-SEC-05 | PII protection | PII detection and redaction before sending to external models; encryption of PII at rest |
| NFR-SEC-06 | Audit logging | All data access and AI decisions logged; logs are tamper-evident |
| NFR-SEC-07 | Vulnerability scanning | Automated dependency scanning in CI/CD; no critical vulnerabilities in production |
| NFR-SEC-08 | Rate limiting | API rate limiting to prevent abuse (configurable per deployment) |
| NFR-SEC-09 | Input validation | All user inputs validated and sanitized to prevent injection attacks |
| NFR-SEC-10 | Secrets management | Secrets stored in environment variables or secrets manager (Vault, AWS Secrets Manager); never in code or logs |

### 8.5 Compliance

| ID | Requirement | Target |
|---|---|---|
| NFR-C-01 | GDPR compliance | Data export, deletion, and consent management supported |
| NFR-C-02 | HIPAA compliance | BAA support (for paid tier); encryption and audit logging meet HIPAA requirements |
| NFR-C-03 | LGPD compliance | Data residency and export supported for Brazilian deployments |
| NFR-C-04 | SOC 2 Type II | Roadmap for SOC 2 certification (v2, not MVP) |
| NFR-C-05 | Data residency | Operators can choose deployment region; no data leaves the region unless explicitly configured |

### 8.6 Usability

| ID | Requirement | Target |
|---|---|---|
| NFR-U-01 | Time-to-first-value | <2 hours from deployment to first AI-handled conversation |
| NFR-U-02 | Documentation | Comprehensive docs: quickstart, API reference, deployment guides, troubleshooting |
| NFR-U-03 | Error messages | Clear, actionable error messages with links to docs |
| NFR-U-04 | Accessibility | WCAG 2.1 AA compliance for admin dashboard and agent inbox |
| NFR-U-05 | Internationalization | UI supports English + one additional language (MVP); extensible for more languages |
| NFR-U-06 | Mobile responsiveness | Agent inbox and admin dashboard usable on tablets; mobile phone support in v1.1 |

### 8.7 Maintainability

| ID | Requirement | Target |
|---|---|---|
| NFR-M-01 | Code quality | Test coverage ≥80%; no critical linting errors |
| NFR-M-02 | API versioning | All APIs versioned (e.g., `/api/v1/...`); backward compatibility for 2 major versions |
| NFR-M-03 | Database migrations | Automated migrations via Alembic (or similar); no manual SQL required |
| NFR-M-04 | Logging | Structured logging (JSON); log levels configurable; no PII in logs |
| NFR-M-05 | Monitoring | Prometheus metrics + Grafana dashboards; alerting on key metrics |
| NFR-M-06 | Open-source components | Core is open-source (AGPL-3.0); paid features are proprietary (open-core model) |

---

## 9. Data & State Requirements

### 9.1 Core Data Models

#### 9.1.1 Conversation

| Field | Type | Description |
|---|---|---|
| id | UUID | Primary key |
| customer_id | UUID | Foreign key to Customer |
| channel | ENUM | 'whatsapp', 'web_chat', 'email' |
| channel_conversation_id | VARCHAR | External conversation ID (e.g., WhatsApp conversation ID) |
| status | ENUM | 'active', 'pending', 'resolved', 'escalated' |
| assigned_agent_id | UUID | Foreign key to Agent (nullable) |
| ai_enabled | BOOLEAN | Whether AI is auto-responding |
| created_at | TIMESTAMP | Conversation start time |
| updated_at | TIMESTAMP | Last activity time |
| resolved_at | TIMESTAMP | Resolution time (nullable) |
| tags | JSONB | Conversation tags (e.g., ['billing', 'urgent']) |
| metadata | JSONB | Channel-specific metadata |

#### 9.1.2 Message

| Field | Type | Description |
|---|---|---|
| id | UUID | Primary key |
| conversation_id | UUID | Foreign key to Conversation |
| sender_type | ENUM | 'customer', 'ai', 'agent' |
| sender_id | UUID | Foreign key to Customer or Agent (nullable for AI) |
| content | TEXT | Message content |
| media_urls | JSONB | Array of media file URLs (nullable) |
| ai_model_used | VARCHAR | Model name (if sender_type = 'ai') |
| ai_confidence | FLOAT | Confidence score (if sender_type = 'ai') |
| ai_routing_decision | JSONB | Routing details (model, reason, PII detected) |
| created_at | TIMESTAMP | Message send time |
| redacted_content | TEXT | PII-redacted version (if sent to external model) |

#### 9.1.3 Customer

| Field | Type | Description |
|---|---|---|
| id | UUID | Primary key |
| channel_identifiers | JSONB | Map of channel to identifier (e.g., {'whatsapp': '+1234567890', 'email': 'customer@example.com'}) |
| name | VARCHAR | Customer name (nullable) |
| pii_data | JSONB | Encrypted PII (name, phone, email, etc.) |
| created_at | TIMESTAMP | First contact time |
| updated_at | TIMESTAMP | Last update time |
| metadata | JSONB | Custom fields |

#### 9.1.4 Agent

| Field | Type | Description |
|---|---|---|
| id | UUID | Primary key |
| user_id | UUID | Foreign key to ODW.ai User (SSO) |
| name | VARCHAR | Agent name |
| email | VARCHAR | Agent email |
| role | ENUM | 'admin', 'agent', 'read_only' |
| status | ENUM | 'online', 'offline', 'away' |
| created_at | TIMESTAMP | Account creation time |

#### 9.1.5 AI Configuration

| Field | Type | Description |
|---|---|---|
| id | UUID | Primary key |
| local_model_endpoint | VARCHAR | Ollama/vLLM endpoint URL |
| local_model_name | VARCHAR | Model name (e.g., 'llama3:8b') |
| frontier_model_provider | ENUM | 'openai', 'anthropic', 'none' |
| frontier_model_name | VARCHAR | Model name (e.g., 'gpt-4o') |
| frontier_api_key_encrypted | TEXT | Encrypted API key |
| routing_policy | JSONB | Routing rules (PII → local, complexity threshold, etc.) |
| confidence_threshold | FLOAT | Escalation threshold (default 0.6) |
| system_prompt | TEXT | Custom system prompt |
| vault_collection_id | UUID | Vault collection to query |
| created_at | TIMESTAMP | Configuration creation time |
| updated_at | TIMESTAMP | Last update time |

#### 9.1.6 Audit Log

| Field | Type | Description |
|---|---|---|
| id | UUID | Primary key |
| timestamp | TIMESTAMP | Event time |
| event_type | ENUM | 'ai_decision', 'data_access', 'data_deletion', 'config_change', 'login' |
| actor_type | ENUM | 'ai', 'agent', 'admin', 'system' |
| actor_id | UUID | Foreign key to Agent or Admin (nullable for AI/system) |
| resource_type | VARCHAR | Resource accessed (e.g., 'conversation', 'customer') |
| resource_id | UUID | Resource ID |
| action | VARCHAR | Action taken (e.g., 'read', 'delete', 'respond') |
| details | JSONB | Event details (e.g., model used, confidence score) |
| ip_address | VARCHAR | Actor's IP address |

### 9.2 State Management

#### 9.2.1 Conversation State Machine

```
[active] → [pending] (customer inactive for 24h)
[active] → [escalated] (AI confidence < threshold, or agent takes over)
[escalated] → [active] (agent hands back to AI)
[active|pending|escalated] → [resolved] (agent resolves, or AI resolves with high confidence)
[resolved] → [active] (customer sends new message)
```

#### 9.2.2 Message Queue

- **Inbound message queue:** Redis or RabbitMQ; messages are queued when received from channels and processed by AI/agent workers.
- **Outbound message queue:** Messages to be sent via channels are queued and processed by channel-specific workers.
- **Retry policy:** Failed messages are retried 3 times with exponential backoff (1s, 5s, 30s); after 3 failures, message is moved to dead-letter queue and admin is notified.

#### 9.2.3 Caching

- **Customer lookup cache:** Redis cache for customer profiles (TTL: 5 minutes); reduces database lookups for repeat customers.
- **Vault query cache:** Redis cache for Vault query results (TTL: 10 minutes); reduces latency for repeated questions.
- **Session cache:** Redis cache for conversation context (TTL: 30 minutes); enables fast multi-turn conversation handling.

### 9.3 Data Retention & Archival

| Data Type | Retention Policy | Archival |
|---|---|---|
| Conversations | Configurable (default: 2 years) | Archived to cold storage (S3 Glacier) after retention period |
| Messages | Same as conversations | Same as conversations |
| Customer profiles | Until deletion request or account closure | Archived to cold storage |
| Audit logs | 7 years (compliance requirement) | Archived to cold storage after 1 year |
| Media files | Same as conversations | Archived to cold storage |
| AI decision logs | 3 years | Archived to cold storage after 1 year |

### 9.4 Data Encryption

| Data Type | Encryption at Rest | Encryption in Transit |
|---|---|---|
| Conversation content | AES-256 (database-level encryption) | TLS 1.3 |
| Customer PII | AES-256 (field-level encryption) | TLS 1.3 |
| API keys / secrets | AES-256 (encrypted via secrets manager) | TLS 1.3 |
| Media files | AES-256 (S3 server-side encryption) | TLS 1.3 |
| Audit logs | AES-256 (database-level encryption) | TLS 1.3 |

### 9.5 Data Backup & Recovery

| Backup Type | Frequency | Retention | Recovery Time |
|---|---|---|---|
| Full database backup | Daily | 30 days | <1 hour |
| Incremental backup (WAL archiving) | Continuous | 7 days | <5 minutes (point-in-time recovery) |
| Media file backup | Daily | 30 days | <1 hour |
| Configuration backup | On change | 90 days | <5 minutes |

---

## 10. Assumptions & Constraints

### 10.1 Assumptions

1. **Operators have technical capability to self-host.** Target customers have IT staff or can hire consultants to deploy and maintain Docker/Kubernetes infrastructure.
2. **WhatsApp Business API access is available.** Operators can obtain WhatsApp Business API access via Meta directly or through a Business Solution Provider (BSP).
3. **Vault is available or can be co-deployed.** Operators either already use ODW.ai Vault or can deploy it alongside Desk (Docker Compose supports co-deployment).
4. **Local models are sufficient for most queries.** Operators can run local models (e.g., Llama 3 8B) on commodity hardware (16GB RAM, GPU optional) and achieve acceptable quality for 60%+ of queries.
5. **Operators are willing to manage infrastructure.** Target customers prefer data sovereignty over managed convenience and are willing to handle updates, backups, and monitoring.
6. **Regulatory compliance is a key motivator.** Target customers are motivated by GDPR, HIPAA, LGPD, or similar regulations and are willing to pay for compliance features.
7. **Open-source core is viable.** Open-core model (AGPL-3.0 for core, proprietary for paid features) is sustainable and does not cannibalize paid tier.
8. **WhatsApp is the dominant channel.** In target markets (EU, LATAM, SEA, Africa), WhatsApp is the primary customer communication channel, and customers expect support on WhatsApp.
9. **AI quality is sufficient for support.** Current LLMs (GPT-4, Claude, Llama 3) are capable of handling customer support queries with acceptable accuracy when grounded in a knowledge base.
10. **Operators will configure routing policies.** Operators will actively configure model routing policies (PII detection, complexity thresholds) and monitor AI performance.

### 10.2 Constraints

1. **WhatsApp Business API limitations.** WhatsApp imposes rate limits, message template requirements, and 24-hour conversation windows. Desk must operate within these constraints.
2. **Local model quality.** Local models (e.g., Llama 3 8B) are less capable than frontier models (GPT-4, Claude). Desk must handle lower-quality responses gracefully (escalation, disclaimers).
3. **Self-hosted complexity.** Self-hosting is inherently more complex than SaaS. Desk must minimize complexity (single-command deployment, comprehensive docs) but cannot eliminate it entirely.
4. **Open-source licensing.** AGPL-3.0 requires derivative works to be open-source. This limits enterprise adoption in some contexts (companies that want to modify and not share changes).
5. **Resource constraints.** MVP must be delivered in 6 months with a team of 5–7 engineers. Scope must be tightly managed.
6. **Integration complexity.** Deep Vault integration requires tight coupling with ODW.ai suite. Changes to Vault API may break Desk.
7. **Regulatory uncertainty.** Data-residency and AI regulations are evolving. Desk must be flexible enough to adapt to new requirements.
8. **Competitive pressure.** Chatwoot, Botpress, and others may add similar features (self-hosted, WhatsApp-first, model-agnostic). Desk must move fast and differentiate on suite integration and sovereignty.
9. **Customer education.** Target customers may not understand the value of self-hosted AI support. Marketing and sales must educate the market.
10. **Model cost.** Frontier model inference is expensive ($0.01–$0.10 per query). Desk must optimize routing to minimize cost (use local models when possible).

---

## 11. Risks & Mitigations

### 11.1 Technical Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **WhatsApp Business API changes or restrictions** | Medium | High | Abstract WhatsApp integration behind a channel adapter; support multiple BSPs; provide fallback to web chat |
| **Local model quality insufficient for support** | High | Medium | Provide clear guidance on model selection; offer hybrid routing (local + frontier); allow operators to fine-tune models externally |
| **Vault integration breaks on Vault updates** | Medium | High | Version Vault API; provide compatibility matrix; test Desk against multiple Vault versions in CI |
| **Performance degradation at scale** | Medium | High | Load test early and often; design for horizontal scaling; provide scaling guides; offer paid support for large deployments |
| **Security vulnerability in open-source dependencies** | High | High | Automated dependency scanning in CI; rapid patch release process; security advisories for customers |
| **Data loss during deployment or upgrade** | Low | Critical | Comprehensive backup tooling; automated pre-upgrade backups; rollback mechanism; extensive testing |
| **PII leak to frontier model** | Low | Critical | PII detection before routing; encryption of PII at rest; audit logging; automated testing of PII redaction |

### 11.2 Market Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **Chatwoot or Botpress adds similar features** | High | Medium | Differentiate on suite integration (Vault, SSO, unified dashboard); move fast; build community |
| **Cloud SaaS adds self-hosted option** | Low | High | Unlikely (conflicts with SaaS business model); monitor and respond if it happens |
| **Target market too small** | Medium | High | Validate market size with customer interviews; expand to adjacent markets (developer tools, agencies) if needed |
| **Open-core model cannibalizes paid tier** | Medium | Medium | Ensure paid tier provides clear value (WhatsApp connector, compliance features, SLA support); monitor conversion rates |
| **Customer education barrier** | High | Medium | Comprehensive docs, video tutorials, webinars; offer paid onboarding; build community (Discord, forums) |
| **Pricing too high for SMBs** | Medium | Medium | Offer tiered pricing (free, starter, pro, enterprise); provide ROI calculator; offer annual discounts |

### 11.3 Operational Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **Team burnout from aggressive timeline** | High | Medium | Prioritize MVP scope; hire additional engineers if needed; provide team support (mental health, time off) |
| **Key person dependency** | Medium | High | Document architecture and decisions; cross-train team; avoid single points of failure in knowledge |
| **Customer support overload** | Medium | Medium | Comprehensive docs and community support; paid tier includes SLA support; automate common support tasks |
| **Regulatory changes require rapid adaptation** | Medium | High | Modular architecture; configurable compliance features; monitor regulatory developments; engage legal counsel |
| **Supply chain attack (compromised dependency)** | Low | Critical | Lock dependencies; verify checksums; use private registry for critical dependencies; monitor for vulnerabilities |

### 11.4 Legal & Compliance Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **AGPL-3.0 licensing dispute** | Low | Medium | Engage open-source legal counsel; provide clear licensing documentation; offer commercial license for companies that cannot comply with AGPL |
| **GDPR non-compliance claim** | Low | Critical | Implement all GDPR requirements (export, deletion, consent); engage legal counsel; provide compliance documentation |
| **HIPAA non-compliance claim** | Low | Critical | Implement all HIPAA requirements (encryption, audit logging, BAA); engage legal counsel; provide compliance documentation |
| **Data breach** | Low | Critical | Encryption at rest and in transit; access controls; audit logging; incident response plan; cyber insurance |
| **WhatsApp Business API terms violation** | Low | High | Review WhatsApp terms; ensure compliance (message templates, opt-in requirements); engage legal counsel |

---

## 12. Dependencies

### 12.1 Internal Dependencies

| Dependency | Description | Owner | Status | Risk |
|---|---|---|---|---|
| **ODW.ai Vault** | Knowledge base for RAG retrieval | Vault team | Stable API (v1.2) | Medium (API changes may break integration) |
| **ODW.ai Auth / SSO** | Single sign-on and user management | Platform team | Stable API (v2.0) | Low |
| **ODW.ai Billing** | Licensing and subscription management | Billing team | In development (v1.0) | High (delayed billing may delay paid tier launch) |
| **ODW.ai Admin Dashboard** | Unified admin UI for suite | Frontend team | In development (v1.0) | Medium (may delay Desk integration) |
| **ODW.ai Documentation** | Docs site and API reference | Docs team | Stable | Low |

### 12.2 External Dependencies

| Dependency | Description | Provider | Status | Risk |
|---|---|---|---|---|
| **WhatsApp Business API** | WhatsApp messaging (enterprise path) | Meta | Stable | Medium (API changes, rate limits, terms changes) |
| **WhatsApp Business Solution Provider (BSP)** | WhatsApp Business API access (for operators who don't want to deal with Meta directly) | Twilio, 360dialog, MessageBird | Stable | Low (multiple providers available) |
| **Baileys** | WhatsApp Web bridge library (quick-start path) | WhiskeySockets (open-source) | Stable | High (reverse-engineered protocol, may break on WhatsApp updates) |
| **OpenAI API** | Frontier model inference (GPT-4, GPT-4o) | OpenAI | Stable | Low (multiple providers available) |
| **Anthropic API** | Frontier model inference (Claude 3.5, Claude 3 Opus) | Anthropic | Stable | Low (multiple providers available) |
| **Ollama** | Local model inference | Ollama (open-source) | Stable | Low (open-source, self-hosted) |
| **vLLM** | Local model inference (high-performance) | vLLM (open-source) | Stable | Low (open-source, self-hosted) |
| **PostgreSQL** | Primary database | PostgreSQL Global Development Group | Stable | Low (mature, widely used) |
| **Redis** | Caching and message queue | Redis Ltd | Stable | Low (mature, widely used) |
| **RabbitMQ** | Message queue (alternative to Redis) | RabbitMQ (open-source) | Stable | Low (mature, widely used) |
| **Docker** | Containerization | Docker, Inc. | Stable | Low (mature, widely used) |
| **Kubernetes** | Container orchestration | Cloud Native Computing Foundation | Stable | Low (mature, widely used) |
| **React** | Frontend framework (admin dashboard, agent inbox) | Meta (open-source) | Stable | Low (mature, widely used) |
| **FastAPI** | Backend framework (API server) | FastAPI (open-source) | Stable | Low (mature, widely used) |
| **LangChain / LlamaIndex** | RAG framework (Vault integration) | LangChain / LlamaIndex (open-source) | Stable | Medium (rapidly evolving, API changes) |

### 12.3 Critical Path Dependencies

| Dependency | Critical Path? | Mitigation if Delayed |
|---|---|---|
| **ODW.ai Vault** | Yes (MVP) | Provide mock Vault for testing; allow operators to use external vector stores (Pinecone, Weaviate) as fallback |
| **ODW.ai Billing** | Yes (paid tier) | Launch free tier first; delay paid tier if billing is not ready |
| **WhatsApp Business API** | Yes (MVP, enterprise path) | Launch with Baileys bridge + web chat + email first; add Business API in v1.1 if API access is delayed |
| **Baileys Bridge** | Yes (MVP, quick-start path) | Launch with Business API + web chat + email first; add Baileys bridge in v1.1 if library stability is insufficient |
| **OpenAI / Anthropic API** | No | Operators can use local models only; no hard dependency on frontier models |
| **ODW.ai Admin Dashboard** | No | Desk can have standalone admin dashboard; integrate with unified dashboard in v1.1 |

---

## 13. Open Questions

### 13.1 Product & Strategy

1. **Should Desk support multi-tenancy (multiple organizations on a single deployment) for agency partners?**
   - Pro: Opens up agency/white-label market.
   - Con: Adds complexity; may conflict with sovereignty messaging.
   - Decision needed: v1.1 or v2?

2. **Should Desk offer a managed hosting option (ODW.ai-hosted Desk) for customers who want sovereignty but lack infrastructure?**
   - Pro: Expands market to customers who can't self-host.
   - Con: Conflicts with self-hosted positioning; adds operational complexity.
   - Decision needed: Yes/No? If yes, when?

3. **Should Desk support generative actions (e.g., "create a refund," "update customer record") in v1.1?**
   - Pro: Increases AI resolution rate; differentiates from Chatwoot.
   - Con: Adds complexity; requires integration with operator's systems (CRM, billing).
   - Decision needed: v1.1 scope?

4. **Should Desk support voice support (voice notes on WhatsApp, IVR)?**
   - Pro: WhatsApp voice notes are popular in some markets.
   - Con: Adds complexity (speech-to-text, text-to-speech); may not be MVP.
   - Decision needed: v1.1 or v2?

5. **Should Desk provide pre-built integrations with popular CRMs (Salesforce, HubSpot, Zoho)?**
   - Pro: Increases adoption; reduces custom integration work.
   - Con: Adds maintenance burden; may not align with "sovereign, minimal" positioning.
   - Decision needed: v1.1 or community-contributed?

### 13.2 Technical

6. **Should Desk use a unified message queue (Redis or RabbitMQ) for all channels, or channel-specific queues?**
   - Pro (unified): Simpler architecture; easier to scale.
   - Pro (channel-specific): Better isolation; channel-specific retry policies.
   - Decision needed: Before MVP architecture finalization.

7. **Should Desk use a vector database (Pinecone, Weaviate, Qdrant) for Vault integration, or query Vault's existing vector store?**
   - Pro (Vault's vector store): Tighter integration; no additional infrastructure.
   - Pro (separate vector DB): More flexibility; can use different embedding models.
   - Decision needed: Depends on Vault team's roadmap.

8. **Should Desk support offline mode (air-gapped deployments with no internet access)?**
   - Pro: Required for some regulated industries (government, military).
   - Con: Adds complexity; cannot use frontier models or WhatsApp Business API.
   - Decision needed: v1.1 or v2?

9. **Should Desk use a microservices architecture or a monolith?**
   - Pro (microservices): Easier to scale individual components; better isolation.
   - Pro (monolith): Simpler to develop and deploy; faster iteration.
   - Decision needed: Before MVP architecture finalization. Recommendation: start with modular monolith, split into microservices if needed.

10. **Should Desk support real-time collaboration (multiple agents working on the same conversation)?**
    - Pro: Useful for large support teams.
    - Con: Adds complexity (conflict resolution, presence management).
    - Decision needed: v1.1 or v2?

11. **Should Desk ship a hosted fine-tuning pipeline, or only support loading externally-trained LoRA adapters?**
    - Pro (hosted pipeline): Easier for operators; end-to-end experience.
    - Pro (load only): Keeps core deployment lightweight; training is GPU-bound and occasional; operators can use external tools (Hugging Face, Axolotl).
    - Decision needed: v1.1 scope? Recommendation: support loading only; document external training workflow.

12. **Should the intent classifier (for Response Policy) be rule-based, a small local classifier model, or an LLM call?**
    - Pro (rule-based): Fast, free, transparent, deterministic — perfect for competitor names and banned terms.
    - Pro (local classifier): Handles fuzzier intents; still fast and private.
    - Pro (LLM call): Most flexible; but adds latency and cost.
    - Decision needed: Before MVP. Recommendation: tiered approach (deterministic rules first, optional classifier/LLM for complex intents).

13. **Should post-generation policy checking run on every message (latency cost) or only on policy-flagged ones?**
    - Pro (every message): Catches all violations; safer.
    - Pro (flagged only): Lower latency; only checks messages that triggered pre-hook rules.
    - Decision needed: Before MVP. Recommendation: check all messages when guardrails are enabled (paid tier); make it configurable.

### 13.3 Business & Go-to-Market

11. **What is the pricing model for the paid tier?**
    - Options: per-seat, per-conversation, flat monthly fee, usage-based.
    - Decision needed: Before paid tier launch. Recommendation: flat monthly fee + usage-based for frontier model inference.

12. **Should Desk offer a free trial of the paid tier (e.g., 14-day trial with WhatsApp connector)?**
    - Pro: Increases conversion to paid.
    - Con: Adds complexity; may attract free-tier users who never convert.
    - Decision needed: Before paid tier launch.

13. **What is the go-to-market strategy for regulated industries?**
    - Options: direct sales, partnerships with compliance consultants, content marketing (whitepapers, webinars).
    - Decision needed: Before launch. Recommendation: content marketing + partnerships with compliance consultants.

14. **Should Desk pursue SOC 2 Type II certification before launch?**
    - Pro: Increases trust with enterprise customers.
    - Con: Expensive ($50k–$100k); takes 6–12 months.
    - Decision needed: v1.1 or v2? Recommendation: v2 (after initial traction).

15. **Should Desk pursue HIPAA certification (or provide a BAA) before launch?**
    - Pro: Opens up healthcare market (high willingness to pay).
    - Con: Requires additional compliance work (BAA, audit logging, encryption).
    - Decision needed: Before paid tier launch. Recommendation: provide BAA for paid tier (healthcare is a key target market).

### 13.4 Legal & Compliance

16. **Is AGPL-3.0 the right license for the open-source core?**
    - Pro: Ensures derivative works are open-source; aligns with open-source values.
    - Con: May limit enterprise adoption (some companies cannot comply with AGPL).
    - Decision needed: Before open-source launch. Recommendation: AGPL-3.0 for core, commercial license available for companies that cannot comply.

17. **How should Desk handle data residency for customers in regions with strict data-localization laws (e.g., Russia, China)?**
    - Pro: Opens up additional markets.
    - Con: Adds complexity; may require region-specific deployments.
    - Decision needed: v2? Recommendation: support any region where operators can self-host; no region-specific features in MVP.

18. **Should Desk provide a Data Processing Agreement (DPA) template for customers?**
    - Pro: Simplifies GDPR compliance for customers.
    - Con: Requires legal review; may need to be customized per customer.
    - Decision needed: Before paid tier launch. Recommendation: provide DPA template for paid tier.

---

## Appendix A: Glossary

| Term | Definition |
|---|---|
| **AI** | Artificial Intelligence; in this document, refers to the LLM-based conversational agent. |
| **Agent** | A human customer support representative who uses the Desk agent inbox. |
| **BSP** | Business Solution Provider; a company that provides WhatsApp Business API access (e.g., Twilio, 360dialog). |
| **Channel** | A communication platform (WhatsApp, web chat, email) through which customers interact with Desk. |
| **Conversation** | A thread of messages between a customer and Desk (AI or human agent). |
| **Desk** | The ODW.ai product described in this PRD: a self-hosted, WhatsApp-first AI customer-support agent. |
| **Frontier model** | A state-of-the-art LLM (e.g., GPT-4, Claude 3.5) provided by a third-party API. |
| **GDPR** | General Data Protection Regulation; EU data privacy law. |
| **HIPAA** | Health Insurance Portability and Accountability Act; US healthcare data privacy law. |
| **LGPD** | Lei Geral de Proteção de Dados; Brazilian data privacy law. |
| **Local model** | An LLM running on the operator's own infrastructure (e.g., Llama 3 via Ollama). |
| **MVP** | Minimum Viable Product; the first release of Desk with core features. |
| **ODW.ai** | The suite of products that Desk is part of (includes Vault, etc.). |
| **PII** | Personally Identifiable Information; data that can identify an individual (name, phone number, email, etc.). |
| **RAG** | Retrieval-Augmented Generation; a technique for grounding LLM responses in retrieved documents. |
| **Sovereignty** | Data sovereignty; the principle that data is subject to the laws of the country where it is stored. |
| **Vault** | The ODW.ai knowledge base product; stores documents and provides RAG retrieval. |

---

## Appendix B: References

- **WhatsApp Business API documentation:** https://developers.facebook.com/docs/whatsapp
- **GDPR overview:** https://gdpr.eu/
- **HIPAA overview:** https://www.hhs.gov/hipaa/index.html
- **LGPD overview:** https://lgpd-brazil.com/
- **ODW.ai Vault documentation:** [internal link]
- **ODW.ai suite architecture:** [internal link]
- **Competitive analysis:** [internal link]
- **Customer interviews:** [internal link]

---

## Appendix C: Revision History

| Version | Date | Author | Changes |
|---|---|---|---|
| 1.0 | 2026-06-23 | ODW.ai Product Team | Initial draft |
| 1.1 | 2026-06-24 | ODW.ai Product Team | Added dual WhatsApp strategy (Business API + Baileys bridge), channel-agnostic adapter architecture, future optional channels (Telegram, Discord, Slack, Signal, iMessage) |

---

**End of Document**
