"""
reporter.py
Stage 4: turn classification + extraction + comparison results into a
SubmissionEntry -- the exact shape score_cli.py / POST /submit expects.

Three entry points, one per situation an email can end in:
  non_comparison()      -- SI_REQUEST / INVOICE_QUERY / GENERAL / SPAM
  escalate()             -- BL_COMPARISON that can't be decided confidently
  ok_or_mismatch()         -- BL_COMPARISON that compared cleanly
"""

from models import SubmissionEntry


class ReportBuilder:
    def non_comparison(self, category: str, urgency: str = "routine") -> SubmissionEntry:
        """Every non-BL_COMPARISON category is always status OK with no
        defects -- confirmed by the real ground_truth.json (SI_REQUEST,
        INVOICE_QUERY, GENERAL, SPAM entries are all status: OK)."""
        return SubmissionEntry(
            category=category,
            status="OK",
            review_reason=None,
            has_defect=False,
            defect_fields=[],
            urgency=urgency,
        )

    def escalate(self, review_reason: str, urgency: str = "routine") -> SubmissionEntry:
        """A BL_COMPARISON email that cannot be confidently compared.
        has_defect/defect_fields stay empty -- NEEDS_REVIEW is orthogonal to
        MISMATCH, per the data_v2 README: a blank/unreadable/wrong document
        is uncertainty, not a discrepancy."""
        return SubmissionEntry(
            category="BL_COMPARISON",
            status="NEEDS_REVIEW",
            review_reason=review_reason,
            has_defect=False,
            defect_fields=[],
            urgency=urgency,
        )

    def ok_or_mismatch(self, mismatches, urgency: str = "routine") -> SubmissionEntry:
        """A BL_COMPARISON email that compared cleanly -- either every field
        matched (OK) or one or more genuinely differ (MISMATCH)."""
        if not mismatches:
            return SubmissionEntry(
                category="BL_COMPARISON",
                status="OK",
                review_reason=None,
                has_defect=False,
                defect_fields=[],
                urgency=urgency,
            )
        return SubmissionEntry(
            category="BL_COMPARISON",
            status="MISMATCH",
            review_reason=None,
            has_defect=True,
            defect_fields=sorted(m.field for m in mismatches),
            urgency=urgency,
        )
