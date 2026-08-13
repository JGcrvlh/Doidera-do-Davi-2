from __future__ import annotations

from collections.abc import Callable


class HotkeyManager:
    """Atalhos globais via pynput. Callbacks rodam no thread do listener —
    devem apenas agendar trabalho (ex.: loop.call_soon_threadsafe)."""

    def __init__(self) -> None:
        self._bindings: dict[str, Callable[[], None]] = {}
        self._listener = None

    def bind(self, combo: str, callback: Callable[[], None]) -> None:
        self._bindings[combo] = callback

    def start(self) -> None:
        from pynput import keyboard

        self._listener = keyboard.GlobalHotKeys(dict(self._bindings))
        self._listener.daemon = True
        self._listener.start()

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
