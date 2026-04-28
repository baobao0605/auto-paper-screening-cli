"""Background worker for running screening without blocking the GUI."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from src.gui_service import CancelToken, GuiScreeningService, RuntimeOverrides
from src.gui.summary_utils import summary_to_dict


class ScreeningWorker(QObject):
    started_signal = Signal(dict)
    log_signal = Signal(str)
    paper_started_signal = Signal(dict)
    paper_finished_signal = Signal(dict)
    paper_error_signal = Signal(dict)
    finished_signal = Signal(dict)
    cancelled_signal = Signal(dict)
    failed_signal = Signal(str)

    def __init__(
        self,
        config_path: Path | None,
        overrides: RuntimeOverrides,
        cancel_token: CancelToken,
    ) -> None:
        super().__init__()
        self.config_path = config_path
        self.overrides = overrides
        self.cancel_token = cancel_token

    @Slot()
    def run(self) -> None:
        try:
            service = GuiScreeningService(self.config_path)
            summary = service.run_screening(
                overrides=self.overrides,
                cancel_token=self.cancel_token,
                on_log=lambda message: self.log_signal.emit(message),
                on_started=lambda payload: self.started_signal.emit(payload),
                on_paper_started=lambda payload: self.paper_started_signal.emit(payload),
                on_paper_finished=lambda payload: self.paper_finished_signal.emit(payload),
                on_paper_error=lambda payload: self.paper_error_signal.emit(payload),
            )
            payload = summary_to_dict(summary)
            if self.cancel_token.is_cancelled():
                self.cancelled_signal.emit(payload)
            else:
                self.finished_signal.emit(payload)
        except Exception as exc:  # pragma: no cover - GUI runtime behavior
            self.failed_signal.emit(str(exc))
