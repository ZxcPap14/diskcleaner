"""Тесты Docker-чистильщика (docker system prune)."""
from __future__ import annotations

import pytest

from disk_cleaner_app.cleaners.devtools import (
    DockerSystemCleaner,
    _parse_docker_size,
    _run_docker,
)


def test_parse_docker_size_units() -> None:
    assert _parse_docker_size("0B") == 0
    assert _parse_docker_size("12.3MB") == 12_300_000
    assert _parse_docker_size("1.02GB") == 1_020_000_000
    assert _parse_docker_size("85.9kB") == 85_900
    assert _parse_docker_size("2TB") == 2 * 10**12
    assert _parse_docker_size("n/a") == 0
    assert _parse_docker_size("") == 0


def test_docker_cleaner_is_not_a_path_target() -> None:
    assert DockerSystemCleaner().affected_paths() == ()
    assert DockerSystemCleaner().admin_required is False


@pytest.fixture(autouse=True)
def _reset_docker_size_cache():
    """Кэш ответа daemon — классовое состояние, изолируем тесты."""
    DockerSystemCleaner._size_cache = None
    yield
    DockerSystemCleaner._size_cache = None


def test_size_is_cached_within_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_docker(args: list[str], timeout: int = 60) -> tuple[str, str]:
        calls.append(args)
        if args[0] == "info":
            return ("27.3.1", "")
        return ("Images\t1.02GB (52%)", "")

    monkeypatch.setattr(
        "disk_cleaner_app.cleaners.devtools._run_docker", fake_docker
    )
    cleaner = DockerSystemCleaner()

    assert cleaner.get_size() == 1_020_000_000
    assert cleaner.get_size() == 1_020_000_000
    # Второй вызов берётся из кэша: daemon опрошен один раз (info + df).
    assert len(calls) == 2

    cleaner.clean()  # очистка сбрасывает кэш
    assert DockerSystemCleaner._size_cache is None


def test_size_is_zero_when_docker_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "disk_cleaner_app.cleaners.devtools._run_docker",
        lambda args, timeout=60: ("", "docker: command not found"),
    )
    cleaner = DockerSystemCleaner()

    assert cleaner.get_size() == 0
    assert "не запущен" in cleaner.scan_error


def test_size_sums_reclaimable(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_docker(args: list[str], timeout: int = 60) -> tuple[str, str]:
        calls.append(args)
        if args[0] == "info":
            return ("27.3.1", "")
        assert args[:2] == ["system", "df"]
        return (
            "Images\t1.02GB (52%)\n"
            "Containers\t12.3MB (10%)\n"
            "Local Volumes\t0B (0%)\n"
            "Build Cache\t85.9kB\n"
            "malformed line without tab",
            "",
        )

    monkeypatch.setattr(
        "disk_cleaner_app.cleaners.devtools._run_docker", fake_docker
    )
    cleaner = DockerSystemCleaner()

    assert cleaner.get_size() == 1_020_000_000 + 12_300_000 + 85_900
    assert cleaner.scan_error == ""


def test_clean_parses_reclaimed_space(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_docker(args: list[str], timeout: int = 60) -> tuple[str, str]:
        if args[0] == "info":
            return ("27.3.1", "")
        return ("Deleted Containers:\n  abc\nTotal Reclaimed space: 1.5GB", "")

    monkeypatch.setattr(
        "disk_cleaner_app.cleaners.devtools._run_docker", fake_docker
    )

    status, details = DockerSystemCleaner().clean()

    assert status == "OK"
    assert "1.5GB" in details


def test_clean_reports_error_when_prune_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_docker(args: list[str], timeout: int = 60) -> tuple[str, str]:
        if args[0] == "info":
            return ("27.3.1", "")
        return ("", "Error response from daemon: something broke")

    monkeypatch.setattr(
        "disk_cleaner_app.cleaners.devtools._run_docker", fake_docker
    )

    status, details = DockerSystemCleaner().clean()

    assert status == "ERR"
    assert "something broke" in details


def test_clean_err_when_docker_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "disk_cleaner_app.cleaners.devtools._run_docker",
        lambda args, timeout=60: ("", "error during connect"),
    )

    status, details = DockerSystemCleaner().clean()

    assert status == "ERR"
    assert "не запущен" in details


def test_run_docker_without_binary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "disk_cleaner_app.cleaners.devtools.shutil.which", lambda name: None
    )

    assert _run_docker(["info"]) == ("", "DOCKER_NOT_INSTALLED")
