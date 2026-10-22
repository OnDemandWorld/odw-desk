# Changelog

All notable changes to ODW.ai Desk will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased] - 2026-10-22（第六轮深度审查）

### Added
- **`POST /api/v1/admin/agents` + `GET /api/v1/admin/agents`（D-2）**：此前没有任何
  API 能创建 Agent 行——控制台接管开箱报 "no agent seeded"，人工接管流程不可用。
  邮箱唯一冲突返回 409。
- **`POST /api/v1/admin/personas`（D-2）**：FR-BP-01 落地——运营可通过 API 定义品牌
  人格（tone/dos/donts/emoji_policy/signature_phrases/few_shot），创建后经既有
  activate 端点启用。
- **`system_settings` 表（D-3，迁移 a7f3c2d91e05）**：admin 运行时配置的持久化载体
  （key → JSONB）+ 进程内覆盖缓存 + TTL 缓存工具。

### Fixed
- **[P0] 策略引擎动作接线（D-1）**：6 种动作只执行 block——`redirect`（竞品重定向，
  US-RP-01 旗舰故事）与 `escalate`（FR-RP-08 转人工）决策被静默丢弃、LLM 照常自由
  生成。现前置钩子返回 redirect 定制回复 / escalate 复用升级机制（会话转
  ESCALATED + 广播坐席）；后置钩子支持 append_disclaimer 拼接免责文本。
- **[P0] admin 配置假成功（D-3）**：`POST /setup/vault`、`/setup/whatsapp`、
  `PUT /config/pii` 此前只打日志返回 success 零持久化。现 vault/whatsapp/pii 全部
  落 system_settings；VaultClient 按覆盖热重建（立即生效）；PII kill-switch 在
  analyze() 入口生效；WhatsApp 明确标注重启生效。
- **[P1] AI 配置被引擎消费（D-4）**：`ai_configurations` 表只写不读——admin 配置的
  模型/阈值对推理零生效。引擎每消息 TTL(60s) 快照 + updated_at 变更时重建
  local/frontier provider 与置信度阈值（frontier key 解密复用 admin 写入的派生密钥）。
- **[P1] SLA 首响配置化（D-5）**：硬编码 10 分钟 → settings.sla_first_response_minutes。
- **[P1] `sla.breach` 事件发布（D-9）**：生产扫描器构造 SLAService 不带 event_bus，
  README 承诺的事件从未发出；main.py 传入 app.state.event_bus。
- **[P1] WhatsApp 媒体契约（D-6/D-21）**：入站媒体元数据嵌套进 metadata["media"]
  （router 持久化路径，media_id/mime/caption 不再丢失）；出站 caption 进媒体对象
  （顶层 caption 被 Meta 静默丢弃）。
- **[P1] anthropic 显式拒绝（D-7）**：配置 anthropic 此前静默降级本地模型；现
  `/setup/ai-model` 返回 400 明确 "not implemented yet — use openai or a local
  provider"。
- **[P2] JWT-only 认证路径（D-12）**：admin/agent 守卫链先经 require_api_key，纯 JWT
  bearer（永不等于 API key）被 401——文档宣称的 JWT 签名认证路径不可达。守卫链
  收敛为 require_role 单依赖（其内部完整认证 JWT 或 API key）。
- **[P2] takeover TOCTOU（D-15）**：并发接管双 200 且后者静默驱逐前者；SELECT 加
  with_for_update 行锁。
- **[P2] 并发竞态（D-14）**：同一新客户两条并发 webhook 各建 Customer（此后
  MultipleResultsFound 永久 500）——resolver 改 limit(2).first() + IntegrityError
  回读；消息重复投递撞唯一索引返回 500 —— add_message 捕获后返回 duplicate。
- **[P2] 中文置信度（D-19）**：完整性指标全英文短语，中文回复恒 0.5 基分易误升级；
  补中英双语正/负向指标。
- **[P2] 阈值一致性（D-20）**：会话创建硬编码 0.7 → settings.confidence_threshold。

### Deferred（V1.7）
- D-8 license 门控、D-10 policy_triggers 审计回填、D-11 死指标埋点、D-13 PII 按
  message_id 回写、D-16 消费者 XAUTOCLAIM、D-17 审计链 advisory lock、D-18 死配置
  清理——登记于根仓库 REVIEW_ROUND6_DISCUSSION.md §三。

## [Unreleased] - 2026-10-08（上线前深度审查轮）

### Fixed
- **[P0] 入站 webhook 生产环境 fail-closed**：`WHATSAPP_APP_SECRET` 为空时验签静默放行（伪造
  客户消息 + 借真实凭证向任意号码发信）。生产环境未配置即拒绝（401），开发环境保持
  warn-and-accept；非 ASCII 签名头不再 TypeError→500。Email relay webhook 新增
  `EMAIL_WEBHOOK_SECRET`（HMAC-SHA256 `X-Desk-Signature`），生产环境未配置即拒绝。
- **[P1] `ai_enabled` 死标志**：接管后 AI 仍自动抢答（与坐席回复打架）。takeover 置
  `ai_enabled=False`；MessageProcessor 生成前重读会话状态，人工接管中的线程跳过 AI；
  RESOLVED/CLOSED 会话因客户新消息重开时复位 AI（新一轮由 AI 先应答）。
- **[P1] webhook 重投递幂等**：Meta/邮件 relay 对非 2xx 重投，重试撞
  `UNIQUE(conversation_id, channel_message_id)` → 500 → 无限重试循环。route() 先按
  `channel_message_id` 查重，重复即幂等返回 `status=duplicate`。
- **[P1] Presidio 同步推理阻塞事件循环**（spaCy NER 单条几十至几百 ms）：analyze/anonymize
  移入 `asyncio.to_thread`。
- **[P1] GDPR anonymize 残留可识别信息**：`channel_conversation_id`（WhatsApp 即手机号原文）、
  `channel_message_id`（email Message-ID 含地址域名）、`media_urls` 一并覆写/清空。
- **[P1] 置信度与 Vault `fused_score` 量纲错配**：RRF 排名分（好命中 ~0.03）被当 0-1 相关度
  平均，最好情况总分 ≈0.56 < 0.6 阈值——grounding 良好的回答也被丢弃转人工（AI deflection
  失效）。改为对本次检索集按最佳命中相对归一化。
- **[P2] 会话生命周期**：takeover 拒绝 RESOLVED/CLOSED（此前任意状态强行拉回 ACTIVE）与
  并发抢占（此前双坐席都 200、后写覆盖前写，现 409）；resolve 校验坐席存在与归属
  （此前任意/不存在 agent_id 可 resolve 他人会话）。
- **[P2] WebChat WS 连接卫生**：重连顶替时先关闭旧 socket（此前残留半开）；`disconnect`
  校验 socket 身份（此前旧连接的断开回调会误删新连接，在线访客的回复被丢弃）。
- **[P2] RBAC 生产加固**：`X-Desk-Role` 自证头在生产环境不再授级（共享 key 持有者不能一行
  头提权 admin），可用 `DESK_ROLE_HEADER_TRUSTED` 显式覆盖；开发/预发行为不变。

### Changed — tests
- 250 → 271（新增 `test_review_round4_fixes.py` 21 条回归：ai_enabled ×3、路由幂等 ×2、
  置信度标定 ×2、GDPR 匿名化 ×1、WhatsApp fail-closed ×4、Email HMAC ×3、RBAC 头信任 ×3、
  WS 卫生 ×2、takeover 守卫 ×1）。

## [Unreleased] - 2026-09-13（复查与优化轮）

### Fixed
- **Event bus / Redis**: redis-py ≥ 8 defaults `socket_timeout` to 5s, which races the
  processor's `XREADGROUP block=5000` — every idle poll raised `TimeoutError`
  (processor loop flooded with errors, replies delayed). The shared pool now sets a
  15s socket timeout + keepalive, and a blocking-read expiry is treated as an empty
  poll instead of an outage.
- **Agent inbox `respond`**: the reply text was carried in a URL query parameter —
  long replies exceed URL limits and leak into access logs. The endpoint now accepts
  a JSON body `{"content": "…"}` (query parameter kept for backward compatibility;
  the bundled console switched to the body). Verified live with a ~6,000-char reply.

### Changed — tests
- **Pipeline integration test determinism**: `test_whatsapp_pipeline_dispatches_ai_response`
  asserted the graceful-degradation reply but ran against the developer machine's real
  Ollama (model `gemma4:latest` exists locally → reply becomes free-form and takes far
  longer than the fixed 1.5s wait → flaky failure). The client fixture now pins the
  local-model and Vault endpoints to a closed port, and the fixed sleep became a
  bounded poll.

## [Unreleased] - 2026-09-12（全流程测试与验收轮）

### Fixed — PII / grounding（单项目+组合+三轮验收发现）
- **中文 PII 漏检**（验收 P0）：PII Shield 仅启用 Presidio en 识别器，中文手机号/座机/身份证完全漏检。
  新增中文正则识别层（`1[3-9]\d{9}`、固话、居民身份证）并入 Presidio 结果集；+4 单测。
- **PII 结果不回写消息行**：分析结果此前只用于路由，收件台永远看不到 PII 标记/脱敏文本。
  AI 引擎分析后回写 `pii_detected/pii_types/content_redacted`（best-effort，不阻断 AI 路径）。
- **Desk→Vault grounding 三重失效**（组合测试发现）：`fused_score` 阈值 0.3 与 Vault 实际量表（~0.03）
  不匹配 → 真实结果全被丢弃；httpx 超时 10s vs 真实 RAG 延迟 40s+ → 永远超时；空消息异常不可诊断。
  现信任 Vault 排序（去绝对阈值）、超时可配置（默认 120s）、错误日志带异常类型。
- `vault_client` 删除消息缓存键污染防护：检索失败不再写缓存。

### Added
- `qa/` 套件级测试资产（用例文档 67+19 条、可执行 runner、四阶段报告）。
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
