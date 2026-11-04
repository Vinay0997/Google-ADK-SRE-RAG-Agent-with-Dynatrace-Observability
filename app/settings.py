from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    google_cloud_project: str = ""
    google_cloud_location: str = "us-central1"
    google_genai_use_vertexai: bool = True
    model_name: str = "gemini-3.8-flash"
    evaluator_model: str = "gemini-3.8-flash"

    app_name: str = "sre_rag_observability"
    otel_service_name: str = "google-adk-sre-agent"
    deployment_environment: str = "demo"
    top_k: int = 3

    # Telemetry routing. Priority: collector (GKE) > direct Dynatrace > console.
    otel_collector_endpoint: str = ""
    dynatrace_otlp_endpoint: str = ""
    dynatrace_api_token: str = ""
    use_llm_evaluator: bool = True

    # GenAI telemetry
    capture_prompts: bool = True
    input_price_per_mtok: float = 0.0
    output_price_per_mtok: float = 0.0
    groundedness_threshold: float = 0.7
    hallucination_threshold: float = 0.3

    # BigQuery execution sink
    bq_enabled: bool = False
    bq_dataset: str = "agent_observability"
    bq_table: str = "agent_executions"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
