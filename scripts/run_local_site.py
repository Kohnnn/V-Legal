from __future__ import annotations

import os

import uvicorn

from vlegal_prototype.settings import BASE_DIR


def main() -> None:
    os.environ["VLEGAL_DATABASE_PATH"] = str(
        BASE_DIR / "data" / "corpus" / "sqlite" / "vlegal.sqlite"
    )
    os.environ["VLEGAL_SKIP_STARTUP_MAINTENANCE"] = "true"
    os.environ["VLEGAL_SKIP_REMOTE_USER_DATA"] = "true"
    port = int(os.environ.get("VLEGAL_LOCAL_PORT", "8000"))
    uvicorn.run(
        "vlegal_prototype.app:app",
        host="127.0.0.1",
        port=port,
        reload=False,
        app_dir=str(BASE_DIR / "src"),
    )


if __name__ == "__main__":
    main()
