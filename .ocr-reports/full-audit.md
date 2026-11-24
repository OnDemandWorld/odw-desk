# ODW.ai Desk — Full-Repository Code Audit

- **Date:** 2026-11-24
- **Mode:** Open Code Review — delegation (host-driven analysis; no external OCR binary or API config used)
- **Scope:** Entire repository at `main` @ `e5421d3` — all source, tests, migrations, and infrastructure config (not a diff review)
- **Companion data:** [`full-audit.json`](./full-audit.json) — finding IDs below (`#N`) map 1:1 to the `id` field there.

## Coverage

| Metric | Value |
|---|---|
| Total files in scope | 133 |
| Reviewed | 133 |
| Skipped | 0 |
| Coverage rate | **100%** |

Reviewed: all 90 `src/desk/**/*.py` modules, both `src/desk/static/*.html` consoles, 26 test files, `scripts/smoke_round2.py`, 3 Alembic migrations + `env.py`/`script.py.mako`/`alembic.ini`, `Dockerfile`, `Dockerfile.api`, `docker-compose.dev.yml`, `.github/workflows/ci.yml`, `pyproject.toml`, `requirements.txt`, `.env.example`, `.gitignore`, `k8s/helm/Chart.yaml`, `k8s/helm/values.yaml`.

Excluded per audit guardrails: documentation (`*.md`), `uv.lock`, `LICENSE`, `.git`, and binary/media assets (none tracked). No source files were modified during this pass.

**Method:** six parallel subsystem reviewers read every assigned file in full; the host then independently verified **every High-severity finding** against the code (plus spot-checks of Mediums), merged cross-batch duplicates (121 raw findings → 100 consolidated), and discarded unsubstantiated claims. Findings confirmed by multiple independent reviewers are noted in the JSON.


## Fix progress (branch `fix/ocr-full-audit-round1`)

**40 of 100 findings fixed** (14/14 High, 24/56 Medium, 2/30 Low) across 8 verified batches; 60 remain open (32 Medium, 28 Low). Every batch passed `ruff check src/desk/`, `mypy src/desk/ --ignore-missing-imports --python-version 3.14`, and `PYTHONPATH=src pytest tests/ -m "not e2e"` (285 baseline → 380 passed, 0 failures). Per-finding commands/results and caveats are recorded in `full-audit.json` (`status`, `verification_notes`). Checked items below are fixed; unchecked remain open. Scoped-mitigation caveats: #9 (scale-out relay still open), #11 (opt-in enforcement, partial surfaces), #3 (per-IP connect limiting open), #6 (delivery-status column open), #16 (shared-key mode), #44/#46 (GC disposal / pagination).

## Summary

| Severity | Count | Themes |
|---|---|---|
| **High** | 14 | Default-open admin API, PII sovereignty bypasses, silent message loss (4 independent paths), multi-worker split-brain, unenforced license/retention, broken dev image |
| **Medium** | 56 | Authz/ownership gaps, webhook & SMTP verification flaws, JSONB write-loss pattern, policy-engine outages, confidence-scoring defects, race conditions, infra hardening, hollow tests |
| **Low** | 30 | PII in logs, credential hygiene, pagination/scoping bugs, counters, pinning, minor test gaps |

**Headline risk:** the product's two core promises — *sovereignty* (PII gates frontier models) and *reliability* (every customer message gets an answer) — are each defeated by multiple independent defects in the default configuration. Remediate the High cluster before any production deployment.

---

## HIGH — fix before production (14)

- [x] **#1 — Admin/agent APIs unauthenticated by default** (`src/desk/security/rbac.py:124-129`)
  `require_role` is a no-op when `DESK_API_KEY` is empty (the default); nothing enforces a key even in production, and the variable is absent from `.env.example`/compose/Helm. Unauthenticated callers can disable the PII shield, redirect model/Vault endpoints to attacker servers, hard-delete customer data, and export all PII. *Confirmed by 3 reviewers.* **Fix:** fail closed in production; document the key; validate admin-supplied endpoints.
- [x] **#2 — Long-lived secrets as URL query parameters** (`src/desk/admin/api.py:98-161`)
  Vault key, WhatsApp access/verify tokens, and frontier API key travel in query strings → access logs, proxies, browser history. **Fix:** move to JSON bodies; rotate exposed keys.
- [x] **#3 — Webchat WebSocket hijack via guessable visitor_id** (`src/desk/channels/webchat.py:422-435`)
  No auth; `Math.random`-based id (~41 bits); connecting displaces the victim's live socket and receives their replies (regulated-market PII). **Fix:** signed session tokens, crypto-random ids, connection rate limits.
- [x] **#4 — Raw conversation history bypasses PII Shield** (`src/desk/ai/engine.py:336-343`)
  Only the current message is redacted; history is loaded from raw `msg.content` and sent verbatim to frontier models. The sovereignty guarantee fails even when the shield works. **Fix:** redact history for frontier-bound turns.
- [x] **#5 — Email thread collision → permanent 500s & message loss** (`src/desk/channels/email.py:116-132`)
  Customer-scoped conversation lookup vs global `(channel, channel_conversation_id)` unique constraint; a second thread participant's reply violates it on every relay retry, forever. *Confirmed by 2 reviewers.* **Fix:** align lookup/constraint/thread-key; catch `IntegrityError` and re-read.
- [x] **#6 — Silent outbound delivery loss** (`src/desk/channels/outbound.py:26-66`)
  One send attempt, no retry/tracking despite the docstring; processor discards the failure and acks; inbox reports success to the agent. *Merges 3 findings.* **Fix:** retry/outbox, per-message delivery status, callers must check `success`.
- [x] **#7 — Publish-before-commit message loss** (`src/desk/router/message_router.py:115-127`)
  Event published inside the request transaction; `get_db` commits after the 200 is sent (FastAPI ≥0.111). Commit failure → Meta never redelivers → message lost. **Fix:** transactional outbox or commit-before-publish.
- [x] **#8 — No Redis Streams pending-entry recovery** (`src/desk/events/redis_streams.py:82-89`)
  Only `>` reads; no `XAUTOCLAIM`/`XPENDING`; fixed consumer name `processor-1`. Crash mid-batch strands events forever despite the "at-least-once" claim. **Fix:** claim idle PEL entries with a delivery cap → DLQ.
- [x] **#9 — 4-worker deployment split-brain** (`Dockerfile:59`)
  Per-worker processors share one consumer name; webchat sockets and runtime settings are process-local → ~75% of live webchat replies never delivered; config changes apply to 1 of 4 workers. *Merges 2 findings.* **Fix:** single worker/dedicated processor + Redis pub/sub delivery + shared override cache.
- [x] **#10 — Rate limiter unbounded memory growth (DoS)** (`src/desk/channels/rate_limit.py:42-59`)
  Attacker-controlled visitor keys never evicted; `reset()` has no production callers. Cheap sequential connections OOM the process serving all channels. **Fix:** evict empty keys, sweep/cap, throttle connects.
- [x] **#11 — License feature gates never enforced** (`src/desk/license/manager.py:182-207`)
  `LicenseManager` has zero callers; every paid feature is available on the default free license. **Fix:** wire startup validation + feature-gate dependencies on paid routes.
- [x] **#12 — Data retention never enforced** (`src/desk/compliance/engine.py:204-247`)
  `enforce_retention_policy` has zero callers; `DATA_RETENTION_DAYS` is decorative — GDPR storage-limitation silently violated. **Fix:** schedule it; surface last-run status.
- [x] **#13 — Key-decryption failure halts ALL AI replies permanently** (`src/desk/ai/engine.py:136-161`)
  Runtime-config apply is unguarded and called outside the pipeline try; after `SECRET_KEY` rotation every message dead-letters, forever (stamp never advances). **Fix:** guard the apply block; fall back to local on decrypt failure.
- [x] **#14 — `Dockerfile.api` crash-loops (package not importable)** (`Dockerfile.api:13-23`)
  No `PYTHONPATH`, no `pip install .`; `desk.main` unimportable. The dev stack never comes up. **Fix:** add `ENV PYTHONPATH=/app/src` or install the project.

## MEDIUM — schedule next (56)

### Authorization & identity
- [x] **#15** `rbac.py:91-97` — `X-Desk-Role: admin` trusted in all non-production envs → staging privilege escalation with the shared key.
- [x] **#16** `inbox_api.py:228-233` — acting agent is a client-supplied `agent_id`; any key holder can impersonate any agent (attribution spoofing).
- [x] **#17** `inbox_api.py:499-545` — `/status` has no ownership check or row lock; bypasses `/resolve` authorization; races takeover.
- [x] **#18** `admin/api.py:507-557` — compliance export/delete `actor_id` is caller-controlled; audit non-repudiation spoofable. *(2 reviewers)*
- [x] **#19** `webchat.py:265-292` — read receipts mutate any customer's message cross-channel; existence oracle; `MultipleResultsFound` risk.

### Channel verification & delivery
- [x] **#20** `whatsapp_business.py:304-320` — webhook signature fails open outside production even with live send credentials → forged messages drive real sends.
- [x] **#21** `email.py:242-245` — STARTTLS without certificate verification → SMTP credentials MITM-able.
- [x] **#22** `email.py:347-381` — HMAC computed over extracted `raw` field, not received body → all signed JSON-envelope deliveries rejected 401.
- [x] **#23** `email.py:210-222` — outbound stubs `success=True` in production while inbound flows → silent reply loss.
- [x] **#24** `email.py:186-190` — SMTP without socket timeout → hung sends exhaust the shared `to_thread` executor.
- [ ] **#25** `webchat.py:99-108` — failed send evicts a *replacement* socket (disconnect without identity) → online visitor silently drops replies.
- [x] **#26** `webchat.py:507-509` — raw exception text sent to anonymous visitors (schema/internal leak). *(2 reviewers)*
- [ ] **#27** `channels/manager.py:78-98` — inbound polling `except Exception: pass`; one error kills the adapter silently forever.

### Data integrity (JSONB & state)
- [x] **#28** `inbox_api.py:612-617` — AI feedback never persisted (in-place JSONB mutation, same-object reassignment).
- [x] **#29** `conversations/manager.py:175-179` — status-change reason lost on non-empty metadata (same pattern; fix with #28). *(2 reviewers)*
- [x] **#30** `persona/service.py:173-188` — activating an unknown persona deactivates ALL personas, returns success. *(2 reviewers)*
- [ ] **#31** `persona/service.py:29-33` — `get_active_persona` unscoped/unordered; concurrent activations leave multiple active rows.
- [ ] **#38** `csat_api.py:90-109` — CSAT one-rating rule race; full-dict metadata writes clobber concurrent writers.
- [ ] **#39** `compliance/engine.py:68-73` — audit hash chain forks under concurrent writers → tamper-evidence breaks at high volume. *(2 reviewers)*
- [ ] **#41** `customer_resolver.py:49-76` — no unique constraint on channel identifiers → duplicate customers; dead retry path; incomplete GDPR erasure. *(2 reviewers)*

### Policy engine
- [x] **#32** `policy/engine.py:243-247` — unvalidated `trigger_config`: one bad regex/shape outages the whole AI pipeline; ReDoS on the single worker. *(2 reviewers)*
- [x] **#33** `policy/engine.py:257-262` — metadata conditions OR-bypassed by keywords and never receive metadata in production (inert guardrails).
- [x] **#34** `policy/engine.py:249-254` — substring topic matching ('vs' in 'TVs', 'law' in 'flaw') → false-positive blocks/escalations.

### Configuration plumbing
- [x] **#35** `runtime_settings.py:77-87` — `load_all()` has zero callers; persisted overrides lost on every restart; the persistence test only checks the in-process cache. *(merges infra High test finding)*
- [x] **#36** `admin/api.py:128-152` — `/setup/whatsapp` persists config no component reads; wizard is a silent no-op.
- [ ] **#37** `websocket.py:111-140` — agent WS rejects JWTs the REST API accepts → no realtime updates in production JWT mode.
- [ ] **#61** `model_router.py:237-252` — router frozen from env; admin-configured frontier never routed to.
- [ ] **#62** `pii_shield.py:271-281` — `frontier_allowed_with_redaction` toggle persisted but never consumed.

### Worker & event pipeline
- [x] **#42** `message_processor.py:164-177` — event acked even when DLQ write fails → failed events vanish.
- [x] **#43** `message_processor.py:179-208` — 2s commit-visibility wait gives up, pays inference, drops reply, acks.
- [x] **#44** `db.py:41-56` — engine cache keyed by `id(loop)`; loop-id reuse returns dead-loop engines; pools leak.
- [x] **#45** `redis_streams.py:45-48` — no `MAXLEN`/trim on streams or DLQs → Redis grows to OOM → full pipeline outage.
- [x] **#46** `main.py:129-143` — SLA scanner in every worker: racing duplicate escalations + unbounded eager load of all message history. *(2 reviewers)*

### AI quality & sovereignty
- [ ] **#53** `engine.py:322-334` — Vault skipped for `LOCAL_MODEL_ONLY` → PII-bearing messages capped at 0.56 confidence, always escalated (deflection defeated for the core market).
- [ ] **#54** `confidence_scorer.py:140-159` — purely relative knowledge scoring: one irrelevant chunk = 1.0 > Vault outage 0.3 → confident hallucinations auto-sent.
- [ ] **#55** `confidence_scorer.py:214-229` — whitespace word count mis-scores every Chinese reply as too short.
- [ ] **#56** `pii_shield.py:23-30` — CN phone regex misses `+86` and separated formats → raw numbers to frontier.
- [ ] **#57** `pii_shield.py:179-187` — English-only NER + 3 CN regexes; Chinese names/addresses undetected in mixed text.
- [ ] **#58** `prompt_builder.py:69-91` — raw forgeable `Customer:`/`Agent:` transcript → prompt injection via message or history.
- [ ] **#59** `engine.py:363-370` — `fallback_chain` never executed; provider failure → canned reply acked as success, no escalation.
- [ ] **#60** `vault_client.py:143-148` — Redis cache failure aborts retrieval or discards fetched documents.
- [ ] **#63** `pii_shield.py:129` — spaCy model downloaded at runtime; air-gapped deployments crash-loop the worker. *(2 reviewers)*

### Crypto, license, compliance
- [ ] **#47** `utils/encryption.py:53-59` — unsalted SHA-256 KDF; encryption key = JWT signing secret; two incompatible derivation paths.
- [ ] **#48** `license/manager.py:215-254` — `activate_license('enterprise')` grants enterprise for the literal string.
- [ ] **#49** `license/manager.py:150-180` — NULL `valid_until` fails open; gates never re-check expiry.
- [ ] **#50** `compliance/engine.py:214-227` — retention keeps customer PII (phone/name) forever even after conversations delete.

### Observability
- [ ] **#51** `tracing.py:297-305` — synchronous `httpx.post` on the event loop per span end (up to 2s stalls).
- [ ] **#52** `tracing.py:44-46` — 32-hex span IDs (spec: 16) → collectors reject every OTLP span silently.
- [ ] **#40** `reports_api.py:153-169` — overview CSAT aggregate scans the entire conversations table regardless of window.

### Infrastructure & tests
- [ ] **#64** `Dockerfile.api:1-23` — runs as root; `--reload` baked into CMD.
- [ ] **#65** `docker-compose.dev.yml:14-46` — Postgres/Redis/MinIO published on 0.0.0.0 with weak/no credentials.
- [ ] **#66** `k8s/helm/values.yaml:56-97` — placeholder secret key (forgeable JWTs if padded), desk/desk DB, no Redis auth, no API key.
- [ ] **#67** `k8s/helm/Chart.yaml:1-18` — chart has no templates/dependencies: `helm install` deploys nothing.
- [ ] **#68** `requirements.txt:1-58` — floor-only pins duplicated in two files; builds resolve fresh every time.
- [ ] **#69** `tests/e2e/test_message_flow.py:97-118` — flagship E2E signs the wrong bytes and asserts no pipeline outcome.
- [ ] **#70** `tests/unit/test_review_round4_fixes.py:423-436` — takeover guards "tested" by grepping source strings; zero behavioral coverage.

## LOW — backlog (30)

- [ ] **#71** `websocket.py:124-127` — shared API key in `?token=` query (logged).
- [ ] **#72** `static/inbox.html:137-143` — shared admin-capable key persisted in localStorage.
- [ ] **#73** `persona/service.py:102-105` — `few_shot_examples` dicts rendered as Python repr into prompts. *(2 reviewers)*
- [ ] **#74** `admin/api.py:419-420` — compliance report `actor=system` filter always empty (non-UUID actors stored in details only).
- [ ] **#75** `admin/api.py:369-372` — audit-logs `total` is page size, not row count.
- [ ] **#76** `whatsapp_business.py:359-364` — `contacts[0]` name applied to all batched senders → cross-customer name misattribution.
- [ ] **#77** `whatsapp_business.py:494-495` — malformed signed webhook body → 500 redelivery loop instead of 400.
- [ ] **#78** `email.py:156` — random-UUID Message-ID fallback defeats redelivery dedup.
- [ ] **#79** `email.py:250` (+`whatsapp_business.py:106-110`, `vault_client.py:208-214`) — customer PII (recipients, subjects, query text) at INFO. *(2 reviewers)*
- [ ] **#80** `whatsapp_business.py:75` — `messages_sent` counted before/regardless of outcome.
- [ ] **#81** `main.py:83` — `EVENT_BUS_BACKEND=nats` silently ignored (stub backend).
- [ ] **#82** `models/license_state.py:25-29` — license key plaintext despite "encrypted at rest" comment.
- [ ] **#83** `license/manager.py:109-131` — concurrent `initialize()` creates duplicate license rows.
- [ ] **#84** `compliance/engine.py:144-153` — `verify_audit_chain` unreachable + full-table load.
- [ ] **#85** `compliance/engine.py:219-239` — retention sweep: per-row deletes + audit SELECT each, one long transaction.
- [x] **#86** `policy/engine.py:194-216` — `append_disclaimer` marks responses invalid; double evaluation.
- [x] **#87** `policy/engine.py:78-83` — deployment scoping inconsistent; two uuid5 namespaces for the same deployment.
- [ ] **#88** `tracing.py:228-233` — shared mutable span stack across copied contexts → mis-parented traces.
- [ ] **#89** `tracing.py:68-76` — unvalidated client `X-Trace-Id` bound into every log line (log forgery/amplification).
- [ ] **#90** `engine.py:157-160` — `confidence_threshold=0.0` ignored (truthiness).
- [ ] **#91** `engine.py:238-255` — PII write-back targets newest message, not the processed one.
- [ ] **#92** `engine.py:518-526` — `typing.cast` hides `channel='mock'` pydantic rejection → mock events dead-letter.
- [ ] **#93** `prompt_builder.py:129-149` — no history character budget → long conversations overflow local context.
- [ ] **#94** `requirements.txt:50-58` — dev tooling shipped in production images.
- [ ] **#95** `alembic.ini:6` — default migration URL port 5433 matches nothing.
- [ ] **#96** `docker-compose.dev.yml:35` — MinIO `latest` unpinned.
- [ ] **#97** `k8s/helm/values.yaml:4-7` — app image `latest` + IfNotPresent → stale replicas.
- [ ] **#98** `alembic/env.py:17-34` — `SystemSetting` missing from target metadata → autogenerate would DROP `system_settings` (data-loss potential; review autogenerated migrations).
- [ ] **#99** `tests/unit/test_review_round6_fixes.py:287-301` — no-op self-patch + duplicated disjunct in SLA test.
- [ ] **#100** `scripts/smoke_round2.py:80-89` — smoke webhook signature uses a key the app never verifies with.

---

## Suggested remediation order

1. **Auth cluster first:** #1 → #15 → #2 → #16/#17/#18 (they compound: default-open API + spoofable identity/attribution).
2. **Message-loss cluster:** #6 → #7 → #8 → #42/#43 → #5 (each is an independent loss path; #9 multiplies them).
3. **Sovereignty cluster:** #4 → #56/#57 → #3 → #20 (PII must not reach frontier models or attackers).
4. **Deployment blockers:** #14, #9, #63, #13 (nothing runs reliably until these are fixed).
5. **Compliance promises:** #12 → #50 → #11 → #48/#49 → #39.
6. Then Mediums by subsystem, Lows as backlog. The JSONB pattern (#28/#29), `load_all` wiring (#35/#36/#62), and confidence scoring (#53/#54/#55) are each single-pass fixes covering multiple findings.

## Verification notes

- Every High finding was re-verified by the host against the cited code (file reads/greps), not accepted from reviewer output alone.
- Dead-code claims (#11, #12, #35, #84) were verified by repository-wide grep for callers.
- Cross-batch duplicates were merged into single findings; the JSON `root_cause`/`suggested_fix` fields list all affected locations.
- No finding in this report is speculative-by-design; items whose blast radius depends on configuration (e.g. #20, #23, #66) state the triggering configuration explicitly.
