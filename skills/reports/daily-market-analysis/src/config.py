# -*- coding: utf-8 -*-
"""
daily-market-analysis 共享配置加载器

设计目标：
- 敏感字段（API key / SMTP 凭据 / 收件人）从 .env 读取，.env 已被 .gitignore。
- 非敏感运行时配置（enabled / SMTP 服务器 / 端口 / 排程 / 自选股 / AI 模型）
  保留在 config.json 并入仓库。
- 系统环境变量优先于 .env（load_dotenv(override=False)），便于 CI / cron 注入。
- 邮件推送启用时校验三项必填字段，缺失立即 SystemExit，避免静默失败。

字段映射（config.json key → .env 变量）：
- data_sources.tavily.api_key          ← TAVILY_API_KEY
- data_sources.gnews.api_key           ← GNEWS_API_KEY
- data_sources.tradingeconomics.api_key← TRADING_ECONOMICS_API_KEY
- push.email.username                   ← EMAIL_USERNAME
- push.email.password                   ← EMAIL_PASSWORD
- push.email.recipients                 ← EMAIL_RECIPIENTS（逗号分隔）
"""

import json
import os
from pathlib import Path
from typing import List

from dotenv import load_dotenv

SKILL_DIR = Path(__file__).resolve().parents[1]
CONFIG_PATH = SKILL_DIR / "config.json"
ENV_PATH = SKILL_DIR / ".env"

_API_KEY_FIELDS = (
    ("tavily", "TAVILY_API_KEY"),
    ("gnews", "GNEWS_API_KEY"),
    ("tradingeconomics", "TRADING_ECONOMICS_API_KEY"),
)
_EMAIL_FIELDS = (
    ("username", "EMAIL_USERNAME"),
    ("password", "EMAIL_PASSWORD"),
    ("recipients", "EMAIL_RECIPIENTS"),
)


def _read_config_json() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def _parse_recipients(raw: str) -> List[str]:
    return [r.strip() for r in (raw or "").split(",") if r.strip()]


def _assert_email_complete(cfg: dict) -> None:
    em = cfg.get("push", {}).get("email", {})
    if not em.get("enabled"):
        return
    missing = [k for k, _ in _EMAIL_FIELDS if not em.get(k)]
    if missing:
        names = "/".join(env for _, env in _EMAIL_FIELDS if _ not in missing)
        raise SystemExit(
            "daily-market-analysis: 邮件推送已启用但缺少配置 "
            f"{missing}。请在 .env 设置 "
            "EMAIL_USERNAME / EMAIL_PASSWORD / EMAIL_RECIPIENTS"
        )


def load_skill_config() -> dict:
    """
    合并 config.json（运行时配置）+ 系统环境 / .env（敏感字段），
    返回可直接被 main.py / report_generator.py 使用的 cfg dict。
    """
    cfg = _read_config_json()
    load_dotenv(ENV_PATH, override=False)

    data_sources = cfg.setdefault("data_sources", {})
    for key, env_var in _API_KEY_FIELDS:
        node = data_sources.setdefault(key, {})
        node["api_key"] = os.getenv(env_var, node.get("api_key", "") or "")

    email = cfg.setdefault("push", {}).setdefault("email", {})
    email["username"] = os.getenv("EMAIL_USERNAME", email.get("username", "") or "")
    email["password"] = os.getenv("EMAIL_PASSWORD", email.get("password", "") or "")
    email["recipients"] = _parse_recipients(
        os.getenv("EMAIL_RECIPIENTS", "") or email.get("recipients", "")
    )

    _assert_email_complete(cfg)
    return cfg


if __name__ == "__main__":
    # 单独运行：打印当前生效的 cfg（自动脱敏 api_key / password）
    import pprint

    cfg = load_skill_config()
    sanitized = {
        "data_sources": {
            k: {**v, "api_key": "***" if v.get("api_key") else ""}
            for k, v in cfg.get("data_sources", {}).items()
        },
        "push": {
            "email": {
                **cfg.get("push", {}).get("email", {}),
                "password": "***" if cfg.get("push", {}).get("email", {}).get("password") else "",
            }
        },
    }
    pprint.pprint(sanitized)