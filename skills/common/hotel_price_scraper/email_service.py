from __future__ import annotations

import importlib.util
import os
from pathlib import Path


SKILLS_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_PATH = SKILLS_ROOT / ".env"
EMAIL_MODULE_PATH = SKILLS_ROOT / "common" / "utils" / "email" / "send_email.py"


class EmailService:
    def __init__(self, env_path: str | Path = DEFAULT_ENV_PATH) -> None:
        self.env_path = Path(env_path)
        self._load_env()

    def send_report(self, subject: str, content: str, attachment_path: str | Path) -> bool:
        receivers = os.getenv("EMAIL_RECEIVERS", "")
        if not receivers:
            raise RuntimeError("EMAIL_RECEIVERS is not configured")
        module = self._load_email_module()
        return bool(module.send_email(receivers, subject, content, str(attachment_path)))

    def _load_env(self) -> None:
        if not self.env_path.exists():
            return
        for line in self.env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
        os.environ.setdefault("EMAIL_SENDER_NAME", "YQClaw智能投资助手")

    def _load_email_module(self):
        spec = importlib.util.spec_from_file_location("yquant_send_email", EMAIL_MODULE_PATH)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load email module: {EMAIL_MODULE_PATH}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
