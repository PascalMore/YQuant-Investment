# Z.AI / GLM endpoint and protocol notes

Session: 2026-06-26. Scope: YQuant data-pipeline OCR fallback plus Hermes profile `yquant` model fallback/compression settings.

## Endpoint/protocol distinction

Z.AI exposes multiple compatible protocols/endpoints. Do not infer the right endpoint from model name alone.

| Use case | Protocol | Endpoint | Notes |
|---|---|---|---|
| GLM Coding Plan chat/completion models (`glm-5.2`, `glm-5.1`, `glm-5v-turbo`, `glm-4.7`) | OpenAI Chat Completion | `https://open.bigmodel.cn/api/coding/paas/v4` | Preferred CN Coding Plan endpoint for `zai` provider in YQuant. `/chat/completions` is appended by the client. |
| Global Coding Plan alternative | OpenAI Chat Completion | `https://api.z.ai/api/coding/paas/v4` | Also tested OK for the same key, but not the chosen canonical YQuant endpoint. |
| Anthropic Messages-compatible API | Anthropic Messages | `https://open.bigmodel.cn/api/anthropic` | Use only with an Anthropic-compatible/custom provider and `api_mode=anthropic_messages`; do not put this URL into Hermes built-in `zai` OpenAI-compatible provider. |
| Non-coding GLM endpoint | OpenAI Chat Completion | `https://open.bigmodel.cn/api/paas/v4` or `https://api.z.ai/api/paas/v4` | May return `1113` even when Coding Plan has quota. Do not use this result to conclude `glm-5.2` Coding Plan is exhausted. |

## Current YQuant canonical config

`~/.hermes/profiles/yquant/config.yaml` should explicitly pin `glm-5.2` usage to the CN Coding Plan endpoint instead of relying on automatic endpoint probing/cache:

```yaml
fallback_providers:
- provider: zai
  model: glm-5.2
  base_url: https://open.bigmodel.cn/api/coding/paas/v4
- provider: openai-codex
  model: gpt-5.5

auxiliary:
  compression:
    provider: zai
    model: glm-5.2
    base_url: https://open.bigmodel.cn/api/coding/paas/v4
```

If `auxiliary.vision` uses `provider: zai` with `glm-5v-turbo`, keep it on the same Coding Plan endpoint unless deliberately testing another pool:

```yaml
auxiliary:
  vision:
    provider: zai
    model: glm-5v-turbo
    base_url: https://open.bigmodel.cn/api/coding/paas/v4
```

## Auth/cache pitfall

Hermes `auth.json` may cache a previously auto-detected Z.AI base URL (for example `https://api.z.ai/api/coding/paas/v4`) and stale status such as `exhausted` from a wrong manual probe. When changing canonical endpoint, check/sync `credential_pool.zai[].base_url` and clear stale error status if needed.

## Correct connectivity test

Use the exact Coding Plan endpoint:

```bash
python3 - <<'PY'
import os, httpx
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path.home() / '.hermes' / 'profiles' / 'yquant' / '.env', override=False)
api_key = os.environ.get('GLM_API_KEY') or os.environ.get('Z_AI_API_KEY')
url = 'https://open.bigmodel.cn/api/coding/paas/v4/chat/completions'
r = httpx.post(
    url,
    headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
    json={
        'model': 'glm-5.2',
        'stream': False,
        'max_tokens': 8,
        'messages': [{'role': 'user', 'content': 'say ok'}],
    },
    timeout=20.0,
)
print(r.status_code, r.text[:500])
PY
```

Expected healthy result: HTTP 200 with `model: glm-5.2` in the response.

## Diagnostic lesson

A 429/1113 from `https://api.z.ai/api/paas/v4` or `https://open.bigmodel.cn/api/paas/v4` only says the non-coding pool is exhausted. It does **not** prove Coding Plan quota is exhausted. Always retest on `/api/coding/paas/v4` before reporting quota state.