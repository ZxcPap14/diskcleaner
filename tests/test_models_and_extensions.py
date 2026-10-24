"""Модели и расширения — не кэш: отдельный слой, не входят в безопасный набор."""
from __future__ import annotations

import pytest

from disk_cleaner_app.cleaners.aiml import AIML_CLEANERS
from disk_cleaner_app.cleaners.devtools import (
    DEVTOOLS_CLEANERS,
    AntigravityExtensionsCleaner,
)
from disk_cleaner_app.models.item import SafetyLevel
from disk_cleaner_app.models.target import (
    LAYER_COMPONENTS,
    LAYER_SAFE,
    LAYERS,
    TargetSpec,
)


@pytest.mark.parametrize("cls", AIML_CLEANERS)
def test_models_are_components_not_safe_caches(cls) -> None:
    cleaner = cls()

    assert cleaner.layer == LAYER_COMPONENTS
    assert cleaner.recommended is False
    assert cleaner.safety == SafetyLevel.ADVANCED


def test_antigravity_extensions_are_not_registered() -> None:
    assert AntigravityExtensionsCleaner not in DEVTOOLS_CLEANERS
    assert all(
        cleaner.id != "antigravity_ext"
        for cleaner in (cls() for cls in DEVTOOLS_CLEANERS)
    )


def test_antigravity_class_refuses_to_clean() -> None:
    status, detail = AntigravityExtensionsCleaner().clean()

    assert status == "SKIP"
    assert "расширени" in detail


def test_safe_set_has_no_models_or_extensions() -> None:
    from disk_cleaner_app.cleaners.registry import CleanerRegistry

    class _Config:
        def load_custom_rules(self):
            return []

    registry = CleanerRegistry(_Config())
    safe = [
        cleaner
        for cleaner in registry.get_all(include_auto=False)
        if cleaner.layer == LAYER_SAFE and cleaner.recommended
    ]
    ids = {cleaner.id for cleaner in safe}

    assert "antigravity_ext" not in ids
    for cls in AIML_CLEANERS:
        assert cls().id not in ids


def test_target_spec_rejects_unknown_layer() -> None:
    with pytest.raises(ValueError):
        TargetSpec(id="x", name="X", group="g", layer="Z")


def test_target_spec_rejects_unknown_kind() -> None:
    with pytest.raises(ValueError):
        TargetSpec(id="x", name="X", group="g", kind="magic")


def test_target_spec_requires_roots_for_file_targets() -> None:
    with pytest.raises(ValueError):
        TargetSpec(id="x", name="X", group="g", kind="dir_contents")


def test_target_spec_accepts_command_without_roots() -> None:
    spec = TargetSpec(id="dns", name="DNS", group="g", kind="command")

    assert spec.layer in LAYERS
    assert spec.kind == "command"
