"""🤖 AI/ML: модели, а не кэш. По умолчанию не выбираются."""
from __future__ import annotations

from pathlib import Path

from disk_cleaner_app.cleaners.base import BaseCleaner, get_dir_size, safe_rm_contents
from disk_cleaner_app.models.item import GROUP_AIML, SafetyLevel
from disk_cleaner_app.models.target import LAYER_COMPONENTS

USER = Path.home()


class _ModelCleaner(BaseCleaner):
    group = GROUP_AIML
    safety = SafetyLevel.ADVANCED
    layer = LAYER_COMPONENTS
    recommended = False
    delete_mode = "remove"
    why = "Это скачанная модель, а не временный кэш."
    loss = "После удаления модель придётся скачать заново."
    restore_hint = "Загрузите модель через приложение или huggingface-cli."

    def affected_paths(self) -> tuple[Path, ...]:
        return tuple(p for p in self.paths if p.exists())

    def get_size(self) -> int:
        return sum(get_dir_size(p) for p in self.affected_paths())

    def clean(self) -> tuple[str, str]:
        ok = all(safe_rm_contents(p) for p in self.affected_paths())
        return ("OK", f"{self.name} очищены") if ok else ("ERR", "Ошибка")


class WhisperCacheCleaner(_ModelCleaner):
    id = "whisper"
    name = "🎤 Whisper Models"
    description = "%USER%\\.cache\\whisper"
    paths = (USER / ".cache" / "whisper",)
    restore_hint = "Модель скачается заново при следующем запуске Whisper."


class HuggingFaceCacheCleaner(_ModelCleaner):
    id = "huggingface"
    name = "🤗 HuggingFace Models"
    description = "%USER%\\.cache\\huggingface\\hub"
    paths = (USER / ".cache" / "huggingface" / "hub",)
    why = "Это скачанные модели; токен и настройки HuggingFace не трогаем."
    restore_hint = "huggingface-cli download <model>"


class LMStudioCacheCleaner(_ModelCleaner):
    id = "lmstudio"
    name = "🤖 LM Studio Models"
    description = "%USER%\\.lmstudio\\models"
    paths = (USER / ".lmstudio" / "models",)
    restore_hint = "Скачайте модель заново в LM Studio."


class OllamaModelsCleaner(_ModelCleaner):
    id = "ollama"
    name = "🦙 Ollama Models"
    description = "%USER%\\.ollama\\models"
    paths = (USER / ".ollama" / "models",)
    restore_hint = "ollama pull <model>"


AIML_CLEANERS: list[type[BaseCleaner]] = [
    WhisperCacheCleaner,
    HuggingFaceCacheCleaner,
    LMStudioCacheCleaner,
    OllamaModelsCleaner,
]
