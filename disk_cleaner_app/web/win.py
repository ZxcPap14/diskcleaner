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
_SWP_NOSIZE = 0x0001
_SWP_NOMOVE = 0x0002
_SWP_NOZORDER = 0x0004
_SWP_NOACTIVATE = 0x0010
_SWP_FRAMECHANGED = 0x0020


def handle(window) -> int:
    """HWND окна pywebview (``window.native`` — WinForms-форма)."""
    return int(window.native.Handle.ToInt32())


def _cursor_lparam() -> int:
    """lParam для WM_NCLBUTTONDOWN — экранные координаты курсора.

    С нулём Windows получает точку (0,0), считает её лежащей вне окна и
    вместо ресайза начинает перетаскивать окно целиком.
    """
    pt = wintypes.POINT()
    _user32.GetCursorPos(ctypes.byref(pt))
    return ((pt.y & 0xFFFF) << 16) | (pt.x & 0xFFFF)


class _Margins(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_int), ("right", ctypes.c_int),
        ("top", ctypes.c_int), ("bottom", ctypes.c_int),
    ]


def prepare(window) -> None:
    """Вернуть ресайз и убрать системный заголовок."""
    h = wintypes.HWND(handle(window))
    try:
        style = _user32.GetWindowLongW(h, _GWL_STYLE)
        style = (style | _WS_THICKFRAME) & ~_WS_CAPTION
        _user32.SetWindowLongW(h, _GWL_STYLE, style)
        # Без пересчёта рамки Windows не видит новых границ: у края окна нет
        # зоны ресайза, и захват края превращается в перетаскивание.
        _user32.SetWindowPos(
            h, None, 0, 0, 0, 0,
            _SWP_NOSIZE | _SWP_NOMOVE | _SWP_NOZORDER
            | _SWP_NOACTIVATE | _SWP_FRAMECHANGED,
        )
        # Растягиваем стекло на всю рамку — иначе Win10 рисует вокруг окна
        # чёрную полосу толщиной с зону ресайза.
        _dwm.DwmExtendFrameIntoClientArea(h, ctypes.byref(_Margins(-1, -1, -1, -1)))
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


def _on_ui(window, fn) -> None:
    """Выполнить fn в потоке интерфейса WinForms.

    Захват мыши (SetCapture) и модальный цикл перемещения живут в потоке
    окна: вызов ReleaseCapture из потока pywebview ничего не снимает, и
    окно «не замечает» движение мыши. Поэтому таскание и ресайз — только
    через BeginInvoke в поток формы.
    """
    form = window.native
    try:
        from System import Action  # type: ignore[import-not-found]

        form.BeginInvoke(Action(fn))
    except Exception:
        log.warning("Не удалось выполнить действие в потоке окна", exc_info=True)
        fn()


def begin_drag(window) -> None:
    def drag() -> None:
        _user32.ReleaseCapture()
        _user32.SendMessageW(
            wintypes.HWND(handle(window)), _WM_NCLBUTTONDOWN, _HTCAPTION,
            _cursor_lparam(),
        )

    _on_ui(window, drag)


def begin_resize(window, edge: str) -> None:
    def resize() -> None:
        _user32.ReleaseCapture()
        _user32.SendMessageW(
            wintypes.HWND(handle(window)), _WM_NCLBUTTONDOWN,
            _HT.get(edge, _HTCAPTION), _cursor_lparam(),
        )

    _on_ui(window, resize)


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
