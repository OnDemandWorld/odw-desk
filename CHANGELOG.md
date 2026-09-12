# Changelog

All notable changes to ODW.ai Desk will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased] - 2026-09-12

### Changed — security (breaking for key-protected deployments relying on implicit admin)
- **RBAC default-deny**（评审批次 A）：`desk_default_role` 默认值从 `admin` 改为 **`agent`**。
  持有效 `DESK_API_KEY` 但未声明角色（或声明未知角色）的调用方此前会**默认获得 admin**——
  未知角色头静默升级为管理员（100 画像 UAT 发现）。现在未知/缺失角色回退到最小权限；
  admin 访问必须显式 `X-Desk-Role: admin` 或 JWT `role: admin`。
  单机开发如需旧行为：设 `DESK_DEFAULT_ROLE=admin`。

### Added
- **Operator Console**（评审批次 F）：`GET /console` 坐席收件台（会话列表/接管/回复/解决/
  审计信息，REST 轮询）与 `GET /console/webchat` 可嵌入 webchat 演示页（访客 WebSocket 客户端）。
  零构建静态页，ODW.ai 品牌令牌，key 存 localStorage。`GET /` 现返回 console 地址。

### Fixed
- **webchat 结构化 message 帧**（浏览器级 UAT 发现）：`{"type":"message","content":"…"}` 帧
  此前被整串存为消息内容并被 AI 回显（原始 JSON 进对话历史）。新增 `parse_message_frame`
  提取 `content`，纯文本/媒体/已读帧行为不变（+5 单测）。
- `alembic/env.py`：`DATABASE_URL` 环境变量优先于 alembic.ini（容器/CI 可用环境变量指向迁移库）。

## [Unreleased] - 2026-09-11

### Fixed — correctness (data loss / crash bugs)
- **Admin AI configuration**: `POST /setup/ai-model`, `GET|PUT /config/ai` read and wrote
  ORM attributes that do not exist on `AIConfiguration` (creation raised `TypeError`,
  updates were silently discarded). Requests now map to the real columns — frontier
  providers (`openai`/`anthropic`) persist provider/model/encrypted API key, local
  providers persist model/endpoint, and `max_tokens`/`temperature` are stored in
  `routing_policy`.
- **Brand persona**: persona service and `/admin/personas/active` read non-existent
  columns (`voice_description`, `dos_and_donts`, `vocabulary_guidelines`,
  `example_phrases`, `lora_adapter_*`) → 500 or missing prompt content. Now aligned
  with the real `BrandPersona` columns (`dos`/`donts`, `vocabulary_notes`,
  `few_shot_examples`, `adapter_uri`/`adapter_version`).
- **Conversation reopen**: a customer messaging after their conversation was resolved
  hit the `(channel, channel_conversation_id)` unique constraint → `IntegrityError`,
  the message was lost and the webhook returned 500. Threads are now looked up across
  all statuses and resolved/closed conversations are re-opened to `active`.
- **Message metadata**: `Message(metadata=…)` targeted the reserved Declarative
  attribute instead of the `metadata_` column, so AI/routing/media/agent metadata was
  silently never persisted (inbox confidence scores were always empty). Same fix in
  `CustomerResolver` (`metadata_=`).
- **Compliance (GDPR) export/delete**: the default actor id `"system"` was bound to
  the UUID `audit_logs.actor_id` column → asyncpg `ValueError`, the audit write failed
  and the whole erasure rolled back while the API returned 404. Non-UUID actors are
  now stored as `NULL` with the raw value preserved in `details.actor_id_raw`.
  `audit_logs.event_type` (NOT NULL) is now derived from the action, and the hash
  chain write/verify sides serialize identically (previously verification could never
  reproduce the stored hashes).
- **SLA scanner**: the background scan lazy-loaded `Conversation.messages` inside an
  async context (`MissingGreenlet`) — every scan failed and SLA breaches never
  escalated. Messages are now eager-loaded.
- **Agent list endpoint**: `GET /agents/agents` triggered lazy relationship loading
  in async context (guaranteed 500). Open-conversation counts now come from a grouped
  SQL query.
- **License manager**: rewrote to the actual `LicenseState` columns (`status`,
  `valid_until`, `grace_period_ends`, `features`, `last_validated_at`) — the previous
  version constructed the model with non-existent attributes and always crashed.
- **Message processor race**: the router publishes `conversation.routed` before its
  transaction commits; the processor (separate session) could miss the conversation
  and silently drop the reply. It now waits briefly for commit visibility first.
- **WebSocket connection manager**: multiple connections per agent are now tracked
  independently — a second tab no longer clobbers the first, and closing the older
  tab no longer deregisters the live connection.

### Fixed — security hardening
- **Agent WebSocket authentication**: `/ws/agents/{agent_id}` accepted any visitor and
  streamed full customer messages/escalations. The handshake now mirrors the REST
  API-key guard: when `DESK_API_KEY` is set, clients must present it via `?token=`,
  `X-API-Key`, or `Authorization: Bearer` (close code 4401); unset stays open for dev.
- **Production secret guard**: `Settings` now refuses to start in `production` with
  the hard-coded default `SECRET_KEY` (JWTs are signed with it).
- **API-key comparison**: `hmac.compare_digest` now receives UTF-8 bytes so non-ASCII
  key input returns 401 instead of an unhandled `TypeError` (500).
- **Outbound routing**: replaced blind `startswith` adapter matching with an explicit
  canonical alias map so similarly-prefixed adapters cannot steal channel traffic.
- **Redis resilience**: a single failed Redis command no longer tears down the shared
  connection pool used by the whole process.

### Changed
- `GET /api/v1/admin/config/ai` response shape now reflects the real configuration
  (`frontier_provider`, `frontier_model_name`, `local_model_name`,
  `local_model_endpoint`); `max_tokens`/`temperature` round-trip via `routing_policy`.

### Added
- `docs/USER_GUIDE_zh-CN.md` — non-technical user guide (Chinese).

## [1.0.0] - 2026-06-24

### Added

#### Core Infrastructure
- WhatsApp Business API adapter with webhook verification and message parsing
- Channel adapter plugin system for extensible channel support
- Message router with customer resolution
- Conversation manager with state machine (new → active → escalated → resolved → closed)
- Outbound dispatcher for multi-channel message delivery
- Redis Streams event bus for async message processing
- PostgreSQL database with async SQLAlchemy support
- Alembic migrations for database schema management

#### AI Intelligence Pipeline
- PII Shield with Presidio-based detection (18+ entity types)
- Model router with complexity scoring and local/frontier selection
- Vault client for knowledge base retrieval with Redis caching
- LLM provider abstraction with Ollama/vLLM and OpenAI implementations
- AI Engine orchestrator coordinating full RAG pipeline
- Prompt builder with context and knowledge integration
- Confidence scorer with multi-factor assessment and escalation logic

#### Agent & Admin Interfaces
- Agent Inbox REST API (7 endpoints for conversation management)
- Agent WebSocket for real-time conversation updates
- Admin setup wizard API for guided configuration
- Admin configuration APIs for AI models, PII settings, compliance
- Compliance Engine with GDPR export/deletion workflows
- Tamper-evident audit log with hash chaining
- License Manager with tier-based feature gating (Free/Paid/Enterprise)

#### Brand Persona & Response Policy
- Brand persona service with prompt composition
- Persona integration into AI inference pipeline
- Response policy engine with pre/post-generation hooks
- Keyword, regex, and topic-based policy rules
- Policy admin APIs for rule management

#### Deployment & Operations
- Multi-stage production Dockerfile
- GitHub Actions CI/CD pipeline (lint, test, build)
- Kubernetes Helm charts with configurable values
- Prometheus metrics (25+ metrics across all components)
- End-to-end test suite
- Structured logging with structlog
- Graceful degradation for external service failures

### Technical Details

**Code Statistics:**
- 11,515 total lines of code
- 67+ Python source files
- 8,486 lines in src/ and tests/
- 30+ new files created in final implementation phase

**Dependencies:**
- FastAPI 0.115.6
- SQLAlchemy 2.0.36 (async)
- Redis 5.2.1
- Presidio Analyzer 2.2.357
- LangChain 0.3.14
- Prometheus Client 0.21.1
- And 20+ additional packages

**Testing:**
- Integration tests: 2/2 passing
- E2E test suite: 8 comprehensive test cases
- Code coverage reporting configured
- MyPy type checking: Clean
- Ruff linting: Clean

### Architecture

**Modular Monolith:**
- All components in single FastAPI application
- Event-driven internal messaging via Redis Streams
- Async/await throughout for I/O operations
- Dependency injection for testability

**Data Flow:**
```
WhatsApp Webhook → Channel Gateway → Event Bus → Message Router → 
Conversation Manager → AI Engine (PII → Router → Vault → LLM → Confidence) → 
Outbound Dispatcher → WhatsApp API
```

**Key Design Decisions:**
- Async/await for all I/O operations
- Per-call engine creation for loop safety
- Graceful degradation when external services unavailable
- Hash-chained audit log for tamper evidence
- Feature gates for license tier enforcement
- Channel adapter plugin pattern for extensibility

### Documentation

- Comprehensive README.md with quick start guide
- DEVELOPMENT.md with detailed progress tracking
- Architecture Decision Records (ADRs)
- API documentation (Swagger/ReDoc)
- Contributing guidelines
- Code of conduct

### Security

- PII detection prevents sensitive data from reaching external APIs
- Encrypted API keys at rest (AES-256-GCM)
- Webhook signature verification (HMAC-SHA256)
- Configurable data retention policies
- GDPR-compliant data export and deletion
- Non-root Docker container execution

### Performance

- Connection pooling for database and Redis
- Async I/O for high concurrency
- Redis caching for Vault retrievals (10-min TTL)
- Configurable worker processes
- Health checks for all dependencies

## [0.1.0] - 2026-06-23

### Added
- Initial project structure
- Planning documents (PRD, SAD, TSD, TBK)
- Basic FastAPI application scaffold
- Database models and migrations
- Development environment setup

---

## Version History

### Versioning Scheme

- **Major version**: Breaking changes to APIs or data models
- **Minor version**: New features (backward compatible)
- **Patch version**: Bug fixes and minor improvements

### Upgrade Guide

#### From 0.1.0 to 1.0.0

1. **Database Migration**
   ```bash
   alembic upgrade head
   ```

2. **Environment Variables**
   - Review `.env.example` for new required variables
   - Configure WhatsApp Business API credentials
   - Set up LLM provider (Ollama or frontier model)
   - Configure Vault connection (if using knowledge base)

3. **Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configuration**
   - Review and update AI model settings
   - Configure PII detection rules
   - Set up license tier
   - Configure compliance settings

5. **Testing**
   - Run integration tests
   - Verify webhook connectivity
   - Test AI pipeline with sample messages

---

## Future Roadmap

### v1.1 (Planned)
- Telegram Bot Adapter
- Discord Bot Adapter
- Slack App Adapter
- Signal Messenger Adapter
- iMessage Bridge Adapter
- Advanced persona versioning and rollback
- Intent classifier integration
- Enhanced policy templating

### v1.2 (Planned)
- Multi-tenant support
- Advanced analytics dashboard
- Custom model fine-tuning support
- Voice message transcription
- Media message handling
- Conversation analytics and reporting

### v2.0 (Future)
- Microservices architecture option
- Event sourcing implementation
- CQRS pattern for read/write optimization
- GraphQL API option
- Plugin marketplace
- White-label support

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for details on how to contribute to this project.

## Support

- **Documentation**: [README.md](README.md)
- **Issues**: [GitHub Issues](https://github.com/OnDemandWorld/odw-desk/issues)
- **Discussions**: [GitHub Discussions](https://github.com/OnDemandWorld/odw-desk/discussions)

---

**Last Updated**: 2026-06-24
