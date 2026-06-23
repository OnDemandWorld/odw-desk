
## 1. PRD additions

### 1.1 New section under §1.6 Key Differentiators (add item 8)

> **8. Brand Persona, not generic bot.** Desk is a front-desk agent that *represents the business*. Operators configure a brand voice (tone, vocabulary, formality, do's/don'ts) and response policies so a restaurant taking bookings sounds like that restaurant, and a law firm sounds like that firm. Persona is configurable out of the box and can be reinforced with optional local-model fine-tuning for operators who want maximum consistency.

### 1.2 New functional requirements

Add two new requirement groups to §6. I've kept your ID and priority conventions.

**§6.8 Brand Persona & Voice**

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

**§6.9 Response Policy & Guardrails**

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

### 1.3 Critical PRD edit (resolve the conflict I flagged earlier)

Update **US-AI-01 acceptance criterion (c)**. Current wording lets the model fall back to general knowledge with a disclaimer — that directly defeats the competitor-redirect goal. New wording:

> (c) Given Vault returns no relevant documents, when Desk generates a response, then Desk's behavior is governed by the active Response Policy: by default it says "I don't have that information, let me connect you with our team," and only uses the LLM's general knowledge if the admin has explicitly enabled general-knowledge fallback **and** the topic is not on the restricted-topics list (FR-RP-01/FR-RP-06).

### 1.4 New user stories

Add to §7. Abbreviated here; your agent can expand to full Gherkin matching your house style.

**US-BP-01 (Brand Persona):** *As an operator, I want to configure how Desk speaks so it represents my business's voice.* AC: persona fields editable in dashboard; persona applied to all generations; preview against test messages; changes take effect on next message without redeploy.

**US-BP-02 (Fine-tuned persona):** *As a technical operator, I want to plug in a LoRA-fine-tuned local model so my small model consistently follows our tone.* AC: adapter path configurable; Desk loads adapter at inference; falls back to base model + prompt persona if adapter fails to load; routing/audit logs record which persona backend was used.

**US-RP-01 (Competitor redirect):** *As an operator, I want competitor mentions handled by an approved redirect rather than factual competitor info.* AC: competitor intent detected → approved template/redirect served → general-knowledge competitor info never emitted → trigger logged. (This is your original example, now a first-class story.)

**US-RP-02 (Disclaimer / sensitive topic):** *As a regulated operator, I want legal/medical responses to carry required disclaimers or escalate to a human.* AC: matching intent appends configured disclaimer or routes to handoff; action logged.

### 1.5 Business model / monetization (update §6.7 and §3.1)

Place Persona basics in free tier (it's table-stakes for a front-desk bot), but put **advanced guardrails, fine-tuned-adapter support, disclaimer automation, and per-channel persona overrides in the paid tier.** This extends FR-BM-03. Suggested wording:

> Paid tier additionally includes: Response Policy & Guardrails (competitor/pricing/legal rules, post-generation checks), fine-tuned local persona adapters (LoRA/QLoRA), disclaimer automation, and per-channel persona overrides.

### 1.6 Open questions to add to §13

Add: (a) Do we ship a hosted fine-tuning pipeline, or only *support loading* externally-trained adapters? (Strongly recommend the latter for MVP — see SAD/TSD below.) (b) Is the intent classifier rule-based, a small local classifier model, or an LLM call? (c) Does post-generation checking run on every message (latency cost) or only on policy-flagged ones?

---

## 2. SAD (System Architecture Document) additions

### 2.1 New architectural components

Introduce three new logical components in the AI/inference path, sitting between the existing message pipeline and the model:

The **Persona Service** composes the final prompt: it merges the operator's Brand Persona config, few-shot examples, retrieved Vault context, and conversation history into the prompt sent to the model. When a fine-tuned adapter is configured, it instead (or additionally) selects the adapter-backed model endpoint. This is the single place where "how Desk sounds" is assembled.

The **Policy Engine (Guardrails)** runs as two hooks: a **pre-generation hook** (intent detection → decide allow / template / redirect / escalate / inject-context) and a **post-generation hook** (validate the generated response against active rules → allow / rewrite / block-and-template / escalate). It reads policy config and writes every decision to the audit log.

The **Intent/Policy Classifier** is the detection mechanism the Policy Engine calls. For MVP, recommend a tiered approach: cheap deterministic rules/keywords first (fast, free, transparent — perfect for competitor names and banned terms), with an optional small local classifier or LLM-based classifier for fuzzier intents. This keeps latency and cost predictable.

### 2.2 Request flow (update your sequence diagrams)

The updated inbound flow becomes: **inbound message → PII detection (existing) → Policy Engine pre-hook (new) → [if hard rule matches, serve template/redirect/escalate and skip generation] → model routing (existing FR-AI-05) → Persona Service prompt composition (new) → Vault RAG (existing) → model inference (existing, base model or LoRA adapter) → Policy Engine post-hook (new) → send.** Add this as a new sequence diagram and update Journey 4 (§5.4) to show the persona+policy hooks.

### 2.3 Fine-tuning architecture stance (important SAD decision)

Document this explicitly: **Desk does not perform fine-tuning inside the product for MVP/v1.1. Desk *consumes* fine-tuned artifacts (LoRA/QLoRA adapters) produced by an external pipeline.** Rationale: training is a heavyweight, GPU-bound, occasional batch workload that doesn't belong in the real-time serving path; it also keeps the core deployment lightweight and avoids forcing every operator to provision training hardware. Desk's serving layer (vLLM supports LoRA adapters; Ollama supports adapter merges) loads the adapter at inference time.

### 2.4 Sovereignty / compliance architecture note

Add a constraint: **fine-tuning data must be synthetic or rigorously anonymized.** Training on raw transcripts bakes PII into weights, which is incompatible with GDPR right-to-erasure (FR-DS-05) and your sovereignty promise. The SAD should state that the (external) fine-tuning pipeline must consume only de-identified data, and that the audit log records which adapter version served each response (for traceability). Add this to your §11.1 risk table as a new row: *"PII baked into fine-tuned weights → Critical → mitigate by anonymized/synthetic training data only + adapter versioning in audit log."*

---

## 3. TSD (Technical Specification Document) additions

### 3.1 Data model changes (extend §9)

Add a `BrandPersona` table and a `ResponsePolicy` table, and add fields to existing tables.

`BrandPersona`: `id`, `deployment_id`, `name`, `tone` (e.g., warm/formal/playful), `vocabulary_notes` (TEXT), `dos` (JSONB), `donts` (JSONB), `emoji_policy` (ENUM), `signature_phrases` (JSONB), `few_shot_examples` (JSONB array of {user, assistant}), `channel_overrides` (JSONB), `persona_backend` (ENUM: 'prompt' | 'lora_adapter'), `adapter_uri` (VARCHAR, nullable), `adapter_base_model` (VARCHAR, nullable), `version` (INT), `is_active` (BOOLEAN), `created_at`, `updated_at`.

`ResponsePolicy`: `id`, `deployment_id`, `name`, `trigger_type` (ENUM: 'keyword' | 'classifier' | 'llm_intent'), `trigger_config` (JSONB — e.g., competitor name list, intent label, threshold), `action` (ENUM: 'template' | 'redirect' | 'inject_context' | 'append_disclaimer' | 'block' | 'escalate'), `action_payload` (JSONB — template text, Vault doc id, disclaimer text), `applies_to` (ENUM: 'pre' | 'post' | 'both'), `priority` (INT — evaluation order), `is_active` (BOOLEAN), `created_at`, `updated_at`.

Extend the existing **`Message`** model (§9.1.2) with: `persona_id` (UUID, nullable), `persona_backend_used` (VARCHAR), `policy_triggers` (JSONB — array of {policy_id, action, matched_on}). Extend **`AI Configuration`** (§9.1.5) to reference `active_persona_id`. Extend the **Audit Log** `event_type` ENUM (§9.1.6) with `'policy_decision'` and `'persona_applied'`.

### 3.2 Adapter loading spec

Specify the LoRA/QLoRA contract: adapters are stored as a directory/artifact (`adapter_config.json` + adapter weights, PEFT-format) referenced by `adapter_uri` (local path or S3-compatible object store, consistent with your NFR-S-04). On inference, for vLLM use its `--enable-lora` / per-request LoRA serving; for Ollama, document the adapter-merge-into-Modelfile workflow. Define a startup validation step: Desk verifies `adapter_base_model` matches the configured local model; on mismatch or load failure, log an error and fall back to prompt-based persona (per FR-BP-07/US-BP-02 AC).

### 3.3 Prompt composition spec

Define the deterministic prompt assembly order so it's reproducible and testable: `[system: base instructions] + [system: brand persona block] + [system: active response policies that inject context] + [retrieved Vault chunks] + [few-shot examples] + [conversation history] + [current user message]`. Specify token-budget handling (truncate history before persona/policy; persona and hard policies are never truncated). This belongs in the TSD as the canonical contract the Persona Service implements.

### 3.4 Policy evaluation spec

Pre-hook: evaluate active `ResponsePolicy` rows where `applies_to in ('pre','both')` ordered by `priority`; first hard-match wins; record all matches. Post-hook: run response through `applies_to in ('post','both')` rules; on violation, apply action (rewrite via templated response, block+template, or escalate). Specify latency budget: pre-hook keyword rules must add <20ms; classifier-based detection budgeted within your existing NFR-P-01 (<500ms routing overhead) so the end-to-end <5s target holds.

### 3.5 New NFRs

Add: persona/policy config changes take effect within one message cycle without redeploy; LoRA adapter load adds <X s to model warm-up (define target, e.g., <30s); post-generation check adds <300ms P95 when enabled; guardrail false-positive/negative rates tracked as quality metrics.

---

## 4. TBK (Technical Backlog) additions

Suggested epics and their stories so your agent can populate the backlog. I'll keep these as a list since a backlog is inherently a list.

**Epic A — Brand Persona (Voice) [MVP]:** persona data model + migration; persona admin UI (tone/dos/donts/emoji/few-shot); Persona Service prompt composition; persona preview/test tool; persona injection into inference path; persona versioning + rollback (v1.1).

**Epic B — Response Policy & Guardrails [MVP, paid]:** policy data model + migration; policy admin UI (rule builder); deterministic keyword/rule pre-hook; intent classifier integration (tiered); templated/redirect response actions; post-generation check; policy audit logging; "restricted-topics, no general-knowledge fallback" mode (the US-AI-01(c) fix); escalate-to-human action.

**Epic C — Fine-tuned Local Persona (LoRA/QLoRA) [v1.1, paid]:** adapter storage + `adapter_uri` plumbing; vLLM LoRA serving integration; Ollama adapter workflow + docs; startup validation + graceful fallback; persona-backend switch (prompt ↔ adapter); audit logging of `persona_backend_used`; operator-facing docs/runbook for producing adapters externally (data prep, anonymization, QLoRA training script reference, evaluation checklist).

**Epic D — Compliance & Observability [cross-cutting]:** anonymized/synthetic-data requirement enforcement in fine-tuning runbook; adapter versioning traceability; persona/policy decision metrics (Prometheus); guardrail false-positive/negative dashboards.

I'd sequence it as A → B in MVP (both are mostly prompt/config and deliver the bulk of your value), then C in v1.1 once you have real transcripts to evaluate against and a clearer picture of which small model you're standardizing on.

---

