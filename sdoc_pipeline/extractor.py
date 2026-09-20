"""
extractor.py
Stage 2: pull the 7 comparison fields out of ONE document's raw text
(either the SI or the BL). Called twice per comparison email.

STAGE NOTE: this version handles plain-text attachments only (per our build
order -- pdf/docx/xlsx parsing is added on top of this file later, once the
plain-text path is scoring well via score_cli.py). Whatever future module
reads a pdf/docx/xlsx into text should hand that text to extract() unchanged
-- nothing in this file needs to know the source format.
"""

import json
from models import ExtractedFields, COMPARE_FIELDS, MISSING_VALUE_TOKENS

# Grounded in the real label synonyms from pools.py's LABELS table -- the SI
# and BL deliberately use DIFFERENT headers for the same field, e.g. the
# actual email_001 sample has "Port of Loading (POL)" on the BL and
# "Port of Loading" on the SI, "Notify:" vs "NOTIFY PARTY:", etc.
EXTRACTOR_SYSTEM_PROMPT = f"""You extract shipment fields from ONE shipping
document (either a Shipping Instruction or a draft Bill of Lading). Text may
come from a .txt file, or from a PDF/Word/Excel conversion, so formatting can
be uneven -- tables may be flattened, spacing irregular.

Extract exactly these fields: {COMPARE_FIELDS}

Field-by-field notes:
- shipper, consignee, notify_party: the party name only, trimmed. These
  fields go by different labels across documents -- treat these as the SAME
  field regardless of header: "Shipper" / "Shipper/Exporter" / "SHIPPER";
  "Consignee" / "CONSIGNEE" / "To the Order of"; "Notify Party" / "Notify" /
  "NOTIFY PARTY".
- port_of_loading / port_of_discharge: also multi-labelled -- "Port of
  Loading" = "Port of Loading (POL)" = "Load Port" = "POL"; "Port of
  Discharge" = "Discharge Port" = "POD". Return the port name (with country
  if given), drop the parenthetical UN/LOCODE, e.g. "PORT KLANG (WESTPORT),
  MALAYSIA (MYPKG)" -> "PORT KLANG (WESTPORT), MALAYSIA".
- container_count: the field is often rendered as "<count> x <size>", e.g.
  "1 x 40'HC" or "3 x 20'FCL". Extract ONLY the numeric count ("1", "3") --
  ignore the container size/type that follows the "x". Do not confuse this
  with a container NUMBER (like "ABCD1234567").
- gross_weight_kg: strip thousands separators and the "KG" unit, return a
  bare numeric string, e.g. "21,577 KG" -> "21577".

MISSING VALUES -- read carefully: some real documents deliberately leave a
field blank, shown as one of: {sorted(MISSING_VALUE_TOKENS - {""})} or an
empty/dash value. When a field's value is one of these tokens (or clearly a
placeholder, not real data), you MUST treat it as MISSING -- set it to null
and add its name to missing_fields. NEVER report a blank-token value as if it
were a real value, and never guess what it "should" be.

DOCUMENT TYPE CHECK -- some attachments are not actually an SI or BL at all
(a Commercial Invoice, Packing List, or Certificate of Origin sent by
mistake). Look at the document's own heading/structure: if it clearly is NOT
a shipping instruction or bill of lading, set looks_like_target_doc to false
and detected_doc_type to what it actually is (e.g. "commercial invoice",
"packing list", "certificate of origin"). If it IS an SI or BL (even if
labelled "DRAFT" or informally), looks_like_target_doc is true.

If a genuinely required field cannot be found anywhere in the text (not a
blank-token, just absent), also set it to null and list it in missing_fields.
Do not invent or infer a value that isn't actually present.

Respond with ONLY a JSON object, no other text, no markdown fences, in this
exact shape:
{{
  "shipper": "<string or null>",
  "consignee": "<string or null>",
  "notify_party": "<string or null>",
  "port_of_loading": "<string or null>",
  "port_of_discharge": "<string or null>",
  "container_count": "<string or null>",
  "gross_weight_kg": "<string or null>",
  "missing_fields": ["<field names that are null due to a blank/absent value>"],
  "looks_like_target_doc": true or false,
  "detected_doc_type": "<what the document actually is, only if looks_like_target_doc is false, else empty string>"
}}
"""


class FieldExtractor:
    def __init__(self, client, model="claude-sonnet-4-6"):
        self.client = client
        self.model = model

    def extract(self, document_text: str) -> ExtractedFields:
        # An empty or near-empty string means the document was unreadable
        # upstream (empty file, garbled PDF with no text layer, etc.) --
        # don't even spend an API call guessing at nothing.
        if not document_text or not document_text.strip():
            return ExtractedFields(
                missing_fields=list(COMPARE_FIELDS),
                looks_like_target_doc=False,
                detected_doc_type="unreadable or empty",
            )

        response = self.client.messages.create(
            model=self.model,
            max_tokens=600,
            system=EXTRACTOR_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": document_text}],
        )

        raw_text = "".join(
            block.text for block in response.content if getattr(block, "type", "") == "text"
        )

        try:
            parsed = json.loads(_strip_fences(raw_text))
        except json.JSONDecodeError:
            # Extraction totally failed to parse -- treat as unreadable
            # rather than comparing garbage.
            return ExtractedFields(
                missing_fields=list(COMPARE_FIELDS),
                looks_like_target_doc=False,
                detected_doc_type="extraction failed",
            )

        fields = {}
        for name in COMPARE_FIELDS:
            value = parsed.get(name)
            # Belt-and-suspenders: even if the model returned a literal blank
            # token instead of null, catch it here too.
            if isinstance(value, str) and value.strip() in MISSING_VALUE_TOKENS:
                value = None
            fields[name] = value

        missing = [f for f in parsed.get("missing_fields", []) or [] if f in COMPARE_FIELDS]
        # Make sure anything we nulled out above is also listed as missing,
        # even if the model forgot to add it to missing_fields itself.
        for name, value in fields.items():
            if value is None and name not in missing:
                missing.append(name)

        return ExtractedFields(
            **fields,
            missing_fields=missing,
            looks_like_target_doc=bool(parsed.get("looks_like_target_doc", True)),
            detected_doc_type=parsed.get("detected_doc_type", "") or "",
        )


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    return text.strip()
