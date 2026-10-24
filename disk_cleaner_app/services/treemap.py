"""TreemapData — сбор иерархических данных для Treemap."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class TreemapNode:
    """Узел treemap: папка или файл."""
    name: str
    path: str
    size: int
    is_dir: bool = True
    children: list[TreemapNode] = field(default_factory=list)
    # Для squarify
    x: float = 0
    y: float = 0
    w: float = 0
    h: float = 0


class TreemapData:
    """Сбор данных для treemap."""

    def __init__(self) -> None:
        self._history: list[list[TreemapNode]] = []  # стек для drill-back

    def scan_root(self, path: str = "C:\\", limit: int = 30) -> list[TreemapNode]:
        """Отсканировать корневые папки в path."""
        self._history.clear()
        nodes: list[TreemapNode] = []
        try:
            with os.scandir(path) as it:
                for e in it:
                    try:
                        if e.is_dir(follow_symlinks=False) and not e.name.startswith("$"):
                            sz = self._get_dir_size(Path(e.path))
                            if sz > 0:
                                nodes.append(TreemapNode(
                                    name=e.name,
                                    path=e.path,
                                    size=sz,
                                    is_dir=True,
                                ))
                    except (OSError, PermissionError):
                        continue
        except (OSError, PermissionError):
            pass

        nodes.sort(key=lambda n: n.size, reverse=True)
        self._history.append(nodes)
        return nodes[:limit]

    def drill_down(self, node: TreemapNode, limit: int = 30) -> list[TreemapNode]:
        """Спуститься в папку: показать её содержимое как treemap."""
        children: list[TreemapNode] = []
        try:
            with os.scandir(node.path) as it:
                for e in it:
                    try:
                        if e.is_dir(follow_symlinks=False):
                            sz = self._get_dir_size(Path(e.path))
                            if sz > 0:
                                children.append(TreemapNode(
                                    name=e.name,
                                    path=e.path,
                                    size=sz,
                                    is_dir=True,
                                ))
                        elif e.is_file(follow_symlinks=False):
                            st = e.stat()
                            if st.st_size > 1024 * 1024:  # >1 MB
                                children.append(TreemapNode(
                                    name=e.name,
                                    path=e.path,
                                    size=st.st_size,
                                    is_dir=False,
                                ))
                    except (OSError, PermissionError):
                        continue
        except (OSError, PermissionError):
            pass

        children.sort(key=lambda n: n.size, reverse=True)
        self._history.append(children)
        return children[:limit]

    def can_go_back(self) -> bool:
        return len(self._history) > 1

    def go_back(self, limit: int = 30) -> list[TreemapNode] | None:
        """Вернуться на уровень выше."""
        if len(self._history) <= 1:
            return None
        self._history.pop()  # текущий
        return self._history[-1][:limit] if self._history[-1] else None

    def _get_dir_size(self, path: Path) -> int:
        """Рекурсивно подсчитать размер папки (с кэшированием для повторных вызовов)."""
        total = 0
        try:
            with os.scandir(str(path)) as it:
                for e in it:
                    try:
                        if e.is_dir(follow_symlinks=False):
                            total += self._get_dir_size(Path(e.path))
                        elif e.is_file(follow_symlinks=False):
                            total += e.stat().st_size
                    except (OSError, PermissionError):
                        continue
        except (OSError, PermissionError):
            pass
        return total
