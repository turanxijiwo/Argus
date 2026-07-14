"""Safe gallery-dl wrapper for Argus research media downloads."""

import os
import shutil
import subprocess
from typing import Any, Dict
from urllib.parse import urlparse

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
    target = str(target or "").strip()
    if not _is_http_url(target):
        return _err(
            "target must be a non-empty http/https URL",
            code="INVALID_TARGET",
        )

    resolved_output = resolve_gallery_output_dir(project_root, output_dir)
    if not resolved_output.get("success"):
        return resolved_output

    output_path = resolved_output["data"]["path"]
    command = [
        binary,
        "--config-ignore",
        "--directory",
        output_path,
        "--",
        target,
    ]
    plan = {
        "command": command,
        "cwd": output_path,
        "target": target,
        "confirm_required": not confirm,
    }
    if not confirm:
        return _ok(
            plan,
            mode="dry_run",
            note="Set confirm=True to run gallery-dl inside the project output directory",
        )

    os.makedirs(output_path, exist_ok=True)
    timeout = _safe_int(timeout, 300, 30, 1800)
    try:
        completed = subprocess.run(
            command,
            cwd=output_path,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return _err("gallery-dl timed out", code="TIMEOUT", timeout=timeout)
    except Exception as ex:
        return _err(f"gallery-dl failed to start: {ex}", code="EXEC_ERROR")

    process_result = {
        **plan,
        "returncode": completed.returncode,
        "stdout": (completed.stdout or "")[-5000:],
        "stderr": (completed.stderr or "")[-5000:],
    }
    if completed.returncode != 0:
        return _err(
            "gallery-dl download failed",
            code="DOWNLOAD_FAILED",
            **process_result,
        )

    return _ok(
        process_result,
        mode="executed",
        success_exit=True,
    )


def resolve_gallery_output_dir(project_root: str, output_dir: str) -> Dict:
    return resolve_output_dir(project_root, output_dir or "output/media")


def _is_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


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
