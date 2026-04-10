from __future__ import annotations

from http.cookies import SimpleCookie
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
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

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
    build_runtime_citation_support,
    get_citation_count,
    get_document_citation_graph,
    get_inline_citation_preview,
    get_section_citation_counts,
    rebuild_citation_index,
)
from .compare import (
    build_compare_focus_preview,
    build_compare_view,
    pick_compare_target,
)
from .db import get_connection, get_stats, initialize_database, is_empty
from .provenance import build_provenance_profile, enrich_documents_with_provenance
from .research import (
    build_default_view_name,
    build_research_query_string,
    create_research_view as create_local_research_view,
    delete_research_view as delete_local_research_view,
    get_research_view as get_local_research_view,
    list_research_views as list_local_research_views,
)
from .relations import (
    get_document_relation_graph,
    get_relation_count,
    rebuild_relationship_graph,
)
from .search import (
    get_documents_by_ids,
    get_document,
    get_filter_options,
    get_recent_documents,
    get_related_documents,
    get_top_legal_types,
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
from .structure import (
    build_document_display_html,
    inject_document_links,
    prepare_document_markup,
)
from .tracking import get_same_subject_updates


USER_ID_COOKIE_NAME = "vlegal_user_id"
USER_ID_COOKIE_MAX_AGE = 60 * 60 * 24 * 365


def build_user_id_cookie_header(user_id: str, *, secure: bool) -> str:
    cookie = SimpleCookie()
    cookie[USER_ID_COOKIE_NAME] = user_id
    morsel = cookie[USER_ID_COOKIE_NAME]
    morsel["httponly"] = True
    morsel["max-age"] = USER_ID_COOKIE_MAX_AGE
    morsel["path"] = "/"
    morsel["samesite"] = "lax"
    if secure:
        morsel["secure"] = True
    return morsel.OutputString()


def resolve_user_id(request: Request) -> str:
    for candidate in (
        request.headers.get("x-user-id", "").strip(),
        request.cookies.get(USER_ID_COOKIE_NAME, "").strip(),
    ):
        if len(candidate) >= 8:
            return candidate
    return os.urandom(16).hex()


def get_user_id(request: Request) -> str:
    user_id = getattr(request.state, "user_id", "")
    if len(user_id) >= 8:
        return user_id
    user_id = resolve_user_id(request)
    request.state.user_id = user_id
    return user_id


class UserIdentityMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        user_id = resolve_user_id(request)
        scope.setdefault("state", {})["user_id"] = user_id
        cookie_changed = request.cookies.get(USER_ID_COOKIE_NAME) != user_id

        async def send_wrapper(message: Message) -> None:
            if cookie_changed and message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.append(
                    "set-cookie",
                    build_user_id_cookie_header(
                        user_id,
                        secure=scope.get("scheme") == "https",
                    ),
                )
            await send(message)

        await self.app(scope, receive, send_wrapper)


settings = get_settings()
app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(UserIdentityMiddleware)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def list_local_tracked_rows(connection) -> list[dict]:
    rows = connection.execute(
        """
        SELECT document_id, tracked_at
        FROM tracked_documents
        ORDER BY tracked_at DESC
        """
    ).fetchall()
    return [
        {
            "id": f"local-{row['document_id']}",
            "$id": f"local-{row['document_id']}",
            "document_id": row["document_id"],
            "tracked_at": row["tracked_at"],
        }
        for row in rows
    ]


def list_user_tracked_rows(connection, user_id: str) -> list[dict]:
    try:
        return aw_list_tracked(user_id)
    except Exception:
        return list_local_tracked_rows(connection)


def get_user_tracked_state(connection, user_id: str) -> dict:
    rows = list_user_tracked_rows(connection, user_id)
    document_ids = [
        int(item["document_id"]) for item in rows if item.get("document_id") is not None
    ]
    documents = get_documents_by_ids(connection, document_ids)
    tracked_meta = {
        int(item["document_id"]): item
        for item in rows
        if item.get("document_id") is not None
    }
    for document in documents:
        tracked_row = tracked_meta.get(document["id"], {})
        if tracked_row.get("tracked_at"):
            document["tracked_at"] = tracked_row["tracked_at"]
    return {
        "rows": rows,
        "ids": set(document_ids),
        "documents": documents,
    }


def track_document_for_user(
    connection,
    user_id: str,
    *,
    document_id: int,
    document_title: str,
    document_number: str,
) -> None:
    try:
        aw_track_document(
            user_id=user_id,
            document_id=document_id,
            document_title=document_title,
            document_number=document_number,
        )
    except Exception:
        set_document_tracking(connection, document_id, True)


def untrack_document_for_user(connection, user_id: str, document_id: int) -> None:
    try:
        aw_untrack_document(user_id, document_id)
    except Exception:
        set_document_tracking(connection, document_id, False)


def normalize_local_research_view(view: dict | None) -> dict | None:
    if not view:
        return None
    normalized = dict(view)
    normalized.setdefault("$id", str(normalized["id"]))
    return normalized


def list_user_research_views(connection, user_id: str) -> list[dict]:
    try:
        return aw_list_research_views(user_id)
    except Exception:
        return [
            normalize_local_research_view(view)
            for view in list_local_research_views(connection)
        ]


def get_user_research_view(connection, user_id: str, view_id: str) -> dict | None:
    try:
        view = aw_get_research_view(user_id, view_id)
        if view:
            return view
    except Exception:
        pass

    try:
        local_view_id = int(view_id)
    except ValueError:
        return None
    return normalize_local_research_view(
        get_local_research_view(connection, local_view_id)
    )


def create_user_research_view(
    connection,
    user_id: str,
    *,
    name: str,
    query: str,
    topic_slug: str,
    legal_type: str,
    year: int,
    issuer: str,
) -> dict:
    try:
        return aw_create_research_view(
            user_id=user_id,
            name=name,
            query=query,
            topic_slug=topic_slug,
            legal_type=legal_type,
            year=year,
            issuer=issuer,
        )
    except Exception:
        view_id = create_local_research_view(
            connection,
            name=name,
            query=query,
            topic_slug=topic_slug,
            legal_type=legal_type,
            year=year or None,
            issuer=issuer,
        )
        return normalize_local_research_view(
            get_local_research_view(connection, view_id)
        )


def delete_user_research_view(connection, user_id: str, view_id: str) -> bool:
    try:
        if aw_delete_research_view(user_id, view_id):
            return True
    except Exception:
        pass

    try:
        local_view_id = int(view_id)
    except ValueError:
        return False
    if not get_local_research_view(connection, local_view_id):
        return False
    delete_local_research_view(connection, local_view_id)
    return True


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
    year: str = "",
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
    try:
        selected_year_value = int(year.strip()) if year.strip() else None
    except ValueError:
        selected_year_value = None
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
        year=selected_year_value,
        issuer=issuer,
    )
    results["items"] = enrich_documents_with_provenance(results["items"])
    tracked_state = get_user_tracked_state(connection, user_id)
    recent_documents = get_recent_documents(connection)
    top_legal_types = get_top_legal_types(connection)
    research_views = list_user_research_views(connection, user_id)
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
            "selected_year": selected_year_value,
            "selected_issuer": issuer or "",
            "tracked_ids": tracked_state["ids"],
            "tracked_documents": tracked_state["documents"],
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
    tracked_state = get_user_tracked_state(connection, user_id)
    aw_tracked = tracked_state["rows"]
    tracked_documents = tracked_state["documents"]
    tracked_meta = {
        int(item["document_id"]): item
        for item in aw_tracked
        if item.get("document_id") is not None
    }
    alerts: list[dict] = []
    dossiers: list[dict] = []
    for document in tracked_documents:
        tracked_row = tracked_meta.get(document["id"], {})
        if tracked_row.get("tracked_at"):
            document["tracked_at"] = tracked_row["tracked_at"]
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
    research_views = list_user_research_views(connection, user_id)
    stats = {
        **get_stats(connection),
        "tracked_count": len(aw_tracked),
        "research_view_count": len(research_views),
    }
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
    runtime_citation_support = build_runtime_citation_support(connection, document)
    for anchor, total in runtime_citation_support["section_counts"].items():
        section_citation_counts[anchor] = max(
            section_citation_counts.get(anchor, 0), total
        )
    section_citation_labels: dict[str, int] = {}
    for item in outline:
        runtime_count = runtime_citation_support["section_counts"].get(
            item["anchor"], 0
        )
        item["citation_count"] = max(
            section_citation_counts.get(item["anchor"], 0), runtime_count
        )
        if item["citation_count"]:
            section_citation_labels[item["heading"]] = (
                section_citation_labels.get(item["heading"], 0) + item["citation_count"]
            )
    document_subjects = get_document_subjects(connection, document_id)
    provenance = build_provenance_profile(document)
    relation_graph = get_document_relation_graph(connection, document_id)
    citation_graph = get_document_citation_graph(connection, document_id)
    citation_map = build_citation_map(citation_graph)
    citation_map = {**citation_map, **runtime_citation_support["citation_map"]}
    for label, total in runtime_citation_support["section_labels"].items():
        section_citation_labels[label] = max(
            section_citation_labels.get(label, 0), total
        )
    document_display_html = build_document_display_html(
        document["content"],
        citation_map,
        section_citation_counts,
        section_citation_labels,
    )
    if document_display_html is None:
        document_html = render_markdown(document["content"])
        document_display_html = inject_document_links(str(document_html), citation_map)
    compare_target = pick_compare_target(
        relation_graph=relation_graph,
        citation_graph=citation_graph,
        related_documents=related_documents,
    )
    tracked_state = get_user_tracked_state(connection, user_id)
    return templates.TemplateResponse(
        name="document.html",
        request=request,
        context={
            "request": request,
            "document": document,
            "document_display_html": Markup(document_display_html),
            "document_outline": outline,
            "document_subjects": document_subjects,
            "provenance": provenance,
            "citation_graph": citation_graph,
            "relation_graph": relation_graph,
            "related_documents": related_documents,
            "compare_target": compare_target,
            "is_tracked": document_id in tracked_state["ids"],
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
    view = create_user_research_view(
        connection,
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
    view = get_user_research_view(connection, user_id, view_id)
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
    tracked_ids = get_user_tracked_state(connection, user_id)["ids"]

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
    if not delete_user_research_view(connection, user_id, view_id):
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
def api_tracked(request: Request, connection=Depends(get_db)):
    user_id = get_user_id(request)
    items = list_user_tracked_rows(connection, user_id)
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
        track_document_for_user(
            connection,
            user_id=user_id,
            document_id=document_id,
            document_title=doc.get("title", ""),
            document_number=doc.get("document_number", ""),
        )
    else:
        untrack_document_for_user(connection, user_id, document_id)
    tracked_count = len(list_user_tracked_rows(connection, user_id))
    return JSONResponse(
        {
            "document_id": document_id,
            "tracked": payload.tracked,
            "tracked_count": tracked_count,
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


@app.get("/api/citation-preview/{source_document_id}/{target_document_id}")
def api_citation_preview(
    source_document_id: int,
    target_document_id: int,
    source_anchor: str | None = None,
    raw_reference: str | None = None,
    connection=Depends(get_db),
):
    source_document = get_document(connection, source_document_id)
    target_document = get_document(connection, target_document_id)
    if not source_document or not target_document:
        raise HTTPException(status_code=404, detail="Document not found")

    preview = get_inline_citation_preview(
        connection,
        source_document_id=source_document_id,
        target_document_id=target_document_id,
        source_anchor=source_anchor,
        raw_reference=raw_reference,
    )
    if not preview:
        raise HTTPException(status_code=404, detail="Citation preview not found")

    preview["target_document"]["provenance"] = build_provenance_profile(target_document)
    preview["target_document"]["compare_path"] = (
        f"/compare/{source_document_id}/{target_document_id}"
        if source_document_id != target_document_id
        else None
    )
    preview["target_document"]["reader_path"] = f"/documents/{target_document_id}"

    target_relation_graph = get_document_relation_graph(connection, target_document_id)
    target_citation_graph = get_document_citation_graph(connection, target_document_id)
    target_related_documents = get_related_documents(connection, target_document)
    compare_target = pick_compare_target(
        relation_graph=target_relation_graph,
        citation_graph=target_citation_graph,
        related_documents=target_related_documents,
    )
    if compare_target:
        compare_document = get_document(connection, compare_target["id"])
        if compare_document:
            preview["target_document"]["compare_preview"] = build_compare_focus_preview(
                connection,
                left_document=target_document,
                right_document=compare_document,
                focus_left_anchor=(preview.get("target_section") or {}).get("anchor"),
            )
    return JSONResponse(preview)


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


@app.api_route("/favicon.ico", methods=["GET", "HEAD"], include_in_schema=False)
def favicon() -> RedirectResponse:
    return RedirectResponse(url="/static/favicon.svg", status_code=307)


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
