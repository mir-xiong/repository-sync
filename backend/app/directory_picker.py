from __future__ import annotations

import shutil
import subprocess
import sys
import threading
from pathlib import Path

class DirectoryPickerError(Exception):
    pass


class DirectoryPickerBusy(Exception):
    pass


_lock = threading.Lock()

_MAC_SCRIPT = """
on run argv
  set startPath to item 1 of argv
  try
    set picked to choose folder with prompt "选择本地镜像目录" default location (POSIX file startPath)
    return POSIX path of picked
  on error errMsg number errNum
    if errNum is -128 then
      return ""
    end if
    error errMsg number errNum
  end try
end run
"""


def pick_directory(default: Path) -> str | None:
    if not _lock.acquire(blocking=False):
        raise DirectoryPickerBusy("目录选择窗口已经打开")
    try:
        start = default if default.is_dir() else Path.home()
        if sys.platform == "darwin":
            return _from_completed(_run_macos(start))
        zenity = shutil.which("zenity")
        if zenity:
            return _from_completed(_run_zenity(zenity, start), cancel_codes={1})
        raise DirectoryPickerError("当前系统打不开目录选择窗口，请直接填写路径")
    finally:
        _lock.release()


def _run_macos(start: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["osascript", "-e", _MAC_SCRIPT, str(start)],
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )


def _run_zenity(zenity: str, start: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [zenity, "--file-selection", "--directory", "--title=选择本地镜像目录", f"--filename={start}/"],
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )


def _from_completed(completed: subprocess.CompletedProcess[str], cancel_codes: set[int] | None = None) -> str | None:
    if completed.returncode in (cancel_codes or set()):
        return None
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "无法打开目录选择窗口").strip()
        raise DirectoryPickerError(detail)
    raw = completed.stdout.strip()
    if not raw:
        return None
    return str(Path(raw).expanduser().resolve())
