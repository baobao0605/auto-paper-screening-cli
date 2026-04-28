# AI Full-Text Screening (CLI + Desktop GUI)

This repository is a local-first Python tool for AI-assisted screening of full-text academic papers.

It includes:
- CLI: `python -m src.main ...`
- Desktop GUI MVP: `python -m src.gui_app`

Both modes reuse the same core pipeline: SQLite persistence, deduplication, resume logic, strict output validation, and full export regeneration.

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

If PowerShell blocks venv activation, run:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

## Windows Double-Click GUI Start

After you finish the installation steps above once, you can start GUI by double-clicking:
- `启动AI筛选GUI.bat` (Chinese filename)
- or `start_gui.bat` (English filename)

What the script does:
- Switches to project root
- Activates `.venv`
- Runs `python -m src.gui_app`
- Keeps the window open on exit so errors are visible

Optional hidden launcher:
- `start_gui_hidden.vbs` (no visible console window)
- If startup fails, prefer `start_gui.bat` for debugging error output

If the window flashes or startup fails, run manually in PowerShell:

```powershell
python -m src.gui_app
```

## Environment Variables

- `GEMINI_API_KEY`: Gemini key
- `GOOGLE_API_KEY`: Gemini fallback key
- `OPENAI_COMPATIBLE_API_KEY`: OpenAI-compatible key
- `DEEPSEEK_API_KEY`: DeepSeek key
- `ANTHROPIC_API_KEY`: Anthropic/Claude key
- `GEMINI_MODEL`: optional override for configured Gemini model
- `APP_ENV`: optional environment label

## Input Files

Put local full-text papers in `input/local_papers/`.

Supported file types:
- `.pdf`
- `.docx`
- `.txt`

The pipeline does not move or rename files in the input directory.

## CLI Commands

Run from repository root:

```powershell
python -m src.main scan
python -m src.main run
python -m src.main export
python -m src.main retry-failed
python -m src.main rescreen-doi --dois "10.1000/one|10.1000/two" --delimiter "|"
python -m src.main status
```

Behavior summary:
- `scan`: discover files, register in SQLite, mark duplicates
- `run`: scan + screen queueable papers + export full log
- `retry-failed`: rerun retryable failures + export
- `export`: regenerate full Excel/CSV from SQLite
- `rescreen-doi`: rerun by exact DOI + overwrite conclusion + export
- `status`: show summary counts

Quick verification:

```powershell
python -m src.main --help
python -m src.main scan
python -m src.main status
python -m pytest
```

## Desktop GUI (MVP)

Start GUI:

```powershell
python -m src.gui_app
```

GUI supports:
- Select input folder
- Choose provider (`gemini`, `deepseek`, `openai_compatible`, `anthropic`)
- Set API key, model, base URL
- Edit and save prompt
- Start Screening / Retry Failed / Auto Start / Stop Screening
- Live table refresh (file/status/decision/error)
- Export Excel/CSV
- Refresh status
- Open project output folder
- Clear current project history
- View logs

Stop behavior:
- Stop is cooperative (current paper finishes first)
- Queue stops before the next paper
- SQLite state remains consistent for resume

## Project Workspace (Per Input Folder)

GUI uses isolated workspaces by input folder:
- One `input_dir` maps to one `project_id`
- Each project has its own SQLite, Excel/CSV, logs, and snapshots
- Switching input folder switches current project automatically
- Switching back to an older input folder restores its history
- Export in GUI only exports the current project

Project id format:
- `<input_folder_name>_<short_hash_of_absolute_path>`
- Example: `papers_a83f21`

Output structure:

```text
output/
  projects/
    <project_id>/
      screening.sqlite
      screening_log.xlsx
      screening_log.csv
      run.log
      error.log
      criteria_prompt_snapshot.txt
      settings_snapshot.json
```

Clear Current Project History:
- Deletes current project's SQLite, exports, logs, and snapshots
- Does not delete original papers in input folder

## Provider Configuration

`config/settings.yaml(.example)` includes:
- `provider.name`
- `gemini`
- `openai_compatible`
- `deepseek`
- `anthropic`

Supported provider names:
- Gemini: `gemini`, `google`, `google_gemini`
- OpenAI-compatible: `openai_compatible`
- DeepSeek: `deepseek` (via OpenAI-compatible API)
- Anthropic: `anthropic`, `claude`

Practical GUI defaults:
- `gemini`: leave `base_url` empty, set model (for example `gemini-2.5-flash`)
- `deepseek`: provider `deepseek`, model default is typically `deepseek-chat`, `base_url` can be empty (uses configured default) or custom
- `openai_compatible`: usually requires explicit `base_url` for your endpoint
- `anthropic` / `claude`: `base_url` can be empty (uses configured default), set model explicitly in GUI

## Using Other AI Providers / 使用其他 AI 服务商

Current GUI providers:
- `gemini`
- `deepseek`
- `openai_compatible`
- `anthropic`

If you want to use Kimi, GLM, Qwen, OpenRouter, Together, SiliconFlow, or other third-party platforms:
- If the platform supports OpenAI-compatible APIs, choose `openai_compatible` in GUI.
- Fill `base_url` from that platform's official docs.
- Fill model name required by that platform.
- Fill API key from that platform.
- Do not commit real API keys to this repository.

Examples:
- Gemini:
  - provider = `gemini`
  - base_url = empty
- DeepSeek:
  - provider = `deepseek`
  - base_url = empty (or custom)
- Anthropic / Claude:
  - provider = `anthropic`
  - base_url = empty (or custom)
- Kimi / Moonshot:
  - provider = `openai_compatible`
  - base_url/model from Moonshot docs
- GLM / Zhipu:
  - provider = `openai_compatible`
  - base_url/model from Zhipu docs
- Qwen / DashScope:
  - provider = `openai_compatible`
  - base_url/model from DashScope/Qwen docs
- Other platforms:
  - provider = `openai_compatible`
  - base_url/model/api_key from provider docs

Notes:
- Not all platforms are 100% compatible.
- If errors occur, first verify base_url, model, api_key, quota/billing, account permissions, region settings, and official provider docs.
- This project does not include every provider-specific custom parameter. `openai_compatible` is the general integration path.

## GUI Run Modes

Start Screening:
- Runs normal queue logic for current project (same core behavior as CLI run)

Retry Failed:
- Only retries failed retryable statuses (`TEXT_FAILED_RETRY`, `SCREEN_FAILED_RETRY`) in current project
- Does not rerun `DONE`

Auto Start:
- Phase 1: retry failed papers in current project
- Phase 2: screen `NEW` papers only in current project
- Prevents phase-2 from reprocessing retry-failed rows again

## Prompt Management

- Default prompt path: `config/criteria_prompt.txt`
- GUI uses `PromptManager` to load/save UTF-8 prompt text
- Prompt validation: non-empty string required
- Saved prompt persists across restarts because it is written back to disk

## API Key Storage (GUI)

GUI settings path:
- Windows: `%APPDATA%\ai_fulltext_screening\app_config.json`
- macOS/Linux: `~/.ai_fulltext_screening/app_config.json`

API key behavior:
- Prefer keyring when available
- If keyring unavailable, save under `api_keys` in user `app_config.json`
- Fallback to environment variables when no saved key exists

Never commit real API keys to repository files.

## Resume Behavior

Queueable statuses:
- `NEW`
- `TEXT_FAILED_RETRY`
- `SCREEN_FAILED_RETRY`

Skipped statuses:
- `DONE`
- `MANUAL_DONE`
- `SKIPPED_DUPLICATE`

Interrupted runs recover stale `TEXT_EXTRACTED` and `SCREENING` rows into retryable states on next run.

## Deduplication

Identity matching order:
1. DOI
2. content hash
3. file hash
4. fallback fingerprint

## Export Behavior

Exports are always fully regenerated from SQLite (never append-only).

Column order is fixed:
1. `Title`
2. `DOI`
3. `Decision`
4. `Exclude reason`
5. `Construct`
6. `Note`
7. `Model`

Defaults:
- Excel: `output/screening_log.xlsx`
- CSV: `output/screening_log.csv`

`Model` column:
- Stores actual provider/model used for that row
- Format example: `gemini / gemini-2.5-flash`
- Legacy rows created before this feature may have empty model

## Logging

- `output/run.log`
- `output/error.log`

Raw model responses are optionally stored in `screening_runs` when enabled.

## Local Verification Commands

```powershell
py -3.11 -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pytest
python -m src.main --help
python -m src.main status
python -m src.gui_app
```

Manual GUI validation checklist:
1. Choose input folder A, run Start Screening, Export.
2. Choose input folder B, run Start Screening, Export.
3. Switch back to A and confirm A history remains.
4. Click Retry Failed and verify only retryable failed rows are processed.
5. Click Auto Start and verify retry phase then new-only phase.
6. Open Project Output Folder and verify workspace files.
7. Clear Current Project History and verify only current project data is cleared.

## Optional Packaging (PyInstaller)

For a quick local packaging attempt (needs local validation per machine):

```powershell
python -m pip install pyinstaller
pyinstaller --noconfirm --windowed --name AI-Screening-GUI src\gui_app.py
```

Note: packaging behavior can vary by OS and Python environment, so test the generated app on your target machine.
