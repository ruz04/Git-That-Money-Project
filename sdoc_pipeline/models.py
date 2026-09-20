"""
models.py
Shared constants and data shapes, matching the REAL SDOC schema from
data_v2/ and scoring.py — not the earlier toy-brief version. No logic lives
here on purpose; every other file imports from this one so the schema is
defined in exactly one place.
"""

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# The 5 email categories (scoring.py: CATEGORIES). Order doesn't matter here,
# it's just the closed set the classifier must pick from.
# ---------------------------------------------------------------------------
CATEGORIES = ["BL_COMPARISON", "SI_REQUEST", "INVOICE_QUERY", "GENERAL", "SPAM"]

# The 3 possible outcomes for an email's document-comparison status.
STATUSES = ["OK", "MISMATCH", "NEEDS_REVIEW"]

# The closed set of reasons a case gets escalated to NEEDS_REVIEW
# (edgecases.py / data_v2 README). Nothing outside this set should ever be
# written to review_reason — the scorer's reliability axis checks against it.
REVIEW_REASONS = ["wrong_doc_type", "missing_attachment", "unreadable", "missing_value"]

# The 7 fields every SI/BL comparison checks (pools.py: COMPARE_FIELDS).
COMPARE_FIELDS = [
    "shipper",
    "consignee",
    "notify_party",
    "port_of_loading",
    "port_of_discharge",
    "container_count",
    "gross_weight_kg",
]

# Tokens the real data uses to mark a field as deliberately left blank
# (edgecases.py: BLANK_TOKENS). The extractor must recognise these as
# "missing", never as a literal value to compare — a blank is uncertainty,
# not a discrepancy (data_v2 README, "missing_value" section).
MISSING_VALUE_TOKENS = {"???", "_______", "TBA", "TBC", "", "N/A", "____MT"}


@dataclass
class ClassificationResult:
    """Output of the classifier for one email."""
    category: str                  # one of CATEGORIES
    confidence: float              # 0-1, model's self-reported confidence
    urgency: str = "routine"       # bonus, non-scored: "routine" | "urgent"
    reason: str = ""               # short justification, useful for debugging


@dataclass
class ExtractedFields:
    """Normalized field values pulled out of ONE document (either the SI or
    the BL). The extractor is called twice per comparison email."""
    shipper: Optional[str] = None
    consignee: Optional[str] = None
    notify_party: Optional[str] = None
    port_of_loading: Optional[str] = None
    port_of_discharge: Optional[str] = None
    container_count: Optional[str] = None
    gross_weight_kg: Optional[str] = None

    # Fields that were genuinely blank/unreadable in this document -- these
    # must NOT be silently treated as matching or as a mismatch.
    missing_fields: list = field(default_factory=list)

    # Document-type sanity check -- catches the "wrong_doc_type" edge case
    # (a Commercial Invoice / Packing List / Certificate of Origin sent
    # where an SI or BL was expected).
    looks_like_target_doc: bool = True
    detected_doc_type: str = ""    # e.g. "commercial invoice", "packing list"

    def get(self, name: str):
        return getattr(self, name, None)


@dataclass
class FieldMismatch:
    field: str
    si_value: Optional[str]
    bl_value: Optional[str]


@dataclass
class SubmissionEntry:
    """One email's final result, shaped EXACTLY like the required submission
    JSON (server/app.py POST /submit, data_v2 README). This is what gets
    serialized per email_id in submission.json."""
    category: str
    status: str                        # OK | MISMATCH | NEEDS_REVIEW
    review_reason: Optional[str] = None
    has_defect: bool = False
    defect_fields: list = field(default_factory=list)
    urgency: str = "routine"           # bonus field; scorer ignores unknown keys

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "status": self.status,
            "review_reason": self.review_reason,
            "has_defect": self.has_defect,
            "defect_fields": sorted(self.defect_fields),
            "urgency": self.urgency,
        }
