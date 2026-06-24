# Deployment Guide

This guide covers deploying ODW.ai Desk to production environments.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Docker Deployment](#docker-deployment)
- [Kubernetes Deployment](#kubernetes-deployment)
- [Configuration](#configuration)
- [Security Hardening](#security-hardening)
- [Monitoring & Observability](#monitoring--observability)
- [Backup & Recovery](#backup--recovery)
- [Scaling](#scaling)

## Prerequisites

### Required Services

- **PostgreSQL 16+**: Primary database
- **Redis 7+**: Event bus and caching
- **Python 3.14+**: Application runtime (if not using Docker)

### Optional Services

- **Ollama/vLLM**: Local LLM inference
- **ODW.ai Vault**: Knowledge base integration
- **OpenAI/Anthropic API**: Frontier model access

### Hardware Requirements

**Minimum:**
- 2 CPU cores
- 4 GB RAM
- 20 GB storage
- 100 Mbps network

**Recommended:**
- 4+ CPU cores
- 8+ GB RAM
- 50+ GB SSD storage
- 1 Gbps network

## Docker Deployment

### Build the Image

```bash
# Build production image
docker build -t odw-desk:latest .

# Verify image
docker images | grep odw-desk
```

### Run with Docker Compose

```bash
# Start all services (PostgreSQL, Redis, Desk)
docker-compose -f docker-compose.dev.yml up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f desk-api
```

### Run Standalone

```bash
docker run -d \
  --name odw-desk \
  -p 8000:8000 \
  -e DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/desk \
  -e REDIS_URL=redis://redis:6379/0 \
  -e SECRET_KEY=your-secret-key-min-32-chars \
  -e WHATSAPP_ACCESS_TOKEN=your-token \
  -e WHATSAPP_PHONE_NUMBER_ID=your-phone-id \
  odw-desk:latest
```

### Docker Best Practices

1. **Use specific image tags** (not `latest` in production)
2. **Set resource limits**:
   ```bash
   docker run --memory=2g --cpus=2 ...
   ```
3. **Enable health checks** (already configured in Dockerfile)
4. **Use Docker secrets** for sensitive data
5. **Mount volumes** for persistent data

## Kubernetes Deployment

### Using Helm

```bash
# Add repository
helm repo add odw-desk ./k8s/helm

# Install with default values
helm install desk odw-desk

# Install with custom values
helm install desk odw-desk -f values-production.yaml

# Upgrade
helm upgrade desk odw-desk -f values-production.yaml

# Uninstall
helm uninstall desk
```

### Custom Values

Create `values-production.yaml`:

```yaml
replicaCount: 3

image:
  repository: your-registry/odw-desk
  tag: "1.0.0"

resources:
  limits:
    cpu: 2000m
    memory: 4Gi
  requests:
    cpu: 1000m
    memory: 2Gi

config:
  environment: production
  databaseUrl: postgresql+asyncpg://user:pass@postgres:5432/desk
  redisUrl: redis://redis-master:6379/0
  secretKey: your-production-secret
  
ingress:
  enabled: true
  hosts:
    - host: desk.yourdomain.com
      paths:
        - path: /
          pathType: Prefix
  tls:
    - secretName: desk-tls
      hosts:
        - desk.yourdomain.com

postgresql:
  enabled: true
  auth:
    username: desk
    password: strong-password
    database: desk
  primary:
    persistence:
      enabled: true
      size: 50Gi

redis:
  enabled: true
  master:
    persistence:
      enabled: true
      size: 10Gi
```

### Manual Kubernetes Deployment

```bash
# Apply manifests
kubectl apply -f k8s/manifests/

# Check deployment
kubectl get pods -l app=odw-desk

# View logs
kubectl logs -f deployment/odw-desk
```

## Configuration

### Environment Variables

See `.env.example` for complete list. Key variables:

**Required:**
```bash
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/desk
REDIS_URL=redis://host:6379/0
SECRET_KEY=min-32-chars-secret-key
WHATSAPP_ACCESS_TOKEN=your-token
WHATSAPP_PHONE_NUMBER_ID=your-phone-id
WHATSAPP_WEBHOOK_VERIFY_TOKEN=your-verify-token
```

**AI Configuration:**
```bash
# Local model (recommended for privacy)
OLLAMA_ENDPOINT=http://ollama:11434
LOCAL_MODEL_NAME=llama-3.1-8b
LOCAL_MODEL_ENABLED=true

# Frontier model (optional)
FRONTIER_ENABLED=false
FRONTIER_PROVIDER=openai
FRONTIER_API_KEY=your-key
FRONTIER_MODEL_NAME=gpt-4o-mini
```

**Vault Integration:**
```bash
VAULT_URL=http://vault:8100
VAULT_API_KEY=your-vault-key
VAULT_COLLECTION_ID=your-collection-id
```

### Database Initialization

```bash
# Run migrations
alembic upgrade head

# Verify
alembic current
```

### WhatsApp Business API Setup

1. **Create Meta Business Account**
   - Go to [business.facebook.com](https://business.facebook.com)
   - Create or select your business

2. **Set Up WhatsApp Business Account**
   - Add WhatsApp account to your business
   - Complete phone number verification

3. **Get API Credentials**
   - Access Token: From Meta Business Suite
   - Phone Number ID: From WhatsApp Business API settings
   - Webhook Verify Token: Your custom token

4. **Configure Webhook**
   - URL: `https://your-domain.com/api/v1/webhooks/whatsapp`
   - Verify token: Must match `WHATSAPP_WEBHOOK_VERIFY_TOKEN`
   - Subscribe to `messages` field

5. **Test Webhook**
   - Send test message to your WhatsApp number
   - Check application logs for incoming webhook

## Security Hardening

### Network Security

1. **Use HTTPS** (TLS 1.3+)
   ```nginx
   server {
     listen 443 ssl http2;
     ssl_certificate /path/to/cert.pem;
     ssl_certificate_key /path/to/key.pem;
     ssl_protocols TLSv1.3;
   }
   ```

2. **Firewall Rules**
   - Allow only necessary ports (443, 5432, 6379)
   - Restrict database access to application servers
   - Use VPN for admin access

3. **Webhook Verification**
   - Always verify webhook signatures
   - Use strong verify tokens
   - Validate request origin

### Application Security

1. **Strong Secrets**
   ```bash
   # Generate strong secret
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

2. **Database Security**
   - Use strong passwords
   - Enable SSL connections
   - Restrict user permissions
   - Regular security audits

3. **Redis Security**
   - Enable authentication
   - Use TLS for connections
   - Restrict network access

4. **API Security**
   - Rate limiting
   - CORS configuration
   - Input validation
   - SQL injection prevention (using SQLAlchemy ORM)

### Data Security

1. **PII Protection**
   - PII Shield enabled by default
   - Configure redaction rules
   - Monitor PII detection logs

2. **Encryption**
   - API keys encrypted at rest (AES-256-GCM)
   - Database encryption enabled
   - TLS for all connections

3. **Access Control**
   - License-based feature gating
   - Agent role management
   - Audit all access

## Monitoring & Observability

### Prometheus Metrics

Metrics available at `/metrics` endpoint:

```bash
# Check metrics
curl http://localhost:8000/metrics
```

**Key Metrics:**
- `desk_messages_received_total` - Inbound messages
- `desk_ai_pipeline_duration_seconds` - AI processing time
- `desk_pii_detected_total` - PII detections
- `desk_llm_requests_total` - LLM API calls
- `desk_confidence_scores` - Confidence distribution
- `desk_escalations_total` - Human escalations
- `desk_active_conversations` - Active conversations

### Grafana Dashboards

Import dashboard from `docs/grafana-dashboard.json` (create if needed).

**Recommended Panels:**
1. Message throughput (messages/minute)
2. AI pipeline latency (p50, p95, p99)
3. PII detection rate
4. LLM token usage
5. Confidence score distribution
6. Active conversations
7. Error rates

### Logging

**Log Levels:**
- DEBUG: Development only
- INFO: Normal operation
- WARNING: Potential issues
- ERROR: Failures requiring attention
- CRITICAL: System-breaking issues

**Log Aggregation:**
```bash
# Example: Forward to Elasticsearch
# Configure in logging configuration
```

### Health Checks

```bash
# Application health
curl http://localhost:8000/health

# Database health
curl http://localhost:8000/health | jq '.database'

# Redis health
curl http://localhost:8000/health | jq '.redis'
```

### Alerting

**Recommended Alerts:**
1. High error rate (>5% of requests)
2. High latency (p95 > 5s)
3. Database connection failures
4. Redis connection failures
5. Low disk space (<10%)
6. High memory usage (>80%)
7. PII detection anomalies

## Backup & Recovery

### Database Backup

**PostgreSQL:**
```bash
# Automated backup script
pg_dump -h localhost -U desk desk > backup_$(date +%Y%m%d).sql

# Restore
psql -h localhost -U desk desk < backup_20260624.sql
```

**Automation:**
```bash
# Crontab entry (daily at 2 AM)
0 2 * * * /path/to/backup.sh
```

### Redis Backup

```bash
# Enable RDB persistence in redis.conf
save 900 1
save 300 10
save 60 10000

# Manual backup
redis-cli BGSAVE
```

### Disaster Recovery

1. **RTO (Recovery Time Objective)**: 1 hour
2. **RPO (Recovery Point Objective)**: 1 hour (based on backup frequency)

**Recovery Steps:**
1. Restore PostgreSQL from latest backup
2. Restore Redis from latest RDB file
3. Run `alembic upgrade head`
4. Start application
5. Verify health checks
6. Test with sample message

### Backup Verification

```bash
# Test restore to separate instance
createdb desk_test
psql -d desk_test < backup.sql
# Verify data integrity
```

## Scaling

### Horizontal Scaling

**Application:**
```bash
# Kubernetes
kubectl scale deployment/odw-desk --replicas=5

# Docker Compose
docker-compose up -d --scale desk-api=5
```

**Considerations:**
- Stateless application (safe to scale)
- Redis for session sharing
- Database connection pooling
- Load balancer configuration

### Vertical Scaling

**Increase Resources:**
```yaml
# Kubernetes
resources:
  limits:
    cpu: 4000m
    memory: 8Gi
```

### Database Scaling

**Read Replicas:**
```bash
# PostgreSQL replication
# Configure in postgresql.conf
```

**Connection Pooling:**
```bash
# Already configured via DATABASE_POOL_SIZE
# Adjust based on load
```

### Redis Scaling

**Redis Cluster:**
```bash
# Configure Redis Cluster
# Update REDIS_URL to cluster endpoint
```

**Cache Strategy:**
- Vault queries cached (10-min TTL)
- Customer lookups cached
- Session data in Redis

### Performance Tuning

**Uvicorn Workers:**
```bash
# Formula: (2 x CPU cores) + 1
uvicorn desk.main:app --workers 9
```

**Database:**
```bash
# Increase pool size
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=30
```

**Redis:**
```bash
# Optimize connection pool
# Configure in redis.conf
```

## Production Checklist

- [ ] All environment variables configured
- [ ] Strong SECRET_KEY set
- [ ] Database SSL enabled
- [ ] Redis authentication enabled
- [ ] HTTPS/TLS configured
- [ ] WhatsApp webhook verified
- [ ] PII Shield enabled
- [ ] Audit logging enabled
- [ ] Monitoring configured
- [ ] Alerts configured
- [ ] Backup strategy implemented
- [ ] Disaster recovery tested
- [ ] Load testing completed
- [ ] Security audit completed
- [ ] Documentation reviewed
- [ ] Team trained

## Support

- **Documentation**: [README.md](../README.md)
- **Issues**: [GitHub Issues](https://github.com/OnDemandWorld/odw-desk/issues)
- **Discussions**: [GitHub Discussions](https://github.com/OnDemandWorld/odw-desk/discussions)

---

**Last Updated**: 2026-06-24
