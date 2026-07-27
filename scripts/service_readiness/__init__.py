"""Service readiness package marker.

Readiness probe implementation lives in :mod:`scripts.service_readiness.readiness_probe`.
This package is intentionally minimal; it exists so test code can import
``scripts.service_readiness.readiness_probe`` for offline validation.

DESIGN-10-010 §1.2 / SPEC-10-010 §5.4.
"""