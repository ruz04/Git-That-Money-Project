# ClassE - SDOC Control Tower — Shipping Document Verification Pipeline

**Averis x Monash Hackathon 2026**

An AI-powered inbox triage system for shipping operations. It classifies incoming emails into 5 categories, automatically compares Shipping Instructions (SI) against draft Bills of Lading (BL), flags exact field-level mismatches, and escalates anything it can't confidently decide to a human — with a live drag-and-drop review board to resolve those cases.

## Team Details

Team Name: Git That Money
- Members:
  - Ruzaiqa Naushad
  - Fariya Hossain
  - Jeevika Akshaya

## What it does

- **Classifies** every email into `BL_COMPARISON`, `SI_REQUEST`, `INVOICE_QUERY`, `GENERAL`, or `SPAM`
- **Extracts** 7 shipment fields (shipper, consignee, notify party, port of loading, port of discharge, container count, gross weight) from SI and BL documents, normalizing label synonyms across documents (e.g. "Load Port" vs "Port of Loading")
- **Compares** SI against BL deterministically — the diff step is plain Python, not AI, so the same input always produces the same result
- **Escalates to a human** when a field is genuinely missing, a document is unreadable, or the wrong document type was attached — it never guesses or silently defaults
- **Ships with a control-tower dashboard**: category/urgency/review tabs, a drag-and-drop human review board, self-computed accuracy diagnostics, and an AI & Cloud usage panel

See [REPORT.md](./Report.md) for the full technical writeup, challenges faced, and roadmap.

## Architecture

```
Dashboard (Vercel)  →  Backend API (Render, FastAPI)  →  Claude (classify + extract)
                                                        →  Deterministic Python (compare)
```

| Stage | File            | Role |
|---|-----------------|---|
| Classification | `classifier.py` | Claude API call — categorizes each email, flags urgency |
| Extraction | `extractor.py`  | Claude API call — pulls the 7 fields, flags blanks and wrong document types |
| Comparison | `comparator.py` | Plain Python — deterministic field-by-field diff |
| Escalation logic | `pipeline.py`   | Orchestrates the above, decides OK / MISMATCH / NEEDS_REVIEW |
| Output shaping | `reporter.py`   | Builds the exact required submission schema |
| API | `app.py`        | Hosts the pipeline as a cloud service |
| Dashboard | `index.html`    | Review + diagnostics UI |

## Setup instructions

### 1. Clone and install dependencies
```bash
git clone <this-repo-url>
cd sdoc_pipeline
pip install -r requirements.txt
```

### 2. Add the dataset
This repo does not include the dataset or the organizers' loader (by design — see the note on `ground_truth.json` below). Copy in:
- `loader.py` (organizers' file)
- `data_v2/inbox/` and `data_v2/attachments/` (do **not** copy `ground_truth.json` in if you plan to push this repo anywhere — see note below)

### 3. Set your API key
```bash
cp .env.example .env
```
Open `.env` and replace `your_key_here` with your real Anthropic API key. `.env` is gitignored and will never be committed.

### 4. Run the pipeline
```bash
python main.py --data data_v2 --out submission.json --limit 20   # quick test, ~20 emails
python main.py --data data_v2 --out submission.json              # full run, all 520
```

### 5. Score it (organizers only, or locally with your own ground truth copy)
```bash
python score_cli.py submission.json --ground-truth data_v2/ground_truth.json
```

### 6. Open the dashboard
Open `dashboard.html` directly in a browser, or visit the deployed link below. Load `submission.json`, your inbox files, and optionally `ground_truth.json` (kept local only) using the buttons in the top bar.

## Cloud deployment

- **Backend API**: `https://git-that-money-project-1.onrender.com`
- **Dashboard**: `https://git-that-money.vercel.app/`

## ⚠️ A note on `ground_truth.json`

This dataset's answer key must never be committed to this repository or deployed publicly — it is gitignored (`data_v2/ground_truth.json`) on purpose. Score locally only.

## Team

`[team name / member names]`
