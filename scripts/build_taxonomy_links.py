from __future__ import annotations

from vlegal_prototype.db import get_connection, initialize_database
from vlegal_prototype.settings import BASE_DIR


def force_corpus_database() -> None:
    import os

    os.environ["VLEGAL_DATABASE_PATH"] = str(
        BASE_DIR / "data" / "corpus" / "sqlite" / "vlegal.sqlite"
    )
from vlegal_prototype.taxonomy import bootstrap_taxonomy


def main() -> None:
    force_corpus_database()
    connection = get_connection()
    initialize_database(connection)
    subjects = bootstrap_taxonomy(connection, prefer_live=False)
    connection.close()
    print(f"Built taxonomy subjects and links for {len(subjects)} subjects.")


if __name__ == "__main__":
    main()
