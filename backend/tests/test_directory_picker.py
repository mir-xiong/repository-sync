from __future__ import annotations

import subprocess
from pathlib import Path

from app.directory_picker import pick_directory


def test_macos_picker_returns_selected_folder(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("app.directory_picker.sys.platform", "darwin")

    def fake_run(args, **kwargs):
        assert args[0] == "osascript"
        assert args[-1] == str(tmp_path)
        return subprocess.CompletedProcess(args, 0, stdout=f"{tmp_path}/\n", stderr="")

    monkeypatch.setattr("app.directory_picker.subprocess.run", fake_run)
    assert pick_directory(tmp_path) == str(tmp_path.resolve())


def test_macos_picker_cancel_returns_none(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("app.directory_picker.sys.platform", "darwin")
    monkeypatch.setattr(
        "app.directory_picker.subprocess.run",
        lambda args, **kwargs: subprocess.CompletedProcess(args, 0, stdout="", stderr=""),
    )
    assert pick_directory(tmp_path) is None
