from __future__ import annotations

from urllib.parse import quote_plus

from .taxonomy import normalize_ascii


VBPL_SEARCH_BASE = "https://vbpl.vn/pages/vbpq-timkiem.aspx"
VBPL_ADVANCED_SEARCH_URL = "https://vbpl.vn/Pages/timkiem-nangcao.aspx"
VBPL_PORTAL_URL = "https://vbpl.vn/pages/portal.aspx"

VNCP_SEARCH_URL = "https://vanban.chinhphu.vn/?pageid=473"
VNCP_PORTAL_URL = "https://vanban.chinhphu.vn/"


HIGH_VALUE_TYPES = {
    "luat",
    "nghi dinh",
    "thong tu",
    "nghi quyet",
    "quyet dinh",
    "chi thi",
    "lenh",
    "van ban hop nhat",
}

MEDIUM_VALUE_TYPES = {
    "cong van",
    "ke hoach",
    "huong dan",
    "thong bao",
}

CENTRAL_ISSUER_KEYWORDS = (
    "chinh phu",
    "thu tuong chinh phu",
    "van phong chinh phu",
    "quoc hoi",
    "uy ban thuong vu quoc hoi",
    "chu tich nuoc",
    "ngan hang nha nuoc",
    "hoi dong bau cu quoc gia",
    "toa an nhan dan toi cao",
    "vien kiem sat nhan dan toi cao",
    "bo ",
    "bo,",
    "bo quoc phong",
    "bo tu phap",
    "bo tai chinh",
    "bo cong an",
    "bo nong nghiep",
    "bo giao duc",
)

LOCAL_ISSUER_KEYWORDS = (
    "uy ban nhan dan",
    "ubnd",
    "tinh ",
    "thanh pho ",
    "phuong ",
    "xa ",
    "quan ",
    "huyen ",
    "dac khu",
)


def normalize_type(value: str | None) -> str:
    return normalize_ascii(value or "")


def classify_document_family(legal_type: str | None) -> str:
    normalized = normalize_type(legal_type)
    if normalized in HIGH_VALUE_TYPES:
        return "normative"
    if normalized in MEDIUM_VALUE_TYPES:
        return "administrative"
    return "general"


def classify_issuer_scope(issuer: str | None) -> str:
    normalized = normalize_ascii(issuer or "")
    if not normalized:
        return "unknown"
    if any(keyword in normalized for keyword in LOCAL_ISSUER_KEYWORDS):
        return "local"
    if any(keyword in normalized for keyword in CENTRAL_ISSUER_KEYWORDS):
        return "central"
    return "unknown"


def build_query_value(document: dict) -> str:
    document_number = (document.get("document_number") or "").strip()
    title = (document.get("title") or "").strip()
    if document_number and len(document_number) <= 60:
        return document_number
    return title


def build_vbpl_search_url(document: dict, exact_phrase: bool = True) -> str:
    query = quote_plus(build_query_value(document))
    s_value = "1" if exact_phrase else "0"
    return (
        f"{VBPL_SEARCH_BASE}?type=0&s={s_value}&SearchIn=Title,Title1&Keyword={query}"
    )


def build_vncp_search_url(document: dict) -> str:
    query = quote_plus(build_query_value(document))
    return f"{VNCP_SEARCH_URL}&q={query}"


def should_offer_vncp(document: dict) -> bool:
    issuer_scope = classify_issuer_scope(document.get("issuing_authority"))
    legal_type = normalize_type(document.get("legal_type"))
    document_number = normalize_ascii(document.get("document_number") or "")

    if issuer_scope == "central":
        return True
    if legal_type in {"nghi dinh", "chi thi", "quyet dinh", "nghi quyet"} and (
        "ttg" in document_number or "cp" in document_number
    ):
        return True
    return False


def build_provenance_profile(document: dict) -> dict:
    issuer_scope = classify_issuer_scope(document.get("issuing_authority"))
    document_family = classify_document_family(document.get("legal_type"))

    routes = [
        {
            "id": "vbpl",
            "label": "Search on VBPL",
            "short_label": "VBPL",
            "url": build_vbpl_search_url(document, exact_phrase=True),
            "fallback_url": VBPL_ADVANCED_SEARCH_URL,
            "confidence": "high" if document_family == "normative" else "medium",
            "note": "Best official legal database route for Vietnamese legal text lookup.",
        }
    ]

    if should_offer_vncp(document):
        routes.append(
            {
                "id": "vncp",
                "label": "Search on Government Portal",
                "short_label": "VNCP",
                "url": build_vncp_search_url(document),
                "fallback_url": VNCP_SEARCH_URL,
                "confidence": "high" if issuer_scope == "central" else "medium",
                "note": "Strong official route for central-government texts and related publications.",
            }
        )

    if issuer_scope == "central":
        scope_label = "Central issuer"
    elif issuer_scope == "local":
        scope_label = "Local issuer"
    else:
        scope_label = "Issuer scope unknown"

    if document_family == "normative":
        family_label = "Normative act"
        headline = "Strong official lookup routes available"
    elif document_family == "administrative":
        family_label = "Administrative / guidance record"
        headline = "Official search routes available"
    else:
        family_label = "General legal record"
        headline = "Official search fallbacks available"

    summary = (
        f"This record is classified as {family_label.lower()} with {scope_label.lower()}. "
        "Use the routes below to cross-check the bootstrap corpus against official Vietnamese public sources."
    )

    return {
        "headline": headline,
        "summary": summary,
        "scope_label": scope_label,
        "family_label": family_label,
        "routes": routes,
        "corpus_source": {
            "label": "Bootstrap corpus source",
            "short_label": "HF/TVPL",
            "url": document.get("url") or VBPL_PORTAL_URL,
        },
    }


def enrich_documents_with_provenance(documents: list[dict]) -> list[dict]:
    enriched: list[dict] = []
    for document in documents:
        item = dict(document)
        item["provenance"] = build_provenance_profile(item)
        enriched.append(item)
    return enriched
