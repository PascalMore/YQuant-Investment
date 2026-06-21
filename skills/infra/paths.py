"""Project path helpers shared by OpenClaw and Hermes runtimes."""

import os
from pathlib import Path


def _find_workspace_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / "AGENTS.md").exists() and (candidate / "skills").is_dir():
            return candidate
    return Path("/home/pascal/.openclaw/workspace-yquant").resolve()


def workspace_root() -> Path:
    """Return the YQuant workspace root.

    YQUANT_WORKSPACE can pin the root for Hermes profiles, cron jobs, or tests.
    Without it, the path is inferred from this file so the legacy OpenClaw
    symlink and the standalone workspace both resolve to the same project.
    """
    configured = os.getenv("YQUANT_WORKSPACE")
    if configured:
        return Path(configured).expanduser().resolve()
    return _find_workspace_root(Path(__file__).resolve())


def skills_dir() -> Path:
    return workspace_root() / "skills"


def logs_dir() -> Path:
    return workspace_root() / "logs"


def state_dir(name: str = ".openclaw") -> Path:
    return workspace_root() / name


def shared_env_path() -> Path:
    return skills_dir() / ".env"


def report_marker_path(*parts: str) -> Path:
    return skills_dir().joinpath("reports", *parts, ".last_sent")


WORKSPACE_ROOT = workspace_root()
SKILLS_DIR = skills_dir()
LOGS_DIR = logs_dir()
SHARED_ENV_PATH = shared_env_path()
