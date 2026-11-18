from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(',') if item.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / '.env'),
        env_file_encoding='utf-8',
        extra='ignore',
        case_sensitive=False,
    )

    app_name: str = Field(default='DarGlobal & Wasalt AI Assistant', alias='APP_NAME')
    app_env: str = Field(default='development', alias='APP_ENV')
    app_version: str = Field(default='1.0.0', alias='APP_VERSION')
    log_level: str = Field(default='INFO', alias='LOG_LEVEL')
    host: str = Field(default='0.0.0.0', alias='HOST')
    port: int = Field(default=7860, alias='PORT')

    cors_origins: str = Field(
        default='http://localhost:5173,http://127.0.0.1:5173,http://localhost:8080,http://127.0.0.1:8080',
        alias='CORS_ORIGINS',
    )
    trust_proxy_headers: bool = Field(default=True, alias='TRUST_PROXY_HEADERS')

    openrouter_api_key: str = Field(default='', alias='OPENROUTER_API_KEY')
    openrouter_base_url: str = Field(default='https://openrouter.ai/api/v1', alias='OPENROUTER_BASE_URL')
    openrouter_model: str = Field(default='auto', alias='OPENROUTER_MODEL')
    openrouter_fallback_models: str = Field(
        default=(
            'google/gemma-4-31b-it:free,'
            'nvidia/nemotron-3.5-lightning:free,'
            'inclusionai/ling-3.2-flash:free,'
            'baidu/ernie-5.5-flash-preview:free,'
            'openrouter/free'
        ),
        alias='OPENROUTER_FALLBACK_MODELS',
    )
    openrouter_site_url: str = Field(
        default='https://github.com/utsab345/darglobal-ai-assistant',
        alias='OPENROUTER_SITE_URL',
    )
    openrouter_app_name: str = Field(default='DarGlobal AI Assistant', alias='OPENROUTER_APP_NAME')
    openrouter_timeout_seconds: float = Field(default=60.0, alias='OPENROUTER_TIMEOUT_SECONDS')
    openrouter_max_tokens: int = Field(default=1200, alias='OPENROUTER_MAX_TOKENS')
    openrouter_temperature: float = Field(default=0.2, alias='OPENROUTER_TEMPERATURE')
    openrouter_retries: int = Field(default=2, alias='OPENROUTER_RETRIES')

    embedding_provider: str = Field(default='auto', alias='EMBEDDING_PROVIDER')
    embedding_model: str = Field(default='BAAI/bge-small-en-v1.5', alias='EMBEDDING_MODEL')
    embedding_cache_dir: str = Field(default='.cache/fastembed', alias='EMBEDDING_CACHE_DIR')
    embedding_threads: int = Field(default=2, alias='EMBEDDING_THREADS')

    data_dir: str = Field(default='backend/data', alias='DATA_DIR')
    static_dir: str = Field(default='static', alias='STATIC_DIR')
    chunk_size: int = Field(default=900, alias='CHUNK_SIZE')
    chunk_overlap: int = Field(default=150, alias='CHUNK_OVERLAP')
    top_k_results: int = Field(default=6, alias='TOP_K_RESULTS')
    rag_min_score: float | None = Field(default=None, alias='RAG_MIN_SCORE')
    rag_max_chunks_per_url: int = Field(default=3, alias='RAG_MAX_CHUNKS_PER_URL')
    auto_build_kb: bool = Field(default=True, alias='AUTO_BUILD_KB')

    scrape_rate_limit_seconds: float = Field(default=1.2, alias='SCRAPE_RATE_LIMIT_SECONDS')
    scrape_timeout_seconds: float = Field(default=25.0, alias='SCRAPE_TIMEOUT_SECONDS')
    scrape_max_pages_per_site: int = Field(default=120, alias='SCRAPE_MAX_PAGES_PER_SITE')
    scrape_refresh_days: int = Field(default=7, alias='SCRAPE_REFRESH_DAYS')
    scrape_admin_token: str = Field(default='', alias='SCRAPE_ADMIN_TOKEN')
    scrape_user_agent: str = Field(
        default='DarGlobalAIAssistant/1.0 (+https://github.com/utsab345/darglobal-ai-assistant; research assistant)',
        alias='SCRAPE_USER_AGENT',
    )

    rate_limit_chat: str = Field(default='30/minute', alias='RATE_LIMIT_CHAT')
    rate_limit_scrape: str = Field(default='2/hour', alias='RATE_LIMIT_SCRAPE')

    @property
    def cors_origin_list(self) -> list[str]:
        return _split_csv(self.cors_origins)

    @property
    def openrouter_fallback_list(self) -> list[str]:
        return _split_csv(self.openrouter_fallback_models)

    @property
    def openrouter_configured(self) -> bool:
        return bool(self.openrouter_api_key.strip())

    def resolve_path(self, value: str) -> Path:
        path = Path(value)
        return path if path.is_absolute() else PROJECT_ROOT / path

    @property
    def data_path(self) -> Path:
        return self.resolve_path(self.data_dir)

    @property
    def raw_data_dir(self) -> Path:
        return self.data_path / 'raw'

    @property
    def processed_data_dir(self) -> Path:
        return self.data_path / 'processed'

    @property
    def vector_dir(self) -> Path:
        return self.data_path / 'vectorstore'

    @property
    def static_path(self) -> Path:
        return self.resolve_path(self.static_dir)

    @property
    def embedding_cache_path(self) -> Path:
        return self.resolve_path(self.embedding_cache_dir)


settings = Settings()
