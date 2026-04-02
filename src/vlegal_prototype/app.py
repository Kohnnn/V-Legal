from __future__ import annotations

import os
from pathlib import Path

import markdown
import uvicorn
from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markupsafe import Markup
from pydantic import BaseModel, Field

from .answering import build_grounded_brief
from .appwrite_client import (
    aw_create_research_view,
    aw_delete_research_view,
    aw_get_research_view,
    aw_list_research_views,
    aw_list_tracked,
    aw_track_document,
    aw_untrack_document,
)
from .citations import (
    get_citation_count,
    get_document_citation_graph,
    get_section_citation_counts,
    rebuild_citation_index,
)
from .compare import build_compare_view
from .db import get_connection, get_stats, initialize_database, is_empty
from .provenance import build_provenance_profile, enrich_documents_with_provenance
from .relations import (
    get_document_relation_graph,
    get_relation_count,
    rebuild_relationship_graph,
)
from .search import (
    get_document,
    get_filter_options,
    get_recent_documents,
    get_related_documents,
    get_top_legal_types,
    get_tracked_document_ids,
    get_tracked_documents,
    retrieve_passages,
    search_documents,
    set_document_tracking,
)
from .settings import BASE_DIR, get_settings
from .taxonomy import (
    bootstrap_taxonomy,
    get_document_subjects,
    get_taxonomy_subject_by_slug,
    get_taxonomy_subjects,
)
from .structure import inject_document_links, prepare_document_markup
from .tracking import build_tracking_dashboard, get_same_subject_updates


def get_user_id(request: Request) -> str:
    uid = request.headers.get("x-user-id", "").strip()
    if not uid or len(uid) < 8:
        uid = os.urandom(16).hex()
    return uid


settings = get_settings()
app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


class AskRequest(BaseModel):
    question: str = Field(min_length=4, max_length=600)
    document_id: int | None = None


class TrackRequest(BaseModel):
    tracked: bool


def get_db():
    connection = get_connection()
    try:
        yield connection
    finally:
        connection.close()


@app.on_event("startup")
def startup() -> None:
    connection = get_connection()
    try:
        initialize_database(connection)
        if (
            connection.execute("SELECT COUNT(*) FROM taxonomy_subjects").fetchone()[0]
            == 0
        ):
            bootstrap_taxonomy(connection, prefer_live=False)
        if (
            connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0] > 0
            and get_relation_count(connection) == 0
        ):
            rebuild_relationship_graph(connection)
        if (
            connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0] > 0
            and get_citation_count(connection) == 0
        ):
            rebuild_citation_index(connection)
    finally:
        connection.close()


def render_markdown(value: str) -> Markup:
    prepared_markdown, _ = prepare_document_markup(value)
    html = markdown.markdown(
        prepared_markdown,
        extensions=["tables", "fenced_code", "sane_lists", "toc"],
        output_format="html5",
    )
    return Markup(html)


def build_citation_map(citation_graph: dict) -> dict[str, int]:
    link_map: dict[str, int] = {}

    def norm(value: str) -> str:
        import unicodedata

        return (
            "".join(
                c
                for c in unicodedata.normalize("NFD", value)
                if unicodedata.category(c) != "Mn"
            )
        ).lower()

    for group in citation_graph.get("outgoing_groups", []):
        for item in group["items"]:
            normalized = item.get("document_number", "")
            if normalized and item["id"] not in link_map.values():
                link_map[norm(normalized)] = item["id"]
    for group in citation_graph.get("incoming_groups", []):
        for item in group["items"]:
            normalized = item.get("document_number", "")
            if normalized and item["id"] not in link_map.values():
                link_map[norm(normalized)] = item["id"]
    return link_map


@app.get("/", response_class=HTMLResponse)
def home(
    request: Request,
    q: str = "",
    page: int = 1,
    legal_type: str | None = None,
    year: int | None = None,
    issuer: str | None = None,
    topic: str | None = None,
    connection=Depends(get_db),
):
    user_id = get_user_id(request)
    stats = get_stats(connection)
    options = get_filter_options(connection)
    taxonomy_subjects = get_taxonomy_subjects(connection)
    active_topic = get_taxonomy_subject_by_slug(connection, topic) if topic else None
    effective_query = q.strip()
    if active_topic and not effective_query:
        effective_query = active_topic["name"]
    elif active_topic and effective_query:
        effective_query = f"{active_topic['name']} {effective_query}"
    results = search_documents(
        connection=connection,
        query=effective_query,
        page=page,
        page_size=settings.search_page_size,
        legal_type=legal_type,
        year=year,
        issuer=issuer,
    )
    results["items"] = enrich_documents_with_provenance(results["items"])
    tracked_ids = get_tracked_document_ids(
        connection,
        [item["id"] for item in results["items"]],
    )
    tracked_documents = aw_list_tracked(user_id)
    recent_documents = get_recent_documents(connection)
    top_legal_types = get_top_legal_types(connection)
    research_views = aw_list_research_views(user_id)
    return templates.TemplateResponse(
        name="index.html",
        request=request,
        context={
            "request": request,
            "stats": stats,
            "filters": options,
            "results": results,
            "query": q,
            "effective_query": effective_query,
            "selected_type": legal_type or "",
            "selected_year": year,
            "selected_issuer": issuer or "",
            "tracked_ids": tracked_ids,
            "tracked_documents": tracked_documents,
            "recent_documents": recent_documents,
            "top_legal_types": top_legal_types,
            "research_views": research_views,
            "taxonomy_subjects": taxonomy_subjects,
            "active_topic": active_topic,
            "dataset_empty": is_empty(connection),
        },
    )


@app.get("/tracking", response_class=HTMLResponse)
def tracking_workbench(request: Request, connection=Depends(get_db)):
    user_id = get_user_id(request)
    aw_tracked = aw_list_tracked(user_id)
    tracked_ids = [t["document_id"] for t in aw_tracked]
    tracked_documents = get_tracked_documents(connection)
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
        for group in relation_graph.get("incoming", []):
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
        if citation_graph.get("incoming_total"):
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
                "incoming_citations": citation_graph.get("incoming_total", 0),
                "outgoing_citations": citation_graph.get("outgoing_total", 0),
                "lifecycle_links": relation_graph.get("total", 0),
                "alerts": document_alerts,
                "same_subject_updates": same_subject_updates,
            }
        )
    SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}
    alerts.sort(
        key=lambda item: (
            SEVERITY_ORDER[item["severity"]],
            item["target"].get("issuance_date") or "",
            item["document"].get("tracked_at") or "",
        ),
        reverse=False,
    )
    dashboard = {
        "tracked_documents": tracked_documents,
        "alerts": alerts,
        "alert_count": len(alerts),
        "dossiers": dossiers,
    }
    research_views = aw_list_research_views(user_id)
    stats = get_stats(connection)
    return templates.TemplateResponse(
        name="tracking.html",
        request=request,
        context={
            "request": request,
            "stats": stats,
            "dashboard": dashboard,
            "research_views": research_views,
        },
    )


@app.get("/documents/{document_id}", response_class=HTMLResponse)
def document_detail(request: Request, document_id: int, connection=Depends(get_db)):
    user_id = get_user_id(request)
    document = get_document(connection, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    related_documents = get_related_documents(connection, document)
    _, outline = prepare_document_markup(document["content"])
    section_citation_counts = get_section_citation_counts(connection, document_id)
    for item in outline:
        item["citation_count"] = section_citation_counts.get(item["anchor"], 0)
    tracked_ids = get_tracked_document_ids(connection, [document_id])
    document_subjects = get_document_subjects(connection, document_id)
    provenance = build_provenance_profile(document)
    relation_graph = get_document_relation_graph(connection, document_id)
    citation_graph = get_document_citation_graph(connection, document_id)
    citation_map = build_citation_map(citation_graph)
    document_html = render_markdown(document["content"])
    document_html_str = inject_document_links(str(document_html), citation_map)
    aw_tracked = aw_list_tracked(user_id)
    aw_tracked_ids = {t["document_id"] for t in aw_tracked}
    return templates.TemplateResponse(
        name="document.html",
        request=request,
        context={
            "request": request,
            "document": document,
            "document_html": Markup(document_html_str),
            "document_outline": outline,
            "document_subjects": document_subjects,
            "provenance": provenance,
            "citation_graph": citation_graph,
            "relation_graph": relation_graph,
            "related_documents": related_documents,
            "is_tracked": document_id in aw_tracked_ids,
        },
    )


@app.get("/compare/{left_document_id}/{right_document_id}", response_class=HTMLResponse)
def compare_documents(
    request: Request,
    left_document_id: int,
    right_document_id: int,
    connection=Depends(get_db),
):
    left_document = get_document(connection, left_document_id)
    right_document = get_document(connection, right_document_id)
    if not left_document or not right_document:
        raise HTTPException(
            status_code=404, detail="One or both documents were not found"
        )

    compare_view = build_compare_view(connection, left_document, right_document)
    return templates.TemplateResponse(
        name="compare.html",
        request=request,
        context={
            "request": request,
            "compare_view": compare_view,
        },
    )


@app.post("/research/views")
def create_research_view_route(
    request: Request,
    name: str = Form(default=""),
    q: str = Form(default=""),
    topic: str = Form(default=""),
    legal_type: str = Form(default=""),
    year: str = Form(default=""),
    issuer: str = Form(default=""),
    connection=Depends(get_db),
):
    user_id = get_user_id(request)
    active_topic = get_taxonomy_subject_by_slug(connection, topic) if topic else None
    resolved_name = name.strip() or build_default_view_name(
        q,
        active_topic["name"] if active_topic else None,
        legal_type,
    )
    year_value = int(year) if year.strip() else None
    view = aw_create_research_view(
        user_id=user_id,
        name=resolved_name,
        query=q,
        topic_slug=topic or "",
        legal_type=legal_type or "",
        year=year_value or 0,
        issuer=issuer or "",
    )
    return RedirectResponse(url=f"/research/views/{view['$id']}", status_code=303)


@app.get("/research/views/{view_id}", response_class=HTMLResponse)
def research_view_detail(
    request: Request,
    view_id: str,
    page: int = 1,
    connection=Depends(get_db),
):
    user_id = get_user_id(request)
    view = aw_get_research_view(user_id, view_id)
    if not view:
        raise HTTPException(status_code=404, detail="Research view not found")

    active_topic = (
        get_taxonomy_subject_by_slug(connection, view.get("topic_slug"))
        if view.get("topic_slug")
        else None
    )
    effective_query = (view.get("query") or "").strip()
    if active_topic and not effective_query:
        effective_query = active_topic["name"]
    elif active_topic and effective_query:
        effective_query = f"{active_topic['name']} {effective_query}"

    results = search_documents(
        connection=connection,
        query=effective_query,
        page=page,
        page_size=settings.search_page_size,
        legal_type=view.get("legal_type"),
        year=view.get("year"),
        issuer=view.get("issuer"),
    )
    results["items"] = enrich_documents_with_provenance(results["items"])
    tracked_ids = get_tracked_document_ids(
        connection, [item["id"] for item in results["items"]]
    )

    return templates.TemplateResponse(
        name="research_view.html",
        request=request,
        context={
            "request": request,
            "view": view,
            "active_topic": active_topic,
            "results": results,
            "tracked_ids": tracked_ids,
            "edit_query_string": build_research_query_string(view),
        },
    )


@app.post("/research/views/{view_id}/delete")
def delete_research_view_route(
    request: Request, view_id: str, connection=Depends(get_db)
):
    user_id = get_user_id(request)
    if not aw_delete_research_view(user_id, view_id):
        raise HTTPException(status_code=404, detail="Research view not found")
    return RedirectResponse(url="/tracking", status_code=303)


@app.get("/api/search")
def api_search(
    q: str = "",
    page: int = 1,
    legal_type: str | None = None,
    year: int | None = None,
    issuer: str | None = None,
    connection=Depends(get_db),
):
    results = search_documents(
        connection=connection,
        query=q,
        page=page,
        page_size=settings.search_page_size,
        legal_type=legal_type,
        year=year,
        issuer=issuer,
    )
    results["items"] = enrich_documents_with_provenance(results["items"])
    return JSONResponse(results)


@app.get("/api/tracked")
def api_tracked(request: Request):
    user_id = get_user_id(request)
    items = aw_list_tracked(user_id)
    return JSONResponse({"items": items})


@app.post("/api/tracked/{document_id}")
def api_track_document(
    request: Request,
    document_id: int,
    payload: TrackRequest,
    connection=Depends(get_db),
):
    user_id = get_user_id(request)
    doc = get_document(connection, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if payload.tracked:
        aw_track_document(
            user_id=user_id,
            document_id=document_id,
            document_title=doc.get("title", ""),
            document_number=doc.get("document_number", ""),
        )
    else:
        aw_untrack_document(user_id, document_id)
    stats = get_stats(connection)
    return JSONResponse(
        {
            "document_id": document_id,
            "tracked": payload.tracked,
            "tracked_count": stats["tracked_count"],
        }
    )


@app.post("/api/ask")
def api_ask(payload: AskRequest, connection=Depends(get_db)):
    passages = retrieve_passages(
        connection=connection,
        query=payload.question,
        limit=settings.answer_passage_limit,
        document_id=payload.document_id,
    )
    brief = build_grounded_brief(payload.question, passages)
    return JSONResponse(brief)


@app.get("/api/citations/{document_id}")
def api_citations(document_id: int, connection=Depends(get_db)):
    if not get_document(connection, document_id):
        raise HTTPException(status_code=404, detail="Document not found")
    return JSONResponse(get_document_citation_graph(connection, document_id))


@app.get("/api/compare/{left_document_id}/{right_document_id}")
def api_compare(
    left_document_id: int,
    right_document_id: int,
    connection=Depends(get_db),
):
    left_document = get_document(connection, left_document_id)
    right_document = get_document(connection, right_document_id)
    if not left_document or not right_document:
        raise HTTPException(
            status_code=404, detail="One or both documents were not found"
        )
    return JSONResponse(build_compare_view(connection, left_document, right_document))


@app.get("/api/relations/{document_id}")
def api_relations(document_id: int, connection=Depends(get_db)):
    if not get_document(connection, document_id):
        raise HTTPException(status_code=404, detail="Document not found")
    return JSONResponse(get_document_relation_graph(connection, document_id))


@app.get("/health")
def health(connection=Depends(get_db)):
    stats = get_stats(connection)
    return {"status": "ok", "documents": stats["document_count"]}


def main() -> None:
    uvicorn.run(
        "vlegal_prototype.app:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        app_dir=str(Path(__file__).resolve().parents[2] / "src"),
    )


if __name__ == "__main__":
    main()
