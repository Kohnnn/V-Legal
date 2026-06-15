from __future__ import annotations

import secrets
from functools import lru_cache
from pathlib import Path
from urllib.request import Request, urlopen
import json

from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "V-Legal Prototype"
    environment: str = "development"
    dataset_name: str = "th1nhng0/vietnamese-legal-documents"
    hf_token: str = ""
    database_path: Path = BASE_DIR / "data" / "corpus" / "sqlite" / "vlegal.sqlite"
    corpus_root: Path = BASE_DIR / "data" / "corpus"
    default_import_limit: int = 500
    search_page_size: int = 12
    answer_passage_limit: int = 6
    phapdien_main_url: str = "https://phapdien.moj.gov.vn/TraCuuPhapDien/MainBoPD.aspx"
    phapdien_ebook_url: str = (
        "https://phapdien.moj.gov.vn/TraCuuPhapDien/Files/BoPhapDienDienTu.zip"
    )
    government_portal_base_url: str = "https://vanban.chinhphu.vn"
    government_portal_detail_pageid: str = "27160"
    ocr_python_path: Path = BASE_DIR / ".venv-ocr" / "Scripts" / "python.exe"
    public_base_url: str = "http://127.0.0.1:8000"
    cors_allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    enable_ai_schema_sidecar: bool = False
    ai_schema_provider: str = "off"
    ai_schema_model: str = ""
    ai_schema_endpoint: str = ""
    ai_schema_api_key: str = ""
    ai_schema_timeout_seconds: int = 45

    minimax_api_key: str = ""
    minimax_api_url: str = "https://api.minimax.io/v1"
    minimax_model: str = "MiniMax-M2.7"
    minimax_timeout_seconds: int = 600

    skip_startup_maintenance: bool = False
    skip_remote_user_data: bool = False

    appwrite_endpoint: str = "https://cloud.appwrite.io/v1"
    appwrite_project_id: str = ""
    appwrite_database_id: str = ""
    appwrite_api_key: str = ""

    secret_key: str = ""

    model_config = SettingsConfigDict(
        env_prefix="VLEGAL_",
        env_file=".env",
        extra="ignore",
    )

    def ensure_runtime_paths(self) -> None:
        legacy_path = BASE_DIR / "data" / "vlegal.sqlite"
        corpus_sqlite = BASE_DIR / "data" / "corpus" / "sqlite" / "vlegal.sqlite"
        normalized_database_path = (BASE_DIR / self.database_path).resolve() if not self.database_path.is_absolute() else self.database_path.resolve()
        if normalized_database_path == legacy_path.resolve() and corpus_sqlite.exists():
            self.database_path = corpus_sqlite
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.corpus_root.mkdir(parents=True, exist_ok=True)

    def resolve_appwrite_placeholders(self) -> None:
        env_path = BASE_DIR / ".env"
        if not env_path.exists():
            return
        lines = env_path.read_text(encoding="utf-8").splitlines()

        def first_real(key: str) -> str:
            for line in lines:
                if not line.startswith(f"{key}="):
                    continue
                value = line.split("=", 1)[1].strip()
                if not value or value.lower().startswith("your_"):
                    continue
                return value
            return ""

        if not self.appwrite_endpoint or "cloud.appwrite.io" in self.appwrite_endpoint:
            self.appwrite_endpoint = first_real("VLEGAL_APPWRITE_ENDPOINT") or self.appwrite_endpoint
        if not self.appwrite_project_id or self.appwrite_project_id.lower().startswith("your_"):
            self.appwrite_project_id = first_real("VLEGAL_APPWRITE_PROJECT_ID") or self.appwrite_project_id
        if not self.appwrite_api_key or self.appwrite_api_key.lower().startswith("your_"):
            self.appwrite_api_key = first_real("VLEGAL_APPWRITE_API_KEY") or self.appwrite_api_key
        if not self.appwrite_database_id or self.appwrite_database_id.lower().startswith("your_"):
            candidate = first_real("VLEGAL_APPWRITE_DATABASE_ID")
            if candidate:
                self.appwrite_database_id = candidate
            elif (
                not self.skip_remote_user_data
                and self.appwrite_endpoint
                and self.appwrite_project_id
                and self.appwrite_api_key
            ):
                # Only reach out to Appwrite when remote user data is actually
                # in use. On the local/markdown-first path this blocking HTTP
                # call sits on the hot path of the first get_connection(), so it
                # must never run there. Keep the timeout short as a backstop.
                try:
                    request = Request(
                        f"{self.appwrite_endpoint.rstrip('/')}/tablesdb",
                        headers={
                            "X-Appwrite-Project": self.appwrite_project_id,
                            "X-Appwrite-Key": self.appwrite_api_key,
                        },
                    )
                    with urlopen(request, timeout=5) as response:
                        payload = json.loads(response.read().decode("utf-8"))
                    databases = payload.get("databases") or []
                    if len(databases) == 1 and databases[0].get("$id"):
                        self.appwrite_database_id = databases[0]["$id"]
                except Exception:
                    pass

    def get_cors_origins(self) -> list[str]:
        return [
            item.strip()
            for item in self.cors_allowed_origins.split(",")
            if item.strip()
        ]

    def get_secret_key(self) -> str:
        if not self.secret_key:
            self.secret_key = secrets.token_hex(32)
        return self.secret_key


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_runtime_paths()
    settings.resolve_appwrite_placeholders()
    return settings
