#!/usr/bin/env bash
# verify_env_loaded.sh — 验证 pipeline 入口 + zai provider 的 self-load 是否都生效
#
# 用法：
#   bash skills/data/data-pipeline/scripts/verify_env_loaded.sh
#
# 模拟「裸跑」场景：unset 所有 zai 关键 env 变量，再用 .venv/bin/python 启动。
# 验证两个 self-load 路径是否都把 Z_AI_API_KEY 注入到 os.environ。
#
# 期望输出：两行都显示 Z_AI_API_KEY 已加载（4 个 + 实际 key 前缀）。
# 失败排查：如果某行显示 MISSING，详见 references/image-failure-postmortem.md。

set -e

REPO_ROOT="/home/pascal/workspace/yquant-investment"
PYBIN="$REPO_ROOT/.venv/bin/python"
PYTHONPATH_VALUE="skills/data/data-pipeline/scripts:$REPO_ROOT"

# 1. 验证 Z.AI provider 实例化时 self-load
echo "=== Test 1: ZAIVisionProvider __init__ self-load ==="
unset Z_AI_API_KEY
cd "$REPO_ROOT"
PYTHONPATH="$PYTHONPATH_VALUE" "$PYBIN" -c "
from providers.zai_provider import ZAIVisionProvider
ZAIVisionProvider()  # trigger __init__ self-load
import os
key = os.environ.get('Z_AI_API_KEY', '')
print('  Z_AI_API_KEY:', key[:4] + '...' + key[-4:] if key else 'MISSING ❌')
"

# 2. 验证 pipeline 入口 load_dotenv
echo ""
echo "=== Test 2: run_unified_image_pipeline entry self-load ==="
unset Z_AI_API_KEY
cd "$REPO_ROOT"
PYTHONPATH="$REPO_ROOT" "$PYBIN" -c "
# Just import — the load_dotenv happens at module top
import run_unified_image_pipeline
import os
key = os.environ.get('Z_AI_API_KEY', '')
print('  Z_AI_API_KEY:', key[:4] + '...' + key[-4:] if key else 'MISSING ❌')
"

# 3. 验证完全裸跑（两个都失效的反例）
echo ""
echo "=== Test 3: bare unset, neither path ==="
unset Z_AI_API_KEY
cd "$REPO_ROOT"
PYTHONPATH="$PYTHONPATH_VALUE" "$PYBIN" -c "
import os
key = os.environ.get('Z_AI_API_KEY', '')
print('  Z_AI_API_KEY:', key[:4] + '...' + key[-4:] if key else 'MISSING (this is expected — just confirms .env is not auto-loaded)')
"

echo ""
echo "=== All tests done ==="
