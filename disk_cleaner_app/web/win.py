"""Окно без системного заголовка: тёмная рамка, перетаскивание, ресайз.

WinForms-форма pywebview с ``FormBorderStyle.None`` теряет и рамку ресайза.
Возвращаем её так, как это делает любое приложение со своим тайтлбаром:
оставляем ``WS_THICKFRAME`` (за него отвечает изменение размера) и убираем
``WS_CAPTION`` (за него отвечает наша вёрстка).
"""
from __future__ import annotations

import ctypes
import logging
from ctypes import wintypes

log = logging.getLogger(__name__)

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_dwm = ctypes.WinDLL("dwmapi", use_last_error=True)

_GWL_STYLE = -16
_WS_CAPTION = 0x00C00000
_WS_THICKFRAME = 0x00040000
_WM_NCLBUTTONDOWN = 0x00A1
_HTCAPTION = 2
_HT = {
    "left": 10, "right": 11, "top": 12, "topleft": 13, "topright": 14,
    "bottom": 15, "bottomleft": 16, "bottomright": 17,
}
_SW_MAXIMIZE = 3
_SW_RESTORE = 9


def handle(window) -> int:
    """HWND окна pywebview (``window.native`` — WinForms-форма)."""
    return int(window.native.Handle.ToInt32())


def prepare(window) -> None:
    """Вернуть ресайз и убрать системный заголовок."""
    h = handle(window)
    try:
        style = _user32.GetWindowLongW(wintypes.HWND(h), _GWL_STYLE)
        style = (style | _WS_THICKFRAME) & ~_WS_CAPTION
        _user32.SetWindowLongW(wintypes.HWND(h), _GWL_STYLE, style)
    except Exception:
        log.warning("Не удалось перестроить стиль окна", exc_info=True)


def set_dark_frame(window, dark: bool = True) -> None:
    """Тёмный невидимый каркас: без него Win10 подсвечивает окно белым."""
    value = ctypes.c_int(1 if dark else 0)
    try:
        _dwm.DwmSetWindowAttribute(
            wintypes.HWND(handle(window)), 20, ctypes.byref(value), 4
        )
    except Exception:
        log.debug("DWMWA_USE_IMMERSIVE_DARK_MODE недоступен", exc_info=True)


def begin_drag(window) -> None:
    h = handle(window)
    _user32.ReleaseCapture()
    _user32.SendMessageW(wintypes.HWND(h), _WM_NCLBUTTONDOWN, _HTCAPTION, 0)


def begin_resize(window, edge: str) -> None:
    h = handle(window)
    _user32.ReleaseCapture()
    _user32.SendMessageW(
        wintypes.HWND(h), _WM_NCLBUTTONDOWN, _HT.get(edge, _HTCAPTION), 0
    )


def toggle_maximize(window) -> bool:
    h = wintypes.HWND(handle(window))
    if _user32.IsZoomed(h):
        _user32.ShowWindow(h, _SW_RESTORE)
        return False
    _user32.ShowWindow(h, _SW_MAXIMIZE)
    return True


def minimize(window) -> None:
    h = wintypes.HWND(handle(window))
    _user32.ShowWindow(h, 6)  # SW_MINIMIZE
