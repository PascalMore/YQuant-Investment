"""Scripts package marker.

Phase 3 T4 preflight & smoke tooling lives under scripts.t4_preflight.
This package is intentionally minimal: it exists only so that test code can
import `from scripts.t4_preflight import ...` for offline / dry-run validation
of the production-readiness tooling (DESIGN-03-014 V0.7 §15).

No runtime code lives at this level; submodules implement the actual tools.
"""