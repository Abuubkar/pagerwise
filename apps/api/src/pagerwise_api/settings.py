from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://pagerwise:pagerwise@localhost:5435/pagerwise"

    # Ollama runs natively on the host: Docker on macOS has no GPU access. See docs/adr/0001.
    ollama_host: str = "http://localhost:11434"
    llm_model: str = "qwen3.5:9b-q4_K_M"
    llm_temperature: float = 0.0
    # Always sent explicitly: Ollama's default context is small and truncates long prompts silently.
    llm_num_ctx: int = 8192
    # Room kept for the answer; also sent as num_predict so the answer can't eat into the prompt's share.
    llm_max_output_tokens: int = 1024
    # Qwen3.5 thinks by default; the answer contract is plain text, so thinking stays off.
    llm_think: bool = False
    llm_keep_alive: str = "10m"
    llm_timeout_s: float = 180.0

    embedding_model: str = "BAAI/bge-small-en-v1.5"
    # Which chunk embedding vector search reads: v1 (bge-small, chunks.embedding), v2 (bge-base, embedding_v2) or
    # dual (both, fused with full-text search). See migration 0009 and docs/adr/0009.
    retrieval_embedding_version: str = "v2"  # v2 won on both eval splits (docs/adr/0009); v1 stays until 6b
    # A chunk in the top results brings its document's other chunks in right after it (retrieval._with_siblings).
    retrieval_sibling_chunks: bool = True
    embedding_model_v2: str = "BAAI/bge-base-en-v1.5"
    # Chunks retrieved per question; each goes into the prompt as one [Cn] tag.
    retrieval_top_k: int = 8
    # Cross-encoder that can reorder hybrid search's candidates (docs/adr/0006). Off by default since slice 6: with
    # v2 embeddings and sibling chunks it changed no eval metric and cost ~490 ms per search (docs/adr/0009).
    reranker_model: str = "Xenova/ms-marco-MiniLM-L-6-v2"
    # Fused candidates the reranker reads. 0 turns reranking off (results in fused order).
    rerank_candidates: int = 0

    # Signs pagination cursors so clients can't forge or edit them. Override in every real deployment.
    cursor_secret: str = "dev-only-cursor-secret"
    # A streaming triage renews its heartbeat this often; one silent for triage_abandoned_after_s is treated as
    # abandoned (its process died or its client left), so it stops blocking a new triage of that incident.
    triage_heartbeat_s: int = 15
    triage_abandoned_after_s: int = 120
    # Evidence sources, fetched concurrently, each with its own timeout. The plan said 300/300/500 ms; hybrid search
    # with reranking takes ~0.5 s on its own (ADR 0006), and two run at once on the CPU, so the document sources
    # get 2 s. A source over its timeout is left out of the brief and named in degraded_sources.
    triage_timeout_runbooks_s: float = 2.0
    triage_timeout_postmortems_s: float = 2.0
    triage_timeout_deploys_s: float = 0.5
    triage_runbooks_k: int = 4
    triage_postmortems_k: int = 3
    triage_deploys_max: int = 5
    triage_deploy_window_h: int = 2  # deploys this long before the incident opened are evidence
    deploy_source_url: str = "http://localhost:8002"  # docs_mock's /v1/deploys stands in for a deploy tool
    # Per-tenant limit on queued + running triages; one more gets 503 with Retry-After.
    triage_tenant_limit: int = 2
    triage_slot_ttl_s: int = 900  # a slot a crashed worker never released frees itself after this
    triage_retry_after_s: int = 30
    triage_poll_s: float = 5.0  # the worker also checks for queued runs this often, in case a wake-up was lost

    # Browser origins allowed to open GraphQL subscriptions (WebSocket handshakes aren't covered by CORS).
    web_origins: list[str] = ["http://localhost:3001"]
    redis_url: str = "redis://localhost:6379/0"
    incident_updates_channel: str = "incidents"  # JSON per changed incident; slice 5's GraphQL subscription reads it

    kafka_bootstrap: str = "localhost:19092"
    consumer_group: str = "pagerwise-consumer"
    # Backpressure: fetching pauses when this many records are queued for processing and resumes once the queue
    # drains to the low mark. The gap between the two marks is what stops it flapping.
    consumer_queue_high: int = 500
    consumer_queue_low: int = 100
    # The consumer's own pool (one transaction per partition batch). Fetching also pauses while this share of it is
    # checked out, and resumes below the low share.
    consumer_db_pool_size: int = 20
    consumer_pool_high: float = 0.9
    consumer_pool_low: float = 0.5
    consumer_drain_s: float = 20.0  # on SIGTERM: time allowed to finish queued records before committing and exiting
    # Fault injection for load tests, off by default: this share of events fails transiently, picked by a hash of
    # event_id so every replica agrees. Four in five of those fail once, one in five fails twice.
    consumer_fault_transient_rate: float = 0.0
    # Delay before a message on a retry topic is processed. Tests shorten these; the topic names stay.
    retry_delay_30s_s: float = 30.0
    retry_delay_5m_s: float = 300.0


settings = Settings()
