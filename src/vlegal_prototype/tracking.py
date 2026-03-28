from __future__ import annotations

import sqlite3

from .citations import get_document_citation_graph
from .relations import get_document_relation_graph
from .search import get_tracked_documents
from .taxonomy import get_document_subjects


SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def get_same_subject_updates(
    connection: sqlite3.Connection, document_id: int, year: int | None, limit: int = 3
) -> list[dict]:
    rows = connection.execute(
        """
        SELECT DISTINCT d.id, d.title, d.document_number, d.legal_type, d.issuance_date, d.year
        FROM document_subjects base
        JOIN document_subjects related ON related.subject_id = base.subject_id
        JOIN documents d ON d.id = related.document_id
        WHERE base.document_id = ?
          AND related.document_id <> ?
          AND (? IS NULL OR COALESCE(d.year, 0) >= ?)
        ORDER BY d.year DESC, d.issuance_date DESC, d.title ASC
        LIMIT ?
        """,
        (document_id, document_id, year, year or 0, limit),
    ).fetchall()
    return [dict(row) for row in rows]


def build_tracking_dashboard(connection: sqlite3.Connection, limit: int = 12) -> dict:
    tracked_documents = get_tracked_documents(connection, limit=limit)
    alerts: list[dict] = []
    dossiers: list[dict] = []

    for document in tracked_documents:
        relation_graph = get_document_relation_graph(connection, document["id"])
        citation_graph = get_document_citation_graph(connection, document["id"])
        subjects = get_document_subjects(connection, document["id"])
        same_subject_updates = get_same_subject_updates(
            connection, document["id"], document.get("year"), limit=3
        )

        document_alerts: list[dict] = []

        for group in relation_graph["incoming"]:
            if not group["items"]:
                continue
            severity = (
                "high" if group["label"] in {"Amended by", "Replaced by"} else "medium"
            )
            top_item = group["items"][0]
            document_alerts.append(
                {
                    "severity": severity,
                    "kind": "lifecycle",
                    "headline": f"{group['label']} in local corpus",
                    "copy": f"{document['title']} links to {len(group['items'])} newer or inbound lifecycle document(s).",
                    "document": document,
                    "target": top_item,
                }
            )

        if citation_graph["incoming_total"]:
            top_group = citation_graph["incoming_groups"][0]
            top_item = top_group["items"][0]
            document_alerts.append(
                {
                    "severity": "medium",
                    "kind": "citation",
                    "headline": "Referenced by newer local documents",
                    "copy": f"{document['title']} is cited by {citation_graph['incoming_total']} local section reference(s).",
                    "document": document,
                    "target": top_item,
                }
            )

        if same_subject_updates:
            document_alerts.append(
                {
                    "severity": "low",
                    "kind": "topic",
                    "headline": "Newer same-subject materials available",
                    "copy": f"Found {len(same_subject_updates)} recent documents in the same Phap dien subject area.",
                    "document": document,
                    "target": same_subject_updates[0],
                }
            )

        alerts.extend(document_alerts)
        dossiers.append(
            {
                "document": document,
                "subjects": subjects,
                "incoming_citations": citation_graph["incoming_total"],
                "outgoing_citations": citation_graph["outgoing_total"],
                "lifecycle_links": relation_graph["total"],
                "alerts": document_alerts,
                "same_subject_updates": same_subject_updates,
            }
        )

    alerts.sort(
        key=lambda item: (
            SEVERITY_ORDER[item["severity"]],
            item["target"].get("issuance_date") or "",
            item["document"].get("tracked_at") or "",
        ),
        reverse=False,
    )

    return {
        "tracked_documents": tracked_documents,
        "alerts": alerts,
        "alert_count": len(alerts),
        "dossiers": dossiers,
    }
