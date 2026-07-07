"""Safe gallery-dl wrapper for Argus research media downloads."""

import os
import shutil
import subprocess
from typing import Any, Dict

from .research_io import resolve_output_dir


def download_gallery(
    project_root: str,
    target: str,
    output_dir: str = "output/media",
    confirm: bool = False,
    timeout: int = 300,
) -> Dict:
    """
    Build or execute a safe gallery-dl command inside the project directory.

    By default this returns a dry-run plan. Execution only happens when
    confirm=True, and output is constrained to project_root.
    """
    binary = shutil.which("gallery-dl")
    if not binary:
        return _err(
            "gallery-dl is not installed",
            code="NOT_INSTALLED",
            install_hint="uv tool install gallery-dl",
        )
    if not target:
        return _err("target cannot be empty", code="INVALID_TARGET")

    resolved_output = resolve_gallery_output_dir(project_root, output_dir)
    if not resolved_output.get("success"):
        return resolved_output

    command = [binary, target]
    plan = {
        "command": command,
        "cwd": resolved_output["data"]["path"],
        "target": target,
        "confirm_required": not confirm,
    }
    if not confirm:
        return _ok(
            plan,
            mode="dry_run",
            note="Set confirm=True to run gallery-dl inside the project output directory",
        )

    os.makedirs(resolved_output["data"]["path"], exist_ok=True)
    timeout = _safe_int(timeout, 300, 30, 1800)
    try:
        completed = subprocess.run(
            command,
            cwd=resolved_output["data"]["path"],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return _err("gallery-dl timed out", code="TIMEOUT", timeout=timeout)
    except Exception as ex:
        return _err(f"gallery-dl failed to start: {ex}", code="EXEC_ERROR")

    return _ok(
        {
            **plan,
            "returncode": completed.returncode,
            "stdout": (completed.stdout or "")[-5000:],
            "stderr": (completed.stderr or "")[-5000:],
        },
        mode="executed",
        success_exit=completed.returncode == 0,
    )


def resolve_gallery_output_dir(project_root: str, output_dir: str) -> Dict:
    return resolve_output_dir(project_root, output_dir or "output/media")


def _safe_int(value: int, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(number, maximum))


def _ok(data: Any, **summary) -> Dict:
    return {"success": True, "summary": summary, "data": data}


def _err(message: str, code: str = "RESEARCH_GALLERY_ERROR", **extra) -> Dict:
    return {"success": False, "error": {"code": code, "message": message, **extra}}
