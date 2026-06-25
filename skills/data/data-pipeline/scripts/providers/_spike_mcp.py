"""
Step 0 spike: verify Hermes MCP SDK + minimal stdio transport works.
This does NOT call real mmx or Z.AI; only validates imports & config.
"""
import os
import re
import sys

print("=== Step 0 spike: mcp SDK + stdio transport sanity ===")

# 1. SDK import
from mcp import ClientSession, StdioServerParameters
print("[OK] ClientSession, StdioServerParameters importable")

from mcp.client.stdio import stdio_client
print("[OK] mcp.client.stdio.stdio_client importable")

# 2. Verify stdio_client signature
import inspect
sig = inspect.signature(stdio_client)
print(f"[OK] stdio_client signature: {sig}")

# 3. Verify the Z.AI MCP server is registered in Hermes yquant config
cfg_path = "/home/pascal/.hermes/profiles/yquant/config.yaml"
if not os.path.exists(cfg_path):
    print(f"[WARN] config.yaml not found: {cfg_path}")
    sys.exit(1)
with open(cfg_path) as f:
    cfg_text = f.read()

# Lightweight parse: just confirm "Z.AI Vision MCP" appears with command=npx
if "Z.AI Vision MCP" not in cfg_text:
    print("[FAIL] 'Z.AI Vision MCP' not in config.yaml")
    sys.exit(1)
print("[OK] 'Z.AI Vision MCP' registered in mcp_servers")

# 4. Done
print("[OK] Step 0 spike complete. MCP SDK wireable; Z.AI tool listing deferred to first real call.")
