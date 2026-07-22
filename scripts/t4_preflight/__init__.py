"""T4 Preflight & Smoke toolchain.

DESIGN-03-014 §15: 22-file T4 production-readiness preflight & smoke
allowlist. Default dry-run / zero-write / zero-network. Live-read only
on explicit ``--live-read`` (Pascal Gate, see SPEC §14.6 / RFC §13.6).
"""

__all__: list[str] = []
