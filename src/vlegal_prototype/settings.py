from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "V-Legal Prototype"
    environment: str = "development"
    dataset_name: str = "th1nhng0/vietnamese-legal-documents"
    database_path: Path = BASE_DIR / "data" / "vlegal.sqlite"
    default_import_limit: int = 500
    search_page_size: int = 12
    answer_passage_limit: int = 6
    phapdien_main_url: str = "https://phapdien.moj.gov.vn/TraCuuPhapDien/MainBoPD.aspx"
    public_base_url: str = "http://127.0.0.1:8000"
    cors_allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    model_config = SettingsConfigDict(
        env_prefix="VLEGAL_",
        env_file=".env",
        extra="ignore",
    )

    def ensure_runtime_paths(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)

    def get_cors_origins(self) -> list[str]:
        return [
            item.strip()
            for item in self.cors_allowed_origins.split(",")
            if item.strip()
        ]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_runtime_paths()
    return settings
