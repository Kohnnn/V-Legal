from __future__ import annotations

from vlegal_prototype.citations import rebuild_citation_index
from vlegal_prototype.db import get_connection, initialize_database


def main() -> None:
    connection = get_connection()
    initialize_database(connection)
    count = rebuild_citation_index(connection)
    print(f"Built {count} citation links into the local index.")
    connection.close()


if __name__ == "__main__":
    main()
