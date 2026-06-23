# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Purpose

This is a **documentation repository** for ODW.ai Desk — a self-hosted, WhatsApp-first AI customer support agent. It contains product planning documents, not executable code. The product is in the planning phase (all documents marked "Draft" as of 2026-06-23).

## Document Structure

| Document | Purpose | When to Reference |
|----------|---------|-------------------|
| `README.md` | Product overview, positioning, monetization | Quick context on what Desk is |
| `prd.md` | Product Requirements Document | User stories, features, success metrics, scope |
| `sad.md` | System Architecture Document | High-level components, data flow, architectural decisions |
| `tsd.md` | Technical Specification Document | Detailed service specs, APIs, schemas, interfaces |
| `tbk.md` | Task Breakdown Knowledge Base | Implementation epics, tasks, subtasks, phasing |
| `research.md` | Competitive landscape research | Market positioning, competitor analysis |

## Key Architecture Concepts

**Modular monolith with event-driven internal messaging** — 14 components (Channel Gateway, Message Router, Conversation Manager, AI Engine, PII Shield, Model Router, Vault Client, Agent Inbox, Admin Dashboard, Compliance Engine, License Manager, Data Store, Event Bus, Suite Integration Layer) deployed via Docker Compose or Kubernetes Helm chart.

**Critical data flow:** Customer message → Channel Gateway (normalize) → Event Bus → Message Router (resolve customer) → Conversation Manager (persist) → AI Engine (PII detection → model routing → Vault retrieval → LLM inference → confidence scoring) → Outbound delivery or human escalation.

**Sovereignty-first design:** All conversation data stays in operator's PostgreSQL; PII detection gates frontier model usage; model-agnostic routing (local Ollama/vLLM vs frontier OpenAI/Anthropic).

## Product Context

- **Positioning:** Module of ODW.ai suite (shares auth, Vault knowledge base), not standalone Chatwoot competitor
- **Primary channel:** WhatsApp Business API (first-class); web chat and email (second-class)
- **Target market:** Regulated businesses (healthcare, legal, fintech) requiring data sovereignty
- **Monetization:** Free core (self-hosted chatbot + basic channels); paid tier (WhatsApp Business connector, multi-agent routing, compliance features)
