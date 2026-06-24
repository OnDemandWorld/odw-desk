# ODW.ai Desk

**Self-hosted, WhatsApp-first AI customer support agent with full data sovereignty.**

[![Python 3.14](https://img.shields.io/badge/python-3.14-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green.svg)](https://fastapi.tiangolo.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Overview

ODW.ai Desk is a production-ready, self-hosted AI customer support platform that keeps all conversation data within your infrastructure while delivering intelligent, context-aware responses grounded in your organization's knowledge base.

Unlike cloud-based solutions that send customer data to third-party APIs, Desk maintains complete data sovereignty—ideal for regulated industries (healthcare, legal, fintech, government) where compliance and privacy are non-negotiable.

## Key Features

### 🤖 AI Intelligence Pipeline
- **PII Shield**: Automatic detection and redaction of sensitive information (names, phones, emails, SSN, credit cards, medical IDs)
- **Model Router**: Intelligent routing between local models (Ollama/vLLM) and frontier models (OpenAI/Anthropic) based on PII presence and complexity
- **Vault Integration**: RAG-powered responses grounded in your organization's knowledge base
- **Confidence Scoring**: Multi-factor confidence assessment with automatic escalation to human agents
- **Brand Persona**: Configurable brand voice, tone, and vocabulary guidelines injected into AI responses
- **Response Policies**: Pre/post-generation guardrails for compliance and content control

### 💬 Channel Support
- **WhatsApp Business API**: Full support for Meta's official WhatsApp Business Platform
- **Extensible Architecture**: Plugin system ready for Telegram, Discord, Slack, Signal, and iMessage adapters
- **Real-time Updates**: WebSocket-based live conversation monitoring for agents

### 👥 Human Agent Interface
- **Agent Inbox**: REST API for conversation management, takeover, and response composition
- **Real-time Dashboard**: WebSocket connections for live conversation monitoring
- **AI Feedback**: Thumbs up/down feedback on AI responses for continuous improvement
- **Escalation Workflow**: Seamless handoff from AI to human agents with full context

### 🔒 Compliance & Governance
- **GDPR Ready**: Data export (Article 20) and deletion (Article 17) workflows
- **Tamper-Evident Audit**: Hash-chained audit log for all system actions
- **Data Retention**: Configurable retention policies with automatic enforcement
- **License Management**: Tier-based feature gating (Free/Paid/Enterprise)

### 🚀 Production Ready
- **Docker Deployment**: Multi-stage production Dockerfile with health checks
- **Kubernetes Native**: Helm charts with configurable values for scaling
- **CI/CD Pipeline**: GitHub Actions workflow with lint, test, and build stages
- **Observability**: 25+ Prometheus metrics across all system components
- **Graceful Degradation**: System continues operating when external services (LLM, Vault) are unavailable

## Architecture

```
┌─────────────────┐
│  WhatsApp API   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Channel Gateway │◄──── Other Channels (Telegram, Discord, etc.)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Message Router  │──── Customer Resolution
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Conversation    │◄──── State Machine (new → active → escalated → resolved)
│ Manager         │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│         AI Engine Orchestrator          │
├─────────────────────────────────────────┤
│  1. PII Shield (detect & redact)        │
│  2. Model Router (local vs frontier)    │
│  3. Vault Client (knowledge retrieval)  │
│  4. Prompt Builder (persona + context)  │
│  5. LLM Inference (Ollama/OpenAI)       │
│  6. Confidence Scorer (escalation)      │
│  7. Policy Engine (guardrails)          │
└────────┬────────────────────────────────┘
         │
         ▼
┌─────────────────┐
│ Outbound        │──── WhatsApp Response / Agent Notification
│ Dispatcher      │
└─────────────────┘
```

### Core Components

| Component | Responsibility | Technology |
|-----------|---------------|------------|
| **Channel Gateway** | Inbound/outbound message handling | FastAPI, WebSockets |
| **Message Router** | Customer resolution, context loading | SQLAlchemy, Redis |
| **Conversation Manager** | State machine, message persistence | PostgreSQL, async/await |
| **AI Engine** | Full RAG pipeline orchestration | Presidio, LangChain |
| **PII Shield** | PII detection and redaction | Presidio Analyzer |
| **Model Router** | Local/frontier model selection | Complexity scoring |
| **Vault Client** | Knowledge base retrieval | HTTP, Redis cache |
| **Agent Inbox** | Human agent interface | REST API, WebSocket |
| **Compliance Engine** | GDPR workflows, audit trails | Hash-chained logging |
| **License Manager** | Feature gating, tier enforcement | Database-backed |

## Quick Start

### Prerequisites

- Python 3.14+
- PostgreSQL 16+
- Redis 7+
- (Optional) Ollama or vLLM for local LLM inference
- (Optional) ODW.ai Vault for knowledge base

### Installation

1. **Clone the repository**
```bash
git clone https://github.com/OnDemandWorld/odw-desk.git
cd odw-desk
```

2. **Create virtual environment**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Configure environment**
```bash
cp .env.example .env
# Edit .env with your configuration
```

5. **Initialize database**
```bash
alembic upgrade head
```

6. **Start the application**
```bash
uvicorn desk.main:app --host 0.0.0.0 --port 8000 --reload
```

### Docker Deployment

```bash
# Build the image
docker build -t odw-desk:latest .

# Run with Docker Compose (includes PostgreSQL and Redis)
docker-compose -f docker-compose.dev.yml up -d
```

### Kubernetes Deployment

```bash
# Add Helm repository
helm repo add odw-desk ./k8s/helm

# Install with custom values
helm install desk odw-desk -f values-production.yaml
```

## Configuration

All configuration is managed through environment variables. See `.env.example` for complete reference.

### Essential Configuration

```bash
# Database
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/desk

# Redis
REDIS_URL=redis://localhost:6379/0

# WhatsApp Business API
WHATSAPP_ACCESS_TOKEN=your_token
WHATSAPP_PHONE_NUMBER_ID=your_phone_id
WHATSAPP_WEBHOOK_VERIFY_TOKEN=your_verify_token

# AI Models
OLLAMA_ENDPOINT=http://localhost:11434
LOCAL_MODEL_NAME=llama-3.1-8b
LOCAL_MODEL_ENABLED=true

# Optional: Frontier Models
FRONTIER_ENABLED=false
FRONTIER_PROVIDER=openai  # or anthropic
FRONTIER_API_KEY=your_key
FRONTIER_MODEL_NAME=gpt-4o-mini

# Vault Integration
VAULT_URL=http://localhost:8100
VAULT_API_KEY=your_vault_key
VAULT_COLLECTION_ID=your_collection_id

# Security
SECRET_KEY=your_secret_key_min_32_chars
```

## API Documentation

Once running, access the interactive API documentation:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Key Endpoints

#### WhatsApp Webhook
```
POST /api/v1/webhooks/whatsapp
```
Receives incoming WhatsApp messages from Meta.

#### Agent Inbox
```
GET    /api/v1/agents/conversations
GET    /api/v1/agents/conversations/{id}
POST   /api/v1/agents/conversations/{id}/takeover
POST   /api/v1/agents/conversations/{id}/respond
POST   /api/v1/agents/conversations/{id}/resolve
```

#### Admin APIs
```
GET    /api/v1/admin/setup/status
POST   /api/v1/admin/setup/vault
POST   /api/v1/admin/setup/whatsapp
GET    /api/v1/admin/personas
GET    /api/v1/admin/policies
GET    /api/v1/admin/compliance/audit-logs
POST   /api/v1/admin/compliance/export
POST   /api/v1/admin/compliance/delete
```

#### WebSocket
```
WS /ws/agents/{agent_id}
```
Real-time conversation updates for agents.

## Development

### Project Structure

```
desk/
├── src/desk/
│   ├── ai/                    # AI Intelligence Pipeline
│   │   ├── engine.py         # Main orchestrator
│   │   ├── pii_shield.py     # PII detection & redaction
│   │   ├── model_router.py   # Model selection logic
│   │   ├── vault_client.py   # Knowledge retrieval
│   │   ├── prompt_builder.py # Prompt composition
│   │   ├── confidence_scorer.py
│   │   └── providers/        # LLM provider implementations
│   │       ├── ollama.py
│   │       └── openai.py
│   ├── agents/               # Human agent interfaces
│   │   ├── inbox_api.py      # REST API
│   │   └── websocket.py      # Real-time updates
│   ├── admin/                # Admin & configuration APIs
│   │   ├── api.py
│   │   └── persona_policy_api.py
│   ├── channels/             # Channel adapters
│   │   ├── base.py          # Abstract adapter interface
│   │   ├── whatsapp_business.py
│   │   ├── manager.py
│   │   └── outbound.py
│   ├── conversations/        # Conversation management
│   │   ├── manager.py
│   │   └── state_machine.py
│   ├── compliance/           # GDPR & audit
│   │   └── engine.py
│   ├── license/              # License management
│   │   └── manager.py
│   ├── persona/              # Brand persona
│   │   ├── service.py
│   │   └── integration.py
│   ├── policy/               # Response policies
│   │   └── engine.py
│   ├── observability/        # Metrics & monitoring
│   │   └── metrics.py
│   ├── models/               # SQLAlchemy models
│   ├── events/               # Event bus (Redis Streams)
│   └── utils/                # Utilities
├── tests/
│   ├── integration/          # Integration tests
│   └── e2e/                  # End-to-end tests
├── alembic/                  # Database migrations
├── k8s/helm/                 # Kubernetes Helm charts
└── .github/workflows/        # CI/CD pipeline
```

### Running Tests

```bash
# Integration tests
pytest tests/integration/ -v

# End-to-end tests (requires running application)
pytest tests/e2e/ -v

# With coverage
pytest --cov=desk --cov-report=html
```

### Code Quality

```bash
# Linting
ruff check src/desk/

# Auto-fix linting issues
ruff check src/desk/ --fix

# Type checking
mypy src/desk/

# Formatting
black src/desk/
isort src/desk/
```

## Deployment

### Production Checklist

- [ ] Set `ENVIRONMENT=production`
- [ ] Configure strong `SECRET_KEY` (32+ chars)
- [ ] Set up PostgreSQL with SSL
- [ ] Configure Redis with authentication
- [ ] Set `WHATSAPP_ACCESS_TOKEN` and related credentials
- [ ] Configure Vault connection (if using knowledge base)
- [ ] Set up LLM provider (Ollama or frontier model)
- [ ] Configure monitoring/alerting
- [ ] Set up backup strategy for PostgreSQL
- [ ] Review and configure data retention policies
- [ ] Activate appropriate license tier

### Scaling Considerations

- **Horizontal Scaling**: Deploy multiple API instances behind load balancer
- **Database**: Use connection pooling (configured via `DATABASE_POOL_SIZE`)
- **Redis**: Cluster mode for high availability
- **Worker Processes**: Adjust uvicorn workers based on CPU cores
- **Async Architecture**: All I/O operations are non-blocking

## Monitoring

### Prometheus Metrics

Desk exposes 25+ metrics at `/metrics` endpoint:

- `desk_messages_received_total` - Inbound message count
- `desk_ai_pipeline_duration_seconds` - AI processing time
- `desk_pii_detected_total` - PII detection events
- `desk_llm_requests_total` - LLM API calls
- `desk_confidence_scores` - Confidence distribution
- `desk_escalations_total` - Human escalations
- `desk_active_conversations` - Current conversation count
- `desk_online_agents` - Agent availability

### Health Checks

```bash
# Application health
curl http://localhost:8000/health

# Returns:
{
  "status": "healthy",
  "version": "1.0.0",
  "components": {
    "database": "healthy",
    "redis": "healthy",
    "event_bus": "healthy"
  }
}
```

## Security

### Data Sovereignty

- All conversation data stored in your PostgreSQL instance
- PII detection prevents sensitive data from reaching external APIs
- Configurable routing: force local-only processing when PII detected
- Encrypted API keys at rest (AES-256-GCM)

### Compliance Features

- **GDPR Article 20**: Data export in JSON/CSV format
- **GDPR Article 17**: Right to erasure with audit trail
- **Audit Logging**: Tamper-evident hash-chained logs
- **Data Retention**: Automatic enforcement of retention policies

### Access Control

- License-based feature gating
- Agent role management
- API authentication (configurable)
- Webhook signature verification (HMAC-SHA256)

## Troubleshooting

### Common Issues

**Database connection failed**
```bash
# Check PostgreSQL is running
pg_isready -h localhost -p 5432

# Verify DATABASE_URL in .env
```

**Redis connection failed**
```bash
# Check Redis is running
redis-cli ping

# Verify REDIS_URL in .env
```

**WhatsApp webhook not receiving messages**
```bash
# Verify webhook URL is publicly accessible
# Check WhatsApp Business API configuration in Meta Business Suite
# Verify WHATSAPP_WEBHOOK_VERIFY_TOKEN matches Meta configuration
```

**LLM inference slow or failing**
```bash
# Check Ollama is running
curl http://localhost:11434/api/tags

# Verify model is downloaded
ollama list

# Check logs for errors
```

### Logs

All logs use structured format (JSON) via structlog:

```bash
# View application logs
tail -f logs/desk.log

# Filter by level
grep '"level": "error"' logs/desk.log
```

## Contributing

Contributions welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

### Development Workflow

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Make changes and add tests
4. Ensure all tests pass and linting is clean
5. Commit changes (`git commit -m 'Add amazing feature'`)
6. Push to branch (`git push origin feature/amazing-feature`)
7. Open Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support

- **Documentation**: See [DEVELOPMENT.md](DEVELOPMENT.md) for detailed technical documentation
- **Issues**: [GitHub Issues](https://github.com/OnDemandWorld/odw-desk/issues)
- **Discussions**: [GitHub Discussions](https://github.com/OnDemandWorld/odw-desk/discussions)

## Roadmap

### Completed (v1.0)
- ✅ WhatsApp Business API integration
- ✅ Full AI intelligence pipeline
- ✅ Human agent interfaces
- ✅ Compliance framework
- ✅ Production deployment infrastructure

### Planned (v1.1)
- 🔜 Telegram Bot Adapter
- 🔜 Discord Bot Adapter
- 🔜 Slack App Adapter
- 🔜 Signal Messenger Adapter
- 🔜 iMessage Bridge Adapter
- 🔜 Advanced persona versioning
- 🔜 Intent classifier integration

## Acknowledgments

Built with:
- [FastAPI](https://fastapi.tiangolo.com/) - Modern web framework
- [SQLAlchemy](https://www.sqlalchemy.org/) - Database ORM
- [Presidio](https://microsoft.github.io/presidio/) - PII detection
- [LangChain](https://langchain.com/) - LLM orchestration
- [Redis](https://redis.io/) - Event bus and caching
- [PostgreSQL](https://www.postgresql.org/) - Primary database

---

**Made with ❤️ for organizations that value data sovereignty**
