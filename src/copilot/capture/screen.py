from __future__ import annotations

import io

from copilot.capture.window import ActiveWindow, get_active_window
from copilot.config import Settings
from copilot.domain.models import RawCapture


class CaptureService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def capture(self) -> RawCapture:
        """Captura a janela ativa quando o SO informa o retangulo dela; senao,
        o monitor principal. A imagem existe so em memoria."""
        import mss
        from PIL import Image

        window = get_active_window()
        with mss.mss() as screen:
            region = self._region_for(window, screen)
            shot = screen.grab(region)
            image = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")

        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return RawCapture(
            png=buffer.getvalue(),
            width=image.width,
            height=image.height,
            window_title=window.title,
            process_name=window.process_name,
        )

    @staticmethod
    def _region_for(window: ActiveWindow, screen) -> dict:
        primary = screen.monitors[1] if len(screen.monitors) > 1 else screen.monitors[0]
        if not window.rect:
            return primary
        left, top, right, bottom = window.rect
        if right - left < 200 or bottom - top < 200:
            return primary
        return {"left": left, "top": top, "width": right - left, "height": bottom - top}

    def in_scope(self, window_title: str | None, process_name: str | None) -> bool:
        haystack = f"{window_title or ''} {process_name or ''}".lower()
        return any(p in haystack for p in self._settings.scope_patterns)
