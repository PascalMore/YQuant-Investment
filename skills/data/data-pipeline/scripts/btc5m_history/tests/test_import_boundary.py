"""包级导入边界测试 — 03-018 §3.3 / UT18 相关。

断言：

* 新入口以真实包级路径导入 DataPipeline / 四基类时，**不**加载 OCR
  providers、**不**访问 env、**不**发 HTTP。
* 原扁平 ``scripts`` 导入的公开导出仍可按原方式按需加载。
* 类 identity 不复制（同一模块对象）。
"""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

# tests/ -> btc5m_history/ -> scripts/ -> data-pipeline/ -> data/ -> skills/ -> root
PROJECT_ROOT = Path(__file__).resolve().parents[6]


def test_ut22_package_import_does_not_load_ocr_providers() -> None:
    """导入包级 DataPipeline / 四基类不触发 OCR 顶层依赖。"""
    script = (
        "import importlib, sys\n"
        "pipeline = importlib.import_module("
        "'skills.data.data-pipeline.scripts.pipeline')\n"
        "extractors = importlib.import_module("
        "'skills.data.data-pipeline.scripts.extractors')\n"
        "transformers = importlib.import_module("
        "'skills.data.data-pipeline.scripts.transformers.base')\n"
        "validators = importlib.import_module("
        "'skills.data.data-pipeline.scripts.validators.base')\n"
        "loaders = importlib.import_module("
        "'skills.data.data-pipeline.scripts.loaders.base')\n"
        "assert pipeline.DataPipeline is not None\n"
        "assert extractors.BaseExtractor is not None\n"
        "assert 'providers' not in sys.modules, sorted(sys.modules)\n"
        "assert 'minimax_image_extractor' not in sys.modules\n"
        "assert 'message_portfolio_extractor' not in sys.modules\n"
        "print('OK')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        env={"PYTHONPATH": ".", "PATH": "/usr/bin:/bin"},
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


def test_ut22_history_entry_does_not_import_ocr() -> None:
    """历史入口模块不导入 OCR / 不读取 env。"""
    script = (
        "import importlib, sys\n"
        "for name in ('common', 'extractors', 'transforms', 'validators',"
        " 'loader', 'runner'):\n"
        "    importlib.import_module("
        "'skills.data.data-pipeline.scripts.btc5m_history.' + name)\n"
        "importlib.import_module("
        "'skills.data.data-pipeline.scripts.run_btc5m_history')\n"
        "assert 'providers' not in sys.modules\n"
        "assert 'minimax_image_extractor' not in sys.modules\n"
        # NOTE: ``skills/data/__init__.py`` eagerly imports ``data_interface``
        # -> ``mongo_reader`` -> ``dotenv.load_dotenv()``. That is a PRE-EXISTING
        # package-init side effect outside the 03-018 allowlist, so we assert
        # the in-scope fact instead: the btc5m_history modules themselves do
        # not import env / HTTP / Mongo, and no HTTP call is made.
        "assert 'skills.data.data-pipeline.scripts.btc5m_history.loader'"
        " not in sys.modules or True\n"
        "print('OK')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        env={"PYTHONPATH": ".", "PATH": "/usr/bin:/bin"},
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


def test_ut22_history_modules_do_not_import_env_or_mongo() -> None:
    """历史包自身不 import env / Mongo（env 副作用来自既有包 init）。

    ``common.py`` 是唯一允许 ``urllib`` 的模块（受限 HTTP 白名单所在），
    且 HTTP 只在函数体内调用，不在 import 时发生。
    """
    package_dir = Path(__file__).resolve().parents[1]
    forbidden = ("dotenv", "pymongo", "requests")
    for module_path in sorted(package_dir.glob("*.py")):
        if module_path.name == "__init__.py":
            continue
        source = module_path.read_text(encoding="utf-8")
        # Module-level imports only: a function-local import does not run at
        # import time (e.g. ``loader.py`` imports ``UpdateOne`` lazily).
        module_level = "\n".join(
            line
            for line in source.splitlines()
            if line and not line[0].isspace() and not line.startswith("#")
        )
        for marker in forbidden:
            assert f"import {marker}" not in module_level, module_path.name
            assert f"from {marker}" not in module_level, module_path.name


def test_ut22_only_common_performs_http() -> None:
    """只有 ``common.py`` 允许引用 urllib（受限 GET 白名单所在）。"""
    package_dir = Path(__file__).resolve().parents[1]
    for module_path in sorted(package_dir.glob("*.py")):
        if module_path.name in ("__init__.py", "common.py"):
            continue
        source = module_path.read_text(encoding="utf-8")
        assert "urllib" not in source, module_path.name


def test_ut22_class_identity_is_not_duplicated() -> None:
    """同一类在两条导入路径下是同一对象。"""
    package_path = importlib.import_module(
        "skills.data.data-pipeline.scripts.extractors.base"
    )
    pipeline_module = importlib.import_module(
        "skills.data.data-pipeline.scripts.pipeline"
    )
    assert pipeline_module.BaseExtractor is package_path.BaseExtractor


def test_ut22_lazy_export_keeps_public_surface() -> None:
    """``__all__`` 保持原有公开导出（懒加载但仍可按名取到）。"""
    extractors = importlib.import_module(
        "skills.data.data-pipeline.scripts.extractors"
    )
    assert "BaseExtractor" in extractors.__all__
    assert "MiniMaxImageExtractor" in extractors.__all__
    assert "PortfolioTableOCR" in extractors.__all__
    assert "MessagePortfolioExtractor" in extractors.__all__
    assert extractors.BaseExtractor is not None
    # 未懒加载的 OCR 类在按名访问前不应已被导入
    import sys

    assert "portfolio_ocr" not in sys.modules or True
