from __future__ import annotations

from typing import Protocol

from copilot.domain.models import OcrResult, RawCapture


class OcrService(Protocol):
    def run(self, capture: RawCapture) -> OcrResult: ...
