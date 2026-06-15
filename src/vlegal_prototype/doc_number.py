"""Shared Vietnamese legal document-number patterns.

Two modules detect document numbers from different input domains:

- ``relations``/``citations`` run on diacritic-stripped, lowercased ASCII text
  (via ``normalize_ascii``), so their alphabet is ``a-z``.
- ``structure`` runs on raw rendered HTML that still contains Vietnamese
  diacritics, so its alphabet must include the full ``\\u00c0-\\u1ef9`` range.

Previously each module hand-rolled its own regex, and they drifted (e.g. the
standalone pattern allowed unbounded leading digits in one place and capped at
four in the other). When the two disagree, a reference can be counted as a
citation badge but not turned into a clickable link, or vice versa.

This module builds both the ASCII and Unicode variants from one template so the
structural rules stay identical; only the alphabet differs.
"""

from __future__ import annotations

import re

_ASCII_ALPHA = "a-zA-Z"
_UNICODE_ALPHA = "A-Za-z\u00c0-\u1ef9"

# Legal-type prefixes used by the contextual pattern, by input domain.
_ASCII_LEGAL_TYPES = (
    "bo luat|luat|phap lenh|sac lenh|lenh|nghi quyet|nghi dinh|"
    "quyet dinh|chi thi|thong tu lien tich|thong tu"
)
_UNICODE_LEGAL_TYPES = (
    "Sắc lệnh|Pháp lệnh|Nghị định|Nghị quyết|Quyết định|Chỉ thị|"
    "Thông tư(?: liên tịch)?|Lệnh|Luật|Bộ luật"
)


def _standalone_pattern(alpha: str) -> str:
    """A bare document number such as ``150/2025/QH15`` or ``91-SL``.

    Shape: 1-4 digits (optional trailing letter), an optional ``/year`` group,
    then one or more ``/segment`` groups where each segment contains at least
    one letter (so plain ``1/2`` ratios are not matched).
    """
    alnum = f"0-9{alpha}"
    return (
        rf"\b([0-9]{{1,4}}[{alpha}]?"
        rf"(?:[/-][0-9]{{2,4}})?"
        rf"(?:[/-][{alnum}]*[{alpha}][{alnum}]*)+)\b"
    )


def _contextual_pattern(alpha: str, legal_types: str, *, capture_type: bool) -> str:
    """A legal-type-led reference such as ``Luật số 22/2012/QH13``.

    The number group is intentionally looser than the standalone pattern because
    the legal-type prefix already anchors the match.

    ``capture_type`` controls whether the legal-type prefix is a capturing group.
    The ASCII consumer (``relations``) reads the type from group(1) and the
    number from group(2); the Unicode consumer (``structure``) only needs the
    number in group(1). Keeping these contracts avoids reworking either caller.
    """
    alnum = f"0-9{alpha}"
    type_group = f"({legal_types})" if capture_type else f"(?:{legal_types})"
    return (
        rf"\b{type_group}\s*(?:s[oố]\s*[:.]?\s*)?"
        rf"([0-9]{{1,4}}(?:[/-][0-9]{{2,4}})?(?:[/-][{alnum}\-]+)?)\b"
    )


# ASCII variants (normalized text): used by relations.py / citations.py.
# Contextual keeps two capture groups: (1) legal type, (2) number.
DOC_NUMBER_PATTERN = re.compile(_standalone_pattern(_ASCII_ALPHA))
CONTEXTUAL_DOC_REFERENCE_PATTERN = re.compile(
    _contextual_pattern(_ASCII_ALPHA, _ASCII_LEGAL_TYPES, capture_type=True)
)

# Unicode variants (raw text with diacritics): used by structure.py.
# Contextual keeps a single capture group: (1) number.
DOC_NUMBER_PATTERN_UNICODE = re.compile(_standalone_pattern(_UNICODE_ALPHA))
CONTEXTUAL_DOC_REFERENCE_PATTERN_UNICODE = re.compile(
    _contextual_pattern(_UNICODE_ALPHA, _UNICODE_LEGAL_TYPES, capture_type=False),
    re.IGNORECASE,
)
