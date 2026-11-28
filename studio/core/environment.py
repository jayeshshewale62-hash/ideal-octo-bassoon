"""Environment checks for ``studio doctor``.

Reports what this machine can do. It never installs or downloads anything, and nothing
in the foundation needs a GPU.
"""

from __future__ import annotations

import importlib.util
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str
    required: bool

    @property
    def state(self) -> str:
        if self.ok:
            return "ok"
        return "MISSING" if self.required else "optional-missing"


def _tool_version(tool: str) -> Check:
    path = shutil.which(tool)
    required = False  # FFmpeg becomes required from Milestone 7 (rendering)
    if not path:
        return Check(
            tool, False, "not on PATH (needed for rendering in later milestones)", required
        )
    try:
        out = subprocess.run(
            [path, "-version"], capture_output=True, text=True, timeout=10, check=False
        )
        first = out.stdout.splitlines()[0] if out.stdout else "unknown version"
    except (OSError, subprocess.TimeoutExpired) as exc:
        return Check(tool, False, f"failed to run: {exc}", required)
    return Check(tool, True, first, required)


def _module(name: str, label: str, required: bool, purpose: str) -> Check:
    found = importlib.util.find_spec(name) is not None
    detail = "importable" if found else f"not installed ({purpose})"
    if found and name == "skia":
        try:
            import skia

            detail = f"skia-python {getattr(skia, '__version__', '?')}"
        except Exception as exc:
            return Check(label, False, f"installed but failed to import: {exc}", required)
    return Check(label, found, detail, required)


def run_checks() -> list[Check]:
    checks = [
        Check(
            "python",
            sys.version_info >= (3, 12),
            f"{platform.python_implementation()} {platform.python_version()} ({sys.platform})",
            True,
        ),
        _module("pydantic", "pydantic", True, "core dependency"),
        _module("yaml", "PyYAML", True, "core dependency"),
        _module(
            "skia", "skia-python", False, "optional 'render' extra; core renderer from Milestone 3"
        ),
        _module("numpy", "numpy", False, "optional 'render' extra"),
        _tool_version("ffmpeg"),
        _tool_version("ffprobe"),
    ]
    gpu = shutil.which("nvidia-smi") is not None
    checks.append(
        Check("gpu", True, "NVIDIA tools found" if gpu else "none detected (not required)", False)
    )
    return checks
