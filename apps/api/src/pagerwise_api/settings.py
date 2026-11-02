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
    # Chunks retrieved per question; each goes into the prompt as one [Cn] tag.
    retrieval_top_k: int = 8

    # Signs pagination cursors so clients can't forge or edit them. Override in every real deployment.
    cursor_secret: str = "dev-only-cursor-secret"
    # A streaming triage renews its heartbeat this often; one silent for triage_abandoned_after_s is treated as
    # abandoned (its process died or its client left), so it stops blocking a new triage of that incident.
    triage_heartbeat_s: int = 15
    triage_abandoned_after_s: int = 120


settings = Settings()
