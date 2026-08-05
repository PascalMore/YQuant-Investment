"""P0 G-CF-LIVE R2 hardening — independent verify suite.

DESIGN-03-014 V0.37 §R3.3 / §R3.9 / SPEC-03-014 V0.33 §R3.10 / RFC-03-014
V0.33 §R3.3.

These tests are written independently from the implementation team
(``scripts/t4_preflight/test_smoke_flow.py``) and target the
attack surfaces the task body explicitly calls out:

  1. ``args.output_dir`` chmod 0o700 enforced under a pre-existing wide
     directory (the G-CF-LIVE-R2 root cause). Tested via subprocess CLI
     (not Python call) so the umask dependency cannot be hidden.
  2. ``smoke-flow-YYYYMMDD.yaml`` file mode locked to 0o600 — including
     the attack surface where a pre-existing 0o644 / 0o664 file is
     already on disk and the smoke runner truncates/re-writes it.
     POSIX semantics: ``os.open(..., O_CREAT|O_TRUNC, mode=0o600)``
     only enforces the mode on **new** file creation. An existing
     file keeps its existing mode unless the runner adds a
     follow-up ``os.chmod``. The PR claims the 0o600 lock holds
     regardless of umask — that is only half-true: an existing
     over-permissive file escapes the narrowing unless reopened +
     explicit chmod.
  3. chmod failure on ``out_dir`` MUST fail-stop (return code 2)
     and MUST NOT leave any YAML report on disk.
  4. No shell ``rm -rf`` anywhere — tmp_path / TemporaryDirectory
     only.
"""
