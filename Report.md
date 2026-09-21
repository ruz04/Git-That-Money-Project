# Technical Report — ClasseE - SDOC Control Tower

This document covers the technical architecture, implementation, and written-response
topics required for submission. Each section below is written to be copyable
directly into the corresponding field of the submission Google Form.

---

## Technical Architecture

The system is a three-stage pipeline behind a thin API, split into an AI layer and a
deterministic layer on purpose:

```
Email inbox → Classifier (Claude) → Extractor (Claude) → Comparator (Python) → Report
                                                                  ↓
                                                    NEEDS_REVIEW → Human Review Board
```

- **Frontend**: a single static dashboard (`index.html`), deployed on Vercel — no
  build step, no framework, reads its data client-side from JSON files or the backend API.
- **Backend**: a FastAPI service (`app.py`) wrapping the pipeline, deployed on Render.
  Exposes `/run`, `/submission`, and a locally-scoped `/score` endpoint.
- **AI layer**: Claude (Anthropic API) performs classification and field extraction —
  the two genuinely ambiguous, language-understanding tasks.
- **Deterministic layer**: the SI-vs-BL comparison is plain Python, not AI, so the same
  input always produces the same output — required because the scoring rubric grades
  on an exact set-match of mismatched fields, with no partial credit.

## Implementation Details

Each email is classified into one of 5 categories using real coded subject-line patterns as 
few-shot grounding, independent of whether attachments are present (a BL_COMPARISON request 
with no attachment yet is still BL_COMPARISON). To ensure optimal data quality prior to 
analysis, the system routes all incoming text and metadata through an automated data cleaning 
pipeline. For comparison emails, the SI and BL attachments are each read and their 7 shipment 
fields extracted, with the extractor explicitly normalizing label synonyms (e.g. "Load Port" 
vs "Port of Loading (POL)" vs "POL") and recognizing deliberate blank-value tokens (???, TBA, 
N/A, etc.) as missing data rather than literal values. Before comparison, the pipeline checks, 
in order: whether both an SI and BL attachment exist, whether each is readable, and whether 
each is actually the expected document type — routing to one of four specific escalation 
reasons if not. Only once a case passes all of these does the deterministic comparator run, 
checking each of the 7 fields with numeric-aware, formatting-tolerant equality. Furthermore, 
cases flagged for manual intervention enter a human review panel featuring an internal 
feedback loop, which logs human corrections to continuously improve and refine future 
automated extractions.

## Problem–Solution Alignment

The brief's core pain points map directly onto pipeline stages: finding the right
emails in a mixed inbox → the classifier; manual field-by-field comparison being slow
and error-prone → the deterministic comparator; the same field looking different
across documents → the extractor's synonym normalization; and the risk of confidently
reporting a wrong answer on messy real-world input → the four-reason escalation system,
which refuses to guess rather than produce a false match or a false mismatch.

## AI and Cloud Infrastructure Integration

AI is used for exactly the two stages that require language understanding —
classification and extraction — via the Claude API (Anthropic), and nowhere else; the
comparison step is deliberately kept as plain, auditable Python. Cloud infrastructure:
the backend pipeline is deployed on Render as a containerless Python web service
(scales to zero when idle), and the dashboard is deployed on Vercel as a static site
with global edge delivery. Secrets (the Anthropic API key) are managed via environment
variables on the hosting platform, never committed to source control — enforced via
`.gitignore` and a checked-in `.env.example` template. Additionally, a 

## User Feedback / Testing

The pipeline was validated against the organizers' 520-email synthetic dataset,
including 20 deliberately constructed edge cases (wrong document type, missing
attachment, unreadable file, missing field value) designed to test exactly the
reliability behaviour this system is built around. Scoring is done via the organizers'
`score_cli.py`, and the same scoring logic is mirrored live in the dashboard's
Diagnostics tab for fast iteration. For the human-in-the-loop workflow specifically, we
built and used the drag-and-drop review board ourselves during development to resolve
escalated cases, and the dashboard tracks that review activity (pending / confirmed /
resolved / false-alarm counts) as a lightweight internal feedback loop. 

## Coding Challenges

The biggest constraint was the scoring rubric's exact-set-match requirement on
`defect_fields` — no partial credit — which ruled out using an LLM for the comparison
step itself, since LLM output isn't guaranteed deterministic between runs. Correctly
distinguishing a genuinely blank field from a real value required building an explicit
blank-token vocabulary into the extraction prompt rather than relying on the model to
infer it. We also caught and fixed a real secrets-management mistake mid-build — an
API key was briefly hardcoded during local debugging — and corrected it to use
environment variables before any deployment, which reinforced why that workshop
guidance matters in practice, not just in theory. PDF/DOCX/XLSX attachment parsing
(roughly 22% of the real dataset) is designed for but not yet implemented; those
attachments currently and correctly route to `NEEDS_REVIEW` rather than being
mis-extracted.

## Success Metrics

We evaluate against the organizers' own weighted scoring formula:
`0.30 × Stage 1 classification macro-F1 + 0.20 × Stage 3 defect-detection F1 + 0.50 ×
end-to-end exact-match rate`, computed by `score_cli.py` and mirrored live in our
dashboard. Reliability (correctly escalating the 4 edge-case types rather than false-
alarming) is tracked as a separate diagnostic axis, per the organizers' own scoring
design. *[Insert your actual final-run numbers here once available: accuracy, macro-F1,
defect F1, end-to-end rate, final score.]*

## Scalability Plans

Near-term: complete PDF/DOCX/XLSX text extraction so the full real-world format mix is
covered, not just plain text. Mid-term: a resolution-drafting stage that turns a
confirmed mismatch into a ready-to-send correction email citing the exact source
evidence, closing the loop from detection to action rather than stopping at a report.
Also planned: a session-level "learned synonym" log so recurring label variants are
tracked over time, and tighter security (scoped API keys, rate limiting on the public
API, narrower CORS) once the system moves past demo stage. The architecture — AI and
deterministic logic kept as separate, swappable layers — is built to support all of
this without restructuring the core pipeline.