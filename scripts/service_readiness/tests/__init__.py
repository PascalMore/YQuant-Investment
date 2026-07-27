"""Colocated test package for ``scripts.service_readiness``.

Per DESIGN-10-010 §8.1 and the implementer task brief, tests for the
readiness probe live next to the implementation they exercise. The test
module must not touch real systemd/journal/network/services; everything is
covered via dependency injection or ``subprocess``/HTTP mocks (SPEC §7.1).
"""