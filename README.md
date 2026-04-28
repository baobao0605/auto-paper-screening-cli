# AI Full-Text Screening CLI

This repository is a local-first Python CLI for AI-assisted screening of full-text academic papers. It scans papers already stored in `input/local_papers/`, registers them in SQLite, skips papers that are already completed, screens only eligible unscreened or retryable papers with Gemini, validates model output strictly, and regenerates the full Excel log from SQLite on every export.

## Folder Structure

```text
config/
data/
input/
  local_papers/
output/
src/
tests/
.env.example
requirements.txt
README.md
```

## Installation

1. Use Python 3.11 or newer.
2. Create and activate a virtual environment.
3. Install dependencies.

Windows PowerShell:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
Copy-Item config\settings.yaml.example config\settings.yaml
```

macOS/Linux:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.example .env
cp config/settings.yaml.example config/settings.yaml
```

4. Edit `.env` and set `GEMINI_API_KEY`.
5. Optionally adjust `config/settings.yaml` for paths, prompt version, export locations, or model settings.

Useful Gemini retry settings in `config/settings.yaml`:

```yaml
gemini:
  request_max_retries: 3
  request_retry_delay_seconds: 2.0
```

These settings help the CLI recover automatically from transient SSL/network errors such as `UNEXPECTED_EOF_WHILE_READING`.

## Environment Variables

- `GEMINI_API_KEY`: required for Gemini screening calls.
- `GEMINI_MODEL`: optional override for the configured Gemini model.
- `APP_ENV`: optional environment label for local use.

## Input Files

Put local full-text papers in `input/local_papers/`.

Supported file types:
- `.pdf`
- `.docx`
- `.txt`

The CLI does not move or rename files in `input/local_papers/`.

## Commands

Run commands from the repository root.

If `python` is not on your PATH in Windows, replace `python` with `py -3.11`.

```powershell
python -m src.main scan
python -m src.main run
python -m src.main export
python -m src.main retry-failed
python -m src.main rescreen-doi --dois "10.1000/one|10.1000/two" --delimiter "|"
python -m src.main status
```

Command behavior:
- `scan`: discovers files, registers them in SQLite, and marks obvious duplicates.
- `run`: performs scan, resumes safely, screens only queueable papers, commits each paper immediately, then regenerates the full Excel export.
- `export`: regenerates the complete Excel file from SQLite.
- `retry-failed`: reruns only `TEXT_FAILED_RETRY` and `SCREEN_FAILED_RETRY` papers, then exports again.
- `rescreen-doi`: reruns only the DOI values you specify, overwrites the prior conclusion in SQLite, and then regenerates the full export.
- `status`: prints summary counts for discovered papers and decisions.

`rescreen-doi` usage:
- Put one or more DOI values into `--dois`.
- The DOI text must match the `DOI` column in `screening_log` exactly.
- Use `--delimiter` to tell the CLI which symbol connects multiple DOI values. The default delimiter is `|`.

Examples:

```powershell
python -m src.main rescreen-doi --dois "10.1000/one|10.1000/two" --delimiter "|"
python -m src.main rescreen-doi --dois "10.1000/one;10.1000/two" --delimiter ";"
```

Quick local verification after install:

```powershell
python -m src.main --help
python -m src.main scan
python -m src.main status
python -m pytest
```

## Resume Behavior

The pipeline stores paper-level state in SQLite and does not re-screen papers that are already completed.

Queueable statuses:
- `NEW`
- `TEXT_FAILED_RETRY`
- `SCREEN_FAILED_RETRY`

Automatically skipped statuses:
- `DONE`
- `MANUAL_DONE`
- `SKIPPED_DUPLICATE`

If the process is interrupted, stale `TEXT_EXTRACTED` and `SCREENING` rows are recovered into retryable statuses on the next run.

## Deduplication

The pipeline uses stable identity matching in this order:

1. DOI
2. content hash
3. file hash
4. fallback fingerprint

Duplicate copies of the same paper are marked as `SKIPPED_DUPLICATE` and linked to a canonical paper so they do not generate duplicate screening rows or duplicate export rows.

## Export Behavior

The Excel log is always fully regenerated from SQLite. It is never append-only.

The export contains exactly these columns in this order:

1. `Title`
2. `DOI`
3. `Decision`
4. `Exclude reason`
5. `Construct`
6. `Note`

The default export path is `output/screening_log.xlsx`. A matching CSV is also written by default to `output/screening_log.csv`.

The `run` command also regenerates the full Excel export automatically at the end of each run.

The `rescreen-doi` command also regenerates the full Excel export automatically after targeted rescreening.

## Logging

Logs are written to `output/run.log` and `output/error.log`. Raw Gemini responses are also stored in the `screening_runs` table when `save_raw_response` is enabled.

PDF extraction uses `pypdf` first and falls back to `pdfminer.six` for some malformed or truncated PDFs.

## Config and Prompt

- `config/settings.yaml(.example)` controls paths, export locations, prompt version, batching, and Gemini settings.
- `config/criteria_prompt.txt` is loaded by the app at runtime and inserted into the screening prompt sent to Gemini.
- `.env` is used for `GEMINI_API_KEY` and optional model overrides.

## Development and Tests

Run the test suite with:

```powershell
python -m pytest
```
