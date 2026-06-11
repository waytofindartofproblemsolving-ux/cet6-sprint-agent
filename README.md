# CET-6 Sprint Agent

A small local web app for a three-day CET-6 study sprint. It generates timed drills from user-provided recent real CET-6 exam materials, grades attempts, records mistakes, and schedules next-day review.

## Setup

```powershell
python -m pip install -r requirements.txt
$env:AI_PROVIDER="deepseek"
$env:DEEPSEEK_API_KEY="your-deepseek-key"
python -m uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000>.

If you already placed a DeepSeek key in `OPENAI_API_KEY`, set
`$env:AI_PROVIDER="deepseek"` and the app will reuse it.

OpenAI is still supported:

```powershell
$env:AI_PROVIDER="openai"
$env:OPENAI_API_KEY="sk-your-key"
python -m uvicorn app.main:app --reload
```

For local demo mode without an API key:

```powershell
$env:CET6_USE_FAKE_AI="1"
python -m uvicorn app.main:app --reload
```

## What It Stores

- `cet6.sqlite3`: local drills, attempts, materials, and review items.
- `DEEPSEEK_API_KEY` / `OPENAI_API_KEY`: read only from the environment. Keys are not stored in the repo or rendered on the page.

## Material Policy

Drill generation requires selecting a saved CET-6 real exam material from the past 15 years. The repo does not include copyrighted real-paper text; paste your own source material locally and tag it with its exam year.

The Materials page can also import a full paper that you paste locally. Use section headings such as `## Reading`, `## Listening`, `## Writing`, `## Translation`, or `## Vocabulary`; Chinese headings like `【阅读】` and `【翻译】` are supported too. The importer splits sections into skill-tagged material records.

For local PDF/Word collections, use the Materials page's local folder importer. It scans local CET-6 folders, quarantines ad files into `_quarantine_ads/`, extracts PDF/DOCX/TXT text, stores answer explanations separately from practice materials, and reports files that need manual conversion.

## API Notes

The live adapters are isolated in `app/ai/openai_client.py` and `app/ai/deepseek_client.py`. OpenAI uses the Responses API with JSON schema structured outputs; DeepSeek uses its OpenAI-compatible Chat Completions API with JSON output. Tests use `FakeAIClient`, so they do not spend tokens or require a key.
