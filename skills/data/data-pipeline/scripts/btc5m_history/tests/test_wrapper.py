"""每日 wrapper 模板测试 — 03-018 UT21。

用替身执行检查 argv / cwd / exit 透传；模板无 LLM / 无外发 / 无回填。
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

# tests/ -> btc5m_history/ -> scripts/ -> templates/
TEMPLATE = (
    Path(__file__).resolve().parents[2]
    / "templates"
    / "yquant-data-btc5m-history-daily.sh"
)


def _template_text() -> str:
    return TEMPLATE.read_text(encoding="utf-8")


def test_ut21_template_exists() -> None:
    assert TEMPLATE.is_file()


def test_ut21_template_uses_strict_mode_and_project_cwd() -> None:
    text = _template_text()
    assert "set -euo pipefail" in text
    assert 'PROJECT_ROOT="/home/pascal/workspace/yquant-investment"' in text
    assert 'cd "${PROJECT_ROOT}"' in text


def test_ut21_template_runs_daily_with_apply() -> None:
    text = _template_text()
    assert "daily --apply" in text
    assert "--max-days-per-source 7" in text
    assert "--wall-seconds 1800" in text
    # 不含回填
    assert "backfill" not in text


def test_ut21_template_uses_project_venv_and_execs() -> None:
    text = _template_text()
    assert "${PROJECT_ROOT}/.venv/bin/python" in text
    assert "exec " in text


def test_ut21_template_has_no_secret_and_no_llm() -> None:
    text = _template_text()
    assert "PM_PREDICT_API_KEY" not in text
    assert "MONGODB_PASSWORD" not in text
    # 不 source 任意秘密文件（只看可执行行，忽略注释）。
    executable = "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    )
    # ``source`` 只允许作为 ``. source``/``source <file>`` 形式出现；
    # ``--max-days-per-source`` 这类参数不算。
    import re as _re

    assert not _re.search(r"(^|[;&|]\s*)source\s+\S", executable)
    assert "curl" not in executable
    assert "http" not in executable.lower()
    for marker in ("openai", "anthropic", "minimax", "llm", "agent"):
        assert marker not in executable.lower()


def test_ut21_template_does_not_schedule_anything() -> None:
    text = _template_text()
    assert "crontab" not in text
    assert "systemctl" not in text
    assert "nohup" not in text
    assert "&" not in text


def test_ut21_template_executes_with_a_stub(monkeypatch, tmp_path) -> None:
    """用替身 ``python`` 执行模板，检查 argv / cwd / exit 透传。"""
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    argv_log = tmp_path / "argv.txt"
    stub = stub_dir / "python"
    stub.write_text(
        "#!/usr/bin/env bash\n"
        f'echo "$@" > "{argv_log}"\n'
        'pwd >> "' + str(argv_log) + '"\n'
        "exit 42\n",
        encoding="utf-8",
    )
    stub.chmod(0o755)

    text = _template_text().replace(
        'PYTHON_BIN="${PROJECT_ROOT}/.venv/bin/python"',
        f'PYTHON_BIN="{stub}"',
    )
    script = tmp_path / "wrapper.sh"
    script.write_text(text, encoding="utf-8")
    script.chmod(0o755)

    result = subprocess.run(
        ["bash", str(script)], capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 42
    logged = argv_log.read_text(encoding="utf-8")
    assert "daily --apply" in logged
    assert "--max-days-per-source 7" in logged
    assert "--wall-seconds 1800" in logged
    assert "/home/pascal/workspace/yquant-investment" in logged


def test_ut21_shanghai_schedule_conversion() -> None:
    """上海 11:00 == UTC 03:00（scheduler 时区未知时给主控的换算依据）。"""
    from datetime import datetime, timedelta, timezone

    shanghai = timezone(timedelta(hours=8))
    utc_03 = datetime(2026, 8, 10, 3, 0, tzinfo=timezone.utc)
    assert utc_03.astimezone(shanghai).hour == 11
    assert utc_03.astimezone(shanghai).minute == 0


def test_ut21_wrapper_does_not_embed_credentials() -> None:
    text = _template_text()
    executable = "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    )
    assert not re.search(r"(?i)password|secret|token|api[_-]?key", executable)
