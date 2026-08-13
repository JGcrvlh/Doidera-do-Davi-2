"""Metadados da janela ativa, por plataforma. Alimenta o filtro de escopo e o
recorte da captura. Sempre degrada com graca: sem info de janela, captura-se o
monitor e o filtro pede confirmacao."""

from __future__ import annotations

import sys
from dataclasses import dataclass


@dataclass
class ActiveWindow:
    title: str | None = None
    process_name: str | None = None
    rect: tuple[int, int, int, int] | None = None  # left, top, right, bottom


def get_active_window() -> ActiveWindow:
    try:
        if sys.platform == "win32":
            return _windows()
        if sys.platform == "darwin":
            return _macos()
        return _linux()
    except Exception:
        return ActiveWindow()


def _windows() -> ActiveWindow:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return ActiveWindow()

    length = user32.GetWindowTextLengthW(hwnd)
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, length + 1)

    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))

    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    process_name = _windows_process_name(pid.value)

    return ActiveWindow(
        title=buffer.value or None,
        process_name=process_name,
        rect=(rect.left, rect.top, rect.right, rect.bottom),
    )


def _windows_process_name(pid: int) -> str | None:
    import ctypes

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        buffer = ctypes.create_unicode_buffer(1024)
        size = ctypes.c_ulong(1024)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return buffer.value.rsplit("\\", 1)[-1]
        return None
    finally:
        kernel32.CloseHandle(handle)


def _macos() -> ActiveWindow:
    from AppKit import NSWorkspace  # type: ignore[import-not-found]

    app = NSWorkspace.sharedWorkspace().frontmostApplication()
    return ActiveWindow(title=str(app.localizedName()), process_name=str(app.localizedName()))


def _linux() -> ActiveWindow:
    import subprocess

    out = subprocess.run(
        ["xdotool", "getactivewindow", "getwindowname"],
        capture_output=True, text=True, timeout=2,
    )
    title = out.stdout.strip() or None
    return ActiveWindow(title=title)
