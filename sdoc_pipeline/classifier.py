"""
classifier.py
Stage 1: one email in, one category out of the 5 real SDOC categories.

Classification is based ONLY on the email's own subject/body/sender --
never on whether attachments are present. This matters: ~45% of real
BL_COMPARISON emails have no attachments yet (they're "please send the
draft BL" requests, per generate.py's BL_WITH_ATTACH split), and they are
still BL_COMPARISON. Attachment handling is a downstream concern.
"""

import json
from models import ClassificationResult, CATEGORIES

# A handful of REAL coded-subject patterns (from emails.py's generators),
# given as few-shot anchors so the model recognises this inbox's actual
# style rather than guessing from generic email intuition.
CLASSIFIER_SYSTEM_PROMPT = f"""You are a classifier for a shipping-documentation
inbox (APRIL Fine Paper, a paper trading company). Read the email's subject,
body, and sender, and classify it into exactly one of these categories:

- BL_COMPARISON: sender wants a Shipping Instruction (SI) checked against a
  draft Bill of Lading (BL), OR is requesting/discussing a draft BL at all
  (even with no attachments yet -- e.g. "please send the draft BL for
  checking"). Real subject patterns: "TO CONFIRM DOCS _ <ref> _ <port> _
  <consignee> _ <bl_no>", "REQUEST BL DRAFT _ PO ...", "Draft BL <vessel> ...
  amend BL ...", or coded strings like "AIE - JEBEL_ALI - MSC(MEDUUD104332) -
  5RSG-00133 - ...".
- SI_REQUEST: sender wants a NEW Shipping Instruction prepared (not a
  comparison). Real patterns: "SI - <bl> - DIRECT(<carrier>) - ...",
  "CUST SI _ MEA _ ...", "REQUEST SI _ ...", "SI NEEDED_ ...".
- INVOICE_QUERY: billing/invoice/charges questions. Real patterns:
  "... BILLING ... MISSING GR", "REQUEST TO CANCEL INVOICE - ...",
  "LOCAL CHARGES FOB - ...", "Mill D & D charges - ...", "Total Freight - ...".
- GENERAL: legitimate operational messages that are NOT a doc request, SI
  request, or invoice question. Real patterns: "UPDATE SUMMARY <vessel>",
  "daily Berthing Report", "_Reminder_Paper - Submit SI & AED", "_RPA_ ...
  Billing Process Completed", HR/holiday notices, outstanding-BL lists.
- SPAM: marketing, phishing, prize/parcel-fee scams, unrelated offers.

Rules:
- Judge by INTENT, not just keywords -- a coded subject line can look similar
  across categories; read the body for what's actually being asked.
- Attachment presence is IRRELEVANT to this decision. A BL_COMPARISON email
  with zero attachments is still BL_COMPARISON.
- Forwarded/quoted thread tails ("From: ... Sent: ... Subject: RE: ...") and
  signature blocks are boilerplate -- classify on the new content, not the
  quoted tail.
- Also assess urgency: "urgent" if the email uses language like ASAP, urgent,
  immediate action, escalation, or a hard deadline; otherwise "routine". This
  is a secondary signal for triage, not part of the category decision.
- If genuinely unsure between two categories, pick the more likely one but
  set confidence below 0.6 so it can be flagged for human review downstream.

Respond with ONLY a JSON object, no other text, no markdown fences:
{{"category": "<one of {CATEGORIES}>", "confidence": <0.0-1.0>, "urgency": "routine" or "urgent", "reason": "<one short sentence>"}}
"""


class EmailClassifier:
    def __init__(self, client, model="claude-sonnet-4-6"):
        """client: an anthropic.Anthropic() instance, passed in so this class
        is easy to unit test with a fake client."""
        self.client = client
        self.model = model

    def classify(self, email: dict) -> ClassificationResult:
        subject = email.get("subject", "")
        body = email.get("body", "")
        sender = email.get("from", "")

        user_prompt = f"From: {sender}\nSubject: {subject}\n\nBody:\n{body}"

        response = self.client.messages.create(
            model=self.model,
            max_tokens=300,
            system=CLASSIFIER_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )

        raw_text = "".join(
            block.text for block in response.content if getattr(block, "type", "") == "text"
        )

        try:
            parsed = json.loads(_strip_fences(raw_text))
            category = parsed.get("category", "GENERAL")
            if category not in CATEGORIES:
                category = "GENERAL"
            urgency = parsed.get("urgency", "routine")
            if urgency not in ("routine", "urgent"):
                urgency = "routine"
            return ClassificationResult(
                category=category,
                confidence=float(parsed.get("confidence", 0.5)),
                urgency=urgency,
                reason=parsed.get("reason", ""),
            )
        except (json.JSONDecodeError, ValueError, TypeError):
            # Model didn't return clean JSON -- don't crash the batch. Default
            # to GENERAL with rock-bottom confidence so the low-confidence
            # check downstream can still catch it for review.
            return ClassificationResult(
                category="GENERAL",
                confidence=0.0,
                urgency="routine",
                reason="Failed to parse classifier output; needs manual check.",
            )


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    return text.strip()
