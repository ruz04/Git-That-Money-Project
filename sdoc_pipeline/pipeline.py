"""
pipeline.py
Wires every stage together and decides, for each BL_COMPARISON email, which
of the 4 review_reasons applies (if any) before ever reaching the comparator.

Decision order for a BL_COMPARISON email (checked in this priority, matching
how edgecases.py actually builds the 20 test cases -- each edge case has
exactly ONE thing wrong with it, so ties shouldn't occur in practice, but the
order below is the sane precedence if they ever did):

    1. missing_attachment  -- can't even find both an SI and a BL file
    2. unreadable           -- a file exists but couldn't be turned into text
    3. wrong_doc_type        -- readable, but isn't actually an SI/BL
    4. missing_value           -- both docs read fine, but a field is blank
    5. (else) compare normally -> OK or MISMATCH
"""

from pathlib import Path

from classifier import EmailClassifier
from extractor import FieldExtractor
from comparator import DocumentComparator
from reporter import ReportBuilder

# Confidence below this -> treat like any other genuinely uncertain case.
# (Classification confidence doesn't map to a review_reason -- the 4 reasons
# are specifically about document comparison -- so a low-confidence
# classification is just logged, not escalated. Kept here for visibility.)
CONFIDENCE_LOG_THRESHOLD = 0.6

# Markers the extractor uses internally when a document literally could not
# be turned into usable text (empty file, extraction call itself failed).
# Anything else in detected_doc_type when looks_like_target_doc is False
# means "this IS readable, it's just the wrong kind of document" -> wrong_doc_type.
_UNREADABLE_MARKERS = {"unreadable or empty", "extraction failed"}

# Extensions this build can actually turn into text. pdf/docx/xlsx parsing
# is added on top of this file in a later pass -- until then, those
# attachments correctly fall into "unreadable" rather than being silently
# skipped or mis-extracted.
_SUPPORTED_TEXT_EXTENSIONS = {".txt"}


class ShippingVerificationPipeline:
    def __init__(self, client, inbox):
        """
        client: anthropic.Anthropic() instance
        inbox:  the Inbox object from the organizers' loader.py
        """
        self.inbox = inbox
        self.classifier = EmailClassifier(client)
        self.extractor = FieldExtractor(client)
        self.comparator = DocumentComparator()
        self.reporter = ReportBuilder()

    def run(self) -> dict:
        """Returns {email_id: submission_dict, ...} ready to write to
        submission.json or pass to inbox.submit(...)."""
        results = {}
        for email in self.inbox:
            eid = email["email_id"]
            try:
                entry = self._process_one(email)
            except Exception as exc:  # noqa: BLE001 -- last-resort safety net
                # Never let one bad email crash the whole batch. Escalate the
                # safest way we can given we don't even know what broke.
                entry = self.reporter.escalate("unreadable")
                print(f"[pipeline] {eid}: unhandled error, escalated as "
                      f"unreadable -- {exc!r}")
            results[eid] = entry.to_dict()
        return results

    def _process_one(self, email: dict):
        classification = self.classifier.classify(email)

        if classification.category != "BL_COMPARISON":
            return self.reporter.non_comparison(classification.category,
                                                 classification.urgency)

        return self._process_comparison(email, classification.urgency)

    def _process_comparison(self, email: dict, urgency: str):
        attachments = email.get("attachments", [])
        si_path, bl_path = _find_si_bl(attachments)

        # 1. missing_attachment -- can't find both files by name pattern
        if si_path is None or bl_path is None:
            return self.reporter.escalate("missing_attachment", urgency)

        # 2. unreadable -- read + extract each document
        si_text = self._read_document_text(si_path)
        bl_text = self._read_document_text(bl_path)
        si_fields = self.extractor.extract(si_text)
        bl_fields = self.extractor.extract(bl_text)

        if (si_fields.detected_doc_type in _UNREADABLE_MARKERS
                or bl_fields.detected_doc_type in _UNREADABLE_MARKERS):
            return self.reporter.escalate("unreadable", urgency)

        # 3. wrong_doc_type -- readable, but not actually an SI/BL
        if not si_fields.looks_like_target_doc or not bl_fields.looks_like_target_doc:
            return self.reporter.escalate("wrong_doc_type", urgency)

        # 4. missing_value / normal compare
        mismatches, unresolved = self.comparator.compare(si_fields, bl_fields)
        if unresolved:
            return self.reporter.escalate("missing_value", urgency)

        return self.reporter.ok_or_mismatch(mismatches, urgency)

    def _read_document_text(self, path: str) -> str:
        """Read one attachment's text. Returns "" for anything we can't
        (yet) turn into text -- the extractor treats an empty string as
        unreadable, so this naturally routes into the right review_reason
        without pipeline.py needing its own try/except for format errors."""
        ext = Path(path).suffix.lower()
        if ext not in _SUPPORTED_TEXT_EXTENSIONS:
            # TODO(step 10): add pdf/docx/xlsx -> text parsing here. Until
            # then these attachments are correctly treated as unreadable
            # rather than silently mis-extracted.
            return ""
        try:
            return self.inbox.read_text(path)
        except Exception:
            return ""


def _find_si_bl(attachments):
    """Match attachment paths to SI/BL by filename pattern -- real filenames
    are 'attachments/email_XXX_SI.<ext>' / '..._BL.<ext>' (generate.py),
    consistently, across every format. Returns (si_path, bl_path); either
    can be None if not found."""
    si_path = bl_path = None
    for att in attachments:
        name = str(att)
        if "_SI." in name or "_SI_" in name:
            si_path = att
        elif "_BL." in name or "_BL_" in name:
            bl_path = att
    return si_path, bl_path
