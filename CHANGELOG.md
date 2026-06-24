# Changelog

All notable changes to ODW.ai Desk will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
