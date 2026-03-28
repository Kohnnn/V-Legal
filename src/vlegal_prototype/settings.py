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

    model_config = SettingsConfigDict(
        env_prefix="VLEGAL_",
        env_file=".env",
        extra="ignore",
    )

    def ensure_runtime_paths(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_runtime_paths()
    return settings
