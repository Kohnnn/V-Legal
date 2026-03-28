from __future__ import annotations

from vlegal_prototype.db import get_connection, initialize_database
from vlegal_prototype.relations import rebuild_relationship_graph


def main() -> None:
    connection = get_connection()
    initialize_database(connection)
    count = rebuild_relationship_graph(connection)
    print(f"Built {count} document relationships into the local graph.")
    connection.close()


if __name__ == "__main__":
    main()
