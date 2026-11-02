---
status: accepted
date: 2026-11-02
---

# Runtime baseline: Python 3.13 via uv, pgvector/pgvector:0.8.7-pg18 image, uv workspace from day one

- **Python 3.13** (uv-managed, pinned in `.python-version`). The plan said 3.12; Ledgerline (its ADR 0004) runs
  3.13 with the same libraries, so both projects share one set of habits. 3.14 is installed but compiled wheels
  (asyncpg, onnxruntime for fastembed) are the safer bet on 3.13.
- **Postgres 18 with pgvector 0.8.7**, the official `pgvector/pgvector:0.8.7-pg18-trixie` image. The plan said 16.
  18 brings `uuidv7()` for time-ordered primary keys. PGDATA moved in 18, so the volume mounts
  `/var/lib/postgresql`. Port 5435, because Ledgerline holds 5434.
- **uv workspace root with one member (`apps/api`)**. One member is ahead of its second use, but `apps/consumer`,
  `apps/indexer` and others arrive in slices 3–4 and moving the package later would churn every import path.
- **No vector index yet.** Eight chunks scan faster than any index lookup; HNSW arrives with the 180-document
  corpus in slice 4.

## Considered options

- Python 3.12 and Postgres 16, as written in the plan: no feature we need, and a second set of versions to keep
  in mind next to Ledgerline.

## Assumptions

- Developers run Docker locally; port 5435 is free (it was on 2026-11-02).
- The pgvector SQLAlchemy type sends vectors as text, so asyncpg needs no `register_vector` hook. True for
  pgvector-python 0.5.1.
