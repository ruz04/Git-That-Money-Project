"""
comparator.py
Stage 3: compare an SI's extracted fields against a BL's extracted fields.

Deliberately plain Python, no LLM call -- the diff itself must be
deterministic and exactly reproducible, since scoring.py's end_to_end metric
requires an EXACT set match on defect_fields (no partial credit). Save the
model for the fuzzy parts (classifying, extracting); this part stays boring
and reliable on purpose.
"""

from models import ExtractedFields, FieldMismatch, COMPARE_FIELDS


class DocumentComparator:
    def compare(self, si: ExtractedFields, bl: ExtractedFields):
        """
        Returns (mismatches: list[FieldMismatch], unresolved_fields: list[str])

        unresolved_fields = fields that could NOT be compared because one or
        both sides are missing (a blank-token field, or an entirely absent
        field). Per the data_v2 README, "a blank field ... is not a mismatch
        -- the system genuinely cannot decide." These must route to
        NEEDS_REVIEW / missing_value downstream, never be silently treated
        as matching OR as a defect.
        """
        mismatches = []
        unresolved = []

        for f in COMPARE_FIELDS:
            si_val = si.get(f)
            bl_val = bl.get(f)

            if si_val is None or bl_val is None:
                unresolved.append(f)
                continue

            if not _values_match(f, si_val, bl_val):
                mismatches.append(FieldMismatch(field=f, si_value=si_val, bl_value=bl_val))

        return mismatches, sorted(unresolved)


def _values_match(field_name: str, a: str, b: str) -> bool:
    a_norm = _normalize(a)
    b_norm = _normalize(b)

    if field_name in ("container_count", "gross_weight_kg"):
        # Numeric compare so "22000" == "22,000" == "22000.0" and small
        # formatting differences never cause a false mismatch.
        a_num = _to_number(a_norm)
        b_num = _to_number(b_norm)
        if a_num is not None and b_num is not None:
            return a_num == b_num
        return a_norm == b_norm

    # Text fields: case-insensitive, whitespace/punctuation-tolerant compare.
    # Real values are compared as extracted -- the SI/BL do sometimes include
    # slightly different address-line detail after the party name, but the
    # extractor is instructed to return only the party name itself, so this
    # stays a straightforward equality check.
    return a_norm == b_norm


def _normalize(value: str) -> str:
    return " ".join(str(value).strip().lower().replace(",", "").split())


def _to_number(value: str):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
