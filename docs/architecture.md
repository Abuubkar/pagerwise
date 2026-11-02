# Pagerwise: target architecture

Copied from 02-pagerwise.md in slice 1. A destination, not a to-do list: each folder, service and dependency
appears only when a slice needs it (HOW_WE_BUILD.md section 2). Where an ADR changed a choice below, the ADR wins
(e.g. the model: ADR 0001; Python and Postgres versions: ADR 0002).

**Stack:** Python 3.12, uv workspaces, FastAPI, Pydantic v2, SQLAlchemy 2.0 async + asyncpg, Alembic, Strawberry GraphQL (with subscriptions over graphql-transport-ws), aiokafka, Redpanda (Kafka API) + Redpanda Console, Postgres 16 with pgvector, Redis 7, fastembed for local embeddings and reranking, Next.js 15 + TypeScript UI, pnpm.

```text
  apps/api/          FastAPI: REST /v1, GraphQL /graphql (+ subscriptions), SSE /v1/incidents/{id}/triage/stream
  apps/consumer/     long-running aiokafka consumer service (alerts, deploys, logs)
  apps/indexer/      document importer + embedding/indexing jobs
  apps/simulator/    event generator: emits realistic alert storms, deploys, and log samples for a 12-service system; configurable rate and failure scenarios
  apps/docs_mock/    mock docs API (runbooks/postmortems) with Link-header pagination, ETags, and injectable 5xx
  apps/web/          Next.js incident list, timeline, and triage brief viewer
  packages/core/     domain types: Alert, Incident, Evidence, ServiceGraph
  packages/db/       models, sessions, Alembic
  packages/kafka/    typed producer/consumer wrappers, header schema, retry-topic router
  packages/retrieval/ chunking, embedding, hybrid search, RRF, rerank
  packages/ai/       Ollama client, prompts, citation-tag parser, token/latency accounting
  packages/clients/  generated clients (never hand-edited)
  packages/telemetry/
  contracts/         openapi.yaml, schema.graphql, kafka/ (JSON Schema per topic + AsyncAPI 3.0 doc)
  evals/ infra/ scripts/ .github/workflows/
```
