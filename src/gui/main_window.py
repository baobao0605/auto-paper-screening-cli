"""Minimal desktop GUI for local screening workflow."""

from __future__ import annotations

from dataclasses import replace
import os
from pathlib import Path
import subprocess
import sys

from PySide6.QtCore import QThread
from PySide6.QtWidgets import (
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QComboBox,
)

from src.app_config import get_api_key, load_app_config, save_api_key, save_app_config
from src.gui.screening_worker import ScreeningWorker
from src.gui_service import CancelToken, GuiScreeningService, RuntimeOverrides
from src.prompt_manager import PromptManager, PromptManagerError


TABLE_COLUMNS = [
    "File name",
    "Title",
    "DOI",
    "Status",
    "Decision",
    "Exclude reason",
    "Construct",
    "Note",
    "Model",
    "Error",
    "Elapsed(s)",
]

PROVIDER_OPTIONS = ["gemini", "deepseek", "openai_compatible", "anthropic"]
PROVIDER_HELP_TEXT = (
    "Provider guide:\n"
    "- Gemini: choose gemini, keep Base URL empty.\n"
    "- DeepSeek: choose deepseek, Base URL can be empty, model can be deepseek-chat.\n"
    "- Anthropic/Claude: choose anthropic, Base URL can be empty, set Claude model.\n"
    "- Kimi, GLM, Qwen, OpenRouter, Together, SiliconFlow and similar platforms:\n"
    "  if they support OpenAI-compatible API, choose openai_compatible and fill Base URL, Model, API Key.\n"
    "- For most other OpenAI-compatible providers, try openai_compatible first."
)
OPENAI_COMPATIBLE_LOG_HINT = (
    "OpenAI-compatible mode works for many third-party platforms such as "
    "Kimi/GLM/Qwen/OpenRouter/Together/SiliconFlow when they provide OpenAI-compatible APIs. "
    "Please fill Base URL, Model, and API Key from that platform's docs."
)
OPENAI_COMPATIBLE_REFERENCE = (
    "Common OpenAI-compatible references (verify with official docs):\n"
    "- Kimi/Moonshot: base_url often https://api.moonshot.ai/v1\n"
    "- GLM/Zhipu: use Zhipu OpenAI-compatible endpoint from official docs\n"
    "- Qwen/DashScope: use DashScope/Qwen endpoint from official docs\n"
    "- OpenRouter: base_url often https://openrouter.ai/api/v1\n"
    "- Together: base_url often https://api.together.xyz/v1\n"
    "- SiliconFlow: base_url/model per SiliconFlow docs"
)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("AI Full-Text Screening (MVP)")
        self.config = load_app_config()
        self.thread: QThread | None = None
        self.worker: ScreeningWorker | None = None
        self.cancel_token: CancelToken | None = None
        self.elapsed_by_file: dict[str, str] = {}
        self._setup_ui()
        self._load_initial_values()
        self._refresh_project_info()
        self.refresh_status()
        self.refresh_table()

    def _setup_ui(self) -> None:
        root = QWidget(self)
        layout = QVBoxLayout(root)
        self.setCentralWidget(root)

        layout.addWidget(QLabel("Input Folder"))
        input_row = QHBoxLayout()
        self.input_dir_edit = QLineEdit()
        self.select_input_btn = QPushButton("Browse")
        self.select_input_btn.clicked.connect(self.choose_input_dir)
        input_row.addWidget(self.input_dir_edit)
        input_row.addWidget(self.select_input_btn)
        layout.addLayout(input_row)
        self.project_label = QLabel("Current Project: -")
        self.project_output_label = QLabel("Project Output: -")
        layout.addWidget(self.project_label)
        layout.addWidget(self.project_output_label)

        layout.addWidget(QLabel("Provider Settings"))
        grid = QGridLayout()
        self.provider_combo = QComboBox()
        self.provider_combo.addItems(PROVIDER_OPTIONS)
        self.provider_combo.currentTextChanged.connect(self.load_api_key_for_provider)
        self.provider_combo.setToolTip(
            "Most third-party model platforms that are OpenAI API compatible can use openai_compatible."
        )
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        self.model_edit = QLineEdit()
        self.base_url_edit = QLineEdit()
        self.save_settings_btn = QPushButton("Save Settings")
        self.save_settings_btn.clicked.connect(self.save_settings)
        grid.addWidget(QLabel("Provider"), 0, 0)
        grid.addWidget(self.provider_combo, 0, 1)
        grid.addWidget(QLabel("API Key"), 1, 0)
        grid.addWidget(self.api_key_edit, 1, 1)
        grid.addWidget(QLabel("Model"), 2, 0)
        grid.addWidget(self.model_edit, 2, 1)
        grid.addWidget(QLabel("Base URL"), 3, 0)
        grid.addWidget(self.base_url_edit, 3, 1)
        grid.addWidget(self.save_settings_btn, 4, 1)
        layout.addLayout(grid)

        self.provider_help = QPlainTextEdit()
        self.provider_help.setReadOnly(True)
        self.provider_help.setPlainText(PROVIDER_HELP_TEXT + "\n\n" + OPENAI_COMPATIBLE_REFERENCE)
        self.provider_help.setMaximumHeight(155)
        layout.addWidget(self.provider_help)

        layout.addWidget(QLabel("Prompt"))
        self.prompt_edit = QPlainTextEdit()
        layout.addWidget(self.prompt_edit)
        self.save_prompt_btn = QPushButton("Save Prompt")
        self.save_prompt_btn.clicked.connect(self.save_prompt)
        layout.addWidget(self.save_prompt_btn)

        control_row = QHBoxLayout()
        self.start_btn = QPushButton("Start Screening")
        self.stop_btn = QPushButton("Stop Screening")
        self.stop_btn.setEnabled(False)
        self.retry_failed_btn = QPushButton("Retry Failed")
        self.retry_failed_btn.setToolTip("Retry only TEXT_FAILED_RETRY and SCREEN_FAILED_RETRY rows.")
        self.auto_start_btn = QPushButton("Auto Start")
        self.clear_project_btn = QPushButton("Clear Current Project History")
        self.export_excel_btn = QPushButton("Export Excel")
        self.export_csv_btn = QPushButton("Export CSV")
        self.refresh_btn = QPushButton("Refresh Status")
        self.open_output_btn = QPushButton("Open Project Output Folder")
        self.start_btn.clicked.connect(self.start_screening)
        self.stop_btn.clicked.connect(self.stop_screening)
        self.retry_failed_btn.clicked.connect(self.start_retry_failed)
        self.auto_start_btn.clicked.connect(self.start_auto_start)
        self.clear_project_btn.clicked.connect(self.clear_project_history)
        self.export_excel_btn.clicked.connect(self.export_now)
        self.export_csv_btn.clicked.connect(self.export_now)
        self.refresh_btn.clicked.connect(self.refresh_all)
        self.open_output_btn.clicked.connect(self.open_output_dir)
        for button in [
            self.start_btn,
            self.stop_btn,
            self.retry_failed_btn,
            self.auto_start_btn,
            self.clear_project_btn,
            self.export_excel_btn,
            self.export_csv_btn,
            self.refresh_btn,
            self.open_output_btn,
        ]:
            control_row.addWidget(button)
        layout.addLayout(control_row)

        self.status_label = QLabel("Status: -")
        layout.addWidget(self.status_label)

        self.table = QTableWidget(0, len(TABLE_COLUMNS))
        self.table.setHorizontalHeaderLabels(TABLE_COLUMNS)
        layout.addWidget(self.table)

        layout.addWidget(QLabel("Log"))
        self.log_edit = QPlainTextEdit()
        self.log_edit.setReadOnly(True)
        layout.addWidget(self.log_edit)

    def _load_initial_values(self) -> None:
        self.input_dir_edit.setText(self.config.input_dir)
        index = self.provider_combo.findText(self.config.provider)
        if index >= 0:
            self.provider_combo.setCurrentIndex(index)
        self.model_edit.setText(self.config.model)
        self.base_url_edit.setText(self.config.base_url)
        self.load_api_key_for_provider(self.provider_combo.currentText())
        prompt_path = Path(self.config.prompt_path)
        manager = PromptManager(default_prompt_path=prompt_path)
        self.prompt_edit.setPlainText(manager.load_prompt(prompt_path))

    def append_log(self, message: str) -> None:
        self.log_edit.appendPlainText(message)

    def choose_input_dir(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "Select input folder", self.input_dir_edit.text())
        if selected:
            self.input_dir_edit.setText(selected)
            self.config = replace(self.config, input_dir=selected)
            save_app_config(self.config)
            self._refresh_project_info()
            self.refresh_all()

    def _refresh_project_info(self) -> None:
        workspace = GuiScreeningService().project_workspace(input_dir=self.input_dir_edit.text().strip())
        self.project_label.setText(f"Current Project: {workspace.project_id}")
        self.project_output_label.setText(f"Project Output: {workspace.root_dir}")

    def load_api_key_for_provider(self, provider: str) -> None:
        key, source = get_api_key(provider)
        self.api_key_edit.setText(key or "")
        if source != "missing":
            self.append_log(f"Loaded API key from {source} for provider={provider}")
        if provider == "openai_compatible":
            self.append_log(OPENAI_COMPATIBLE_LOG_HINT)

    def save_settings(self) -> None:
        self.config = replace(
            self.config,
            input_dir=self.input_dir_edit.text().strip(),
            provider=self.provider_combo.currentText().strip(),
            model=self.model_edit.text().strip(),
            base_url=self.base_url_edit.text().strip(),
            prompt_path=self.config.prompt_path,
        )
        save_app_config(self.config)
        key = self.api_key_edit.text().strip()
        if key:
            result = save_api_key(self.config.provider, key)
            self.append_log(f"API key save result: {result.source}")
        self.append_log("Settings saved.")

    def save_prompt(self) -> None:
        prompt_path = Path(self.config.prompt_path)
        manager = PromptManager(default_prompt_path=prompt_path)
        prompt_text = self.prompt_edit.toPlainText()
        try:
            manager.save_prompt(prompt_text, prompt_path=prompt_path)
        except PromptManagerError as exc:
            QMessageBox.warning(self, "Prompt validation failed", str(exc))
            return
        self.append_log(f"Prompt saved: {prompt_path}")

    def _validate_before_run(self) -> bool:
        input_dir = Path(self.input_dir_edit.text().strip())
        if not input_dir.exists():
            QMessageBox.warning(self, "Input path error", f"Input folder does not exist: {input_dir}")
            return False
        prompt_text = self.prompt_edit.toPlainText()
        try:
            PromptManager.validate_prompt(prompt_text)
        except PromptManagerError as exc:
            QMessageBox.warning(self, "Prompt validation failed", str(exc))
            return False
        provider = self.provider_combo.currentText().strip()
        api_key = self.api_key_edit.text().strip()
        model = self.model_edit.text().strip()
        base_url = self.base_url_edit.text().strip()

        if not api_key:
            QMessageBox.warning(self, "API Key missing", "API Key cannot be empty.")
            return False
        if not model:
            QMessageBox.warning(self, "Model missing", "Model cannot be empty.")
            return False
        if provider == "openai_compatible" and not base_url:
            message = "openai_compatible requires Base URL from your provider."
            self.append_log(message)
            QMessageBox.warning(self, "Base URL missing", message)
            return False
        return True

    def _build_overrides(self) -> RuntimeOverrides:
        return RuntimeOverrides(
            input_dir=self.input_dir_edit.text().strip(),
            provider_name=self.provider_combo.currentText().strip(),
            api_key=self.api_key_edit.text().strip(),
            model=self.model_edit.text().strip(),
            base_url=self.base_url_edit.text().strip(),
            prompt_text=self.prompt_edit.toPlainText(),
            prompt_path=self.config.prompt_path,
            run_mode="start",
        )

    def start_screening(self) -> None:
        self._start_run("start")

    def start_retry_failed(self) -> None:
        self._start_run("retry_failed")

    def start_auto_start(self) -> None:
        self._start_run("auto_start")

    def _start_run(self, run_mode: str) -> None:
        if not self._validate_before_run():
            return
        self.save_settings()
        self.save_prompt()
        overrides = self._build_overrides()
        overrides.run_mode = run_mode

        self.cancel_token = CancelToken()
        self.thread = QThread(self)
        self.worker = ScreeningWorker(None, overrides, self.cancel_token)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.log_signal.connect(self.append_log)
        self.worker.started_signal.connect(lambda payload: self.append_log(f"Queued total: {payload.get('total_count', 0)}"))
        self.worker.paper_started_signal.connect(self._on_paper_started)
        self.worker.paper_finished_signal.connect(self._on_paper_finished)
        self.worker.paper_error_signal.connect(self._on_paper_error)
        self.worker.finished_signal.connect(self._on_finished)
        self.worker.cancelled_signal.connect(self._on_cancelled)
        self.worker.failed_signal.connect(self._on_failed)
        self.worker.finished_signal.connect(lambda _: self._cleanup_thread())
        self.worker.cancelled_signal.connect(lambda _: self._cleanup_thread())
        self.worker.failed_signal.connect(lambda _: self._cleanup_thread())
        self.thread.start()
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.append_log(f"Run started. mode={run_mode}")

    def stop_screening(self) -> None:
        if self.cancel_token is not None:
            self.cancel_token.cancel()
            self.append_log("Stopping requested. Current paper will finish first.")

    def _on_paper_started(self, payload: dict) -> None:
        self.append_log(f"Running: {payload.get('file_name', '')}")

    def _on_paper_finished(self, payload: dict) -> None:
        file_name = payload.get("file_name", "")
        elapsed = payload.get("elapsed_seconds", "")
        if file_name and elapsed:
            self.elapsed_by_file[file_name] = str(elapsed)
        self.append_log(f"{payload.get('status', 'Done')}: {payload.get('file_name', '')}")
        self.refresh_table()

    def _on_paper_error(self, payload: dict) -> None:
        file_name = payload.get("file_name", "")
        elapsed = payload.get("elapsed_seconds", "")
        if file_name and elapsed:
            self.elapsed_by_file[file_name] = str(elapsed)
        self.append_log(f"Error: {payload.get('file_name', '')} | {payload.get('error', '')}")
        self.refresh_table()

    def _on_finished(self, payload: dict) -> None:
        self.append_log(f"Finished. Done={payload.get('done', 0)} Failed={payload.get('failed', 0)}")
        self.refresh_all()

    def _on_cancelled(self, payload: dict) -> None:
        self.append_log(f"Cancelled. Processed done={payload.get('done', 0)} failed={payload.get('failed', 0)}")
        self.refresh_all()

    def _on_failed(self, message: str) -> None:
        self.append_log(f"Run failed: {message}")
        QMessageBox.critical(self, "Run failed", message)
        self.refresh_all()

    def _cleanup_thread(self) -> None:
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        if self.thread is not None:
            self.thread.quit()
            self.thread.wait(2000)
        self.thread = None
        self.worker = None
        self.cancel_token = None

    def export_now(self) -> None:
        try:
            count = GuiScreeningService().export(input_dir=self.input_dir_edit.text().strip())
            self.append_log(f"Export completed. rows={count}")
        except Exception as exc:
            self.append_log(f"Export failed: {exc}")
            QMessageBox.warning(self, "Export failed", str(exc))

    def refresh_status(self) -> None:
        summary = GuiScreeningService().status(input_dir=self.input_dir_edit.text().strip())
        self.status_label.setText(
            "Status: "
            f"total={summary.get('total_discovered', 0)} "
            f"done={summary.get('done', 0)} "
            f"new={summary.get('new', 0)} "
            f"failed={summary.get('failed', 0)}"
        )

    def refresh_table(self) -> None:
        rows = GuiScreeningService().list_table_rows(input_dir=self.input_dir_edit.text().strip(), limit=500)
        self.table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            file_name = str(row.get("File name", ""))
            row_with_elapsed = dict(row)
            row_with_elapsed["Elapsed(s)"] = self.elapsed_by_file.get(file_name, "")
            for col_index, column in enumerate(TABLE_COLUMNS):
                value = row_with_elapsed.get(column, "")
                self.table.setItem(row_index, col_index, QTableWidgetItem(str(value)))

    def refresh_all(self) -> None:
        self.refresh_status()
        self.refresh_table()

    def open_output_dir(self) -> None:
        output_dir = GuiScreeningService().project_workspace(input_dir=self.input_dir_edit.text().strip()).root_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        try:
            if sys.platform.startswith("win"):
                os.startfile(str(output_dir))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(output_dir)])
            else:
                subprocess.Popen(["xdg-open", str(output_dir)])
        except Exception as exc:  # pragma: no cover - OS dependent
            QMessageBox.warning(self, "Open folder failed", str(exc))

    def clear_project_history(self) -> None:
        message = (
            "This will delete current project's SQLite, Excel, CSV and logs.\n"
            "It will NOT delete original papers in input folder.\n\n"
            "Continue?"
        )
        answer = QMessageBox.question(self, "Confirm Clear", message)
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            GuiScreeningService().clear_project_history(input_dir=self.input_dir_edit.text().strip())
            self.append_log("Current project history cleared.")
            self.refresh_all()
            self._refresh_project_info()
        except Exception as exc:
            QMessageBox.warning(self, "Clear failed", str(exc))
