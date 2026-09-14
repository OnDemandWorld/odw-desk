# ODW Desk — 下一步开发计划

> 整理日期：2026-09-13。基于两轮全量代码审查、262 项自动化测试 + 实机冒烟验证的结果。
> 当前质量基线：**pytest 262/262 通过、ruff 零告警、mypy 零错误、覆盖率 72%**。
>
> 优先级定义：**P0** = 上线前必须（正确性/安全）；**P1** = 短期内核心功能补全；
> **P2** = 规模化与体验；**P3** = 产品化/生态。每项附验收标准与涉及文件。

---

## P0 — 上线前必须完成

### P0-1 真实身份认证与授权体系（当前是最大的安全短板）

**现状**
- 全系统只有一个共享的 `DESK_API_KEY`，管理员和客服用同一把钥匙；
- 角色完全由客户端控制：`X-Desk-Role: admin` 头即可进入 admin 路由（JWT 路径存在但签发密钥默认值仍是开发值）；
- 客服 WebSocket 用 `?token=<共享key>` 鉴权；控制台把 key 存在浏览器 localStorage；
- `takeover / respond / resolve` 只要传入**任意存在的 agent id** 即可代表该客服操作，无"你是谁"的校验。

**要做什么**
1. 接入 ODW.ai suite 的 OIDC（`config.py` 中 `auth_oidc_*` 字段已预留但从未使用）：登录换取 JWT，服务端验签并取 `role`/`sub` claim；
2. **删除 `X-Desk-Role` 头信任路径**，角色只信 JWT claim；
3. takeover/respond 校验 `agent_id == 当前登录用户对应的 Agent`（新增 `Agent.user_id` 与 JWT sub 的绑定检查）；
4. WebSocket 握手改为一次性 ticket（REST 登录后换取、短时效），替代 URL 明文 key。

**验收标准**：未登录访问任意 admin/agents 路由返回 401；agent A 无法接管 agent B 的会话；抓包中不出现长期 API key。
**涉及文件**：`src/desk/security/`（新增 auth 模块）、`rbac.py`、`api_auth.py`、`agents/websocket.py`、`agents/inbox_api.py`、`main.py`。

### P0-2 AI 配置真正生效（配置写入后运行时不读取的"假配置"）

**现状**：设置向导 `POST /admin/setup/ai-model` 与 `GET/PUT /admin/config/ai` 已修复并正确落库（`ai_configurations` 表），但 **AI 引擎只读环境变量**——配置保存后重启前不会生效，向导形同虚设。

**要做什么**：`AIEngine.__init__` / `model_router` 启动时优先读 `ai_configurations` 行（存在则覆盖 env 默认），提供 `POST /admin/config/ai/reload` 热加载。

**验收标准**：通过向导把模型从 A 改到 B，不重启进程，新会话的 `metadata.model` 变为 B。
**涉及文件**：`ai/engine.py`、`ai/model_router.py`、`admin/api.py`。

### P0-3 许可/功能门控落地（当前整个模块无人调用）

**现状**：`LicenseManager`（上一轮刚修复崩溃）在全代码库中**没有任何调用方**，没有激活/查询 API，Free/Paid/Enterprise 的 `check_feature_gate` 从未被执行——"tier-based feature gating" 目前是纸面功能。

**要做什么**：
1. 暴露 `POST /admin/license/activate`、`GET /admin/license`；
2. 在受控路由上挂门控依赖（如 `compliance_tools` 守卫 `/admin/compliance/*`、`multi_agent` 守卫多坐席功能）；
3. 启动时 `validate_license()`，到期/宽限期状态写入 `/health`。

**验收标准**：free tier 激活后访问付费端点返回 402/403 并携带升级提示。
**涉及文件**：`license/manager.py`、`admin/api.py`、`main.py`。

### P0-4 多副本部署下实时推送失效（架构性缺口）

**现状**：客服 WebSocket 与访客 webchat 的连接表都是**进程内 dict**（`agents/websocket.py`、`webchat.manager`）。K8s 横向扩到 2 个副本后，A 副本产生的 `new_message` 广播永远到不了连在 B 副本上的客服——实时性静默丢失。

**要做什么**：把广播改为 Redis pub/sub（或复用 Redis Streams）中转，各副本订阅后投递本地连接；文档注明会话粘滞仅作降级方案。

**验收标准**：起 2 个副本 + 负载均衡，访客在副本 A 发消息，连在副本 B 的客服 ≤1s 收到事件。
**涉及文件**：`agents/websocket.py`、`channels/webchat.py`、`events/`（新增 pubsub 通道）。

---

## P1 — 短期核心功能补全

### P1-1 客服（Agent）管理 API 缺失
现在只能直接写数据库建客服（本次测试即靠 `INSERT INTO agents` 完成），控制台提示"seed an agent first"。需要：`POST/GET/PATCH /admin/agents`（创建、启停、改资料、绑定用户）、在线状态维护。
**涉及**：`agents/inbox_api.py`（已有 GET /agents）、`admin/api.py`、`static/inbox.html`。

### P1-2 网页聊天访客历史消息接口
消息已持久化（含 `read_at`），但访客刷新页面后聊天窗口的历史拉不回来（WS 无历史查询帧、无 REST 端点）。提供 `GET /webchat/history/{visitor_id}` 或 WS `get_history` 帧。
**涉及**：`channels/webchat.py`。

### P1-3 审计链验证暴露为 API + 定时任务
`ComplianceEngine.verify_audit_chain()` 已修好且可用，但没有任何入口。补 `GET /admin/compliance/audit-verify` + 每日定时校验并上报 Prometheus 指标（链被篡改时告警）。
**涉及**：`compliance/engine.py`、`admin/api.py`、`observability/metrics.py`、`main.py`（lifespan 调度）。

### P1-4 邮件通道补全：IMAP 收件
当前 inbound 依赖外部把邮件 POST 给 relay 端点；生产需要内置 IMAP 轮询器（含去重、UID 水位线）与发送重试/退信处理。
**涉及**：`channels/email.py`。

### P1-5 数据保留任务真正调度
`ComplianceEngine` 的 purge 逻辑完整但无人定时跑（README 自述"scheduling is an ops concern"——至少应提供内置 APScheduler 或 K8s CronJob 模板 + 开关）。
**涉及**：`main.py`、`k8s/helm/`、`docs/DEPLOYMENT.md`。

---

## P2 — 规模化、可观测与体验

### P2-1 消息处理器多实例与顺序保证
`consumer_name="processor-1"` 写死——多副本会同名互踩。改为随机/POD 名，并补充同一会话的事件顺序处理测试（当前 Redis Streams 按序但 `block_ms` 空轮询路径需压测确认）。同时补投递重试上限、死信可见化 API。
**涉及**：`workers/message_processor.py`、`events/redis_streams.py`。

### P2-2 数据库规模治理
`messages` 表只增不分区：补 (conversation_id, created_at) 复合索引复核、按时间分区或冷数据归档表；连接池参数（pool=10/overflow=20）写入压测基线；慢查询日志采样。
**涉及**：`alembic/versions/`（新迁移）、`db.py`。

### P2-3 可观测性补齐
25+ 指标已有，但**没有任何告警规则和 Grafana 面板**随仓库交付；`/metrics` 无鉴权（生产应限制）。建议：附 AlertManager 规则（错误率、SLA 升级率、事件积压深度、审计链断裂）、面板 JSON、指标端点保护。
**涉及**：`k8s/helm/`、`main.py`、`observability/`。

### P2-4 控制台工作台化
`/console` 目前是演示页：无历史分页加载、无附件预览、无 CSAT 展示、API key 明文存 localStorage（P0-1 登录化后自然解决）。按真实客服工作台补齐交互。
**涉及**：`static/inbox.html`、`static/webchat.html`。

### P2-5 多语言扩展
i18n 目前仅 en/zh，检测是 Unicode 启发式。补：更多语言资源表、按部署配置语言、LLM 端语言检测兜底。
**涉及**：`i18n/`。

---

## P3 — 产品化与生态

| 项 | 说明 |
|----|------|
| 渠道插件 | README 承诺的 Telegram/Discord/Slack/Signal 适配器（插件系统已就绪，需真实实现 + 契约测试） |
| 套件集成 | `desk/suite/` 目前是空壳：与 ODW.ai 共享 vault、统一登录、用量计费上报 |
| 知识库运营工具 | Vault 内容覆盖率报表、未命中问题收集（现只有检索，无反馈闭环） |
| SDK | Python/JS 客户端 SDK + Webchat 可嵌入 widget 正式化 |
| 版本治理 | `pyproject` 1.0.0 vs README 的 V1.1–V1.6 特性叙述不一致：统一为 1.6.0 并在 CHANGELOG 建立版本→特性映射 |

---

## 工程卫生（随手项，可穿插做）

1. **依赖钉版**：`redis>=5.0.4` 无上限——redis-py 8.0 已因 5s 默认读超时造成一次线上级故障（本轮已修）。对 `redis`/`fastapi`/`sqlalchemy` 等加 `<2`、`<9` 类上限并纳入 Dependabot 评估流程。涉及：`pyproject.toml`、`requirements.txt`。
2. **Schema 漂移守卫**：新增测试比对 `Base.metadata` 与 alembic head 的一致性（上轮 15 个修复中约半数源于"代码与模型列名不同步"，模型与迁移同样可能不同步）。涉及：`tests/unit/`。
3. **回归测试补账**：本轮修复的严重 bug（会话重开、PII 回写、审计 actor 强转、GDPR 删除回滚、agents 列表懒加载）大多靠人工冒烟验证，应逐一沉淀为自动化测试（目标覆盖率 72% → 80%+）。
4. **默认密钥治理**：`whatsapp_app_secret`、`vault_api_key`、`webhook_verify_token` 均有开发默认值；生产启动应像 SECRET_KEY 一样拒绝默认值（`config.py` 已有 SECRET_KEY 先例，补齐其余）。
5. **测试超时兜底**：集成/e2e 中 `asyncio.sleep(1.5/2)` 改为统一的轮询 helper（本轮集成测试已改，e2e 仍有固定等待）。

---

## 建议排期（单人粗估）

| 周期 | 内容 |
|------|------|
| 第 1–2 周 | P0-1 认证、P0-2 配置生效、工程卫生 1/4 |
| 第 3 周 | P0-4 多副本广播、P1-1 Agent 管理 |
| 第 4 周 | P0-3 许可门控、P1-2/P1-3 |
| 第 5–6 周 | P1 其余、P2-1/P2-2 |
| 之后 | P2-3/4/5 → P3 按市场优先级 |

> 本计划与 `README.md` 的 Q3 2026 首个正式发布目标对齐；P0 全部完成前不建议对外承诺生产级 SLA。
