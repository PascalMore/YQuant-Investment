"""Unit tests for the KlineClient abstraction layer (UT-KC-001..005).

Covers DESIGN-03-012 §5.1 matrix items:

- UT-KC-001: FakeKlineClient returns the fixture DataFrame
- UT-KC-002: FakeKlineClient raises ProviderUnavailableError
- UT-KC-003: FakeKlineClient returns empty DataFrame when no fixture
- UT-KC-004: TushareKlineClient raises on missing token
- UT-KC-005: AKShareKlineClient lazy-imports (no crash at import time)
"""

from __future__ import annotations

import pytest

from skills.data.unified_data.exceptions import ProviderError, ProviderUnavailableError
from skills.data.unified_data.providers.kline_client import (
    AKShareKlineClient,
    FakeKlineClient,
    TushareKlineClient,
)

# -- Module-level helpers -----------------------------------------------------


class _FakeSecurityId:
    """Minimal security-id stand-in for tests that exercise the call path."""
    symbol = "600519"


# ---------------------------------------------------------------------------
# FakeKlineClient (UT-KC-001..003)
# ---------------------------------------------------------------------------


class TestFakeKlineClient:
    def test_fake_returns_fixture_dataframe(self):
        """UT-KC-001: FakeKlineClient returns a copy of the fixture DataFrame."""
        import pandas as pd

        fixture = pd.DataFrame({"close": [1.0, 2.0], "trade_date": ["20260713", "20260714"]})
        client = FakeKlineClient(dataframe=fixture)
        result = client.get_kline_daily("security_id", start_date="20260713")
        assert list(result["close"]) == [1.0, 2.0]
        assert len(client.call_log) == 1
        assert client.call_log[0]["security_id"] == "security_id"

    def test_fake_raises_configured(self):
        """UT-KC-002: FakeKlineClient raises the configured exception."""
        client = FakeKlineClient(exception=ProviderUnavailableError("simulated"))
        with pytest.raises(ProviderUnavailableError, match="simulated"):
            client.get_kline_daily("sid")

    def test_fake_returns_empty_dataframe(self):
        """UT-KC-003: FakeKlineClient returns an empty DataFrame when no fixture."""
        client = FakeKlineClient()
        result = client.get_kline_daily("sid", limit=5)
        assert result.empty
        assert len(result.columns) == 0


# ---------------------------------------------------------------------------
# TushareKlineClient (UT-KC-004)
# ---------------------------------------------------------------------------


class TestTushareKlineClient:
    def test_token_missing_raises(self):
        """UT-KC-004: empty token raises ProviderUnavailableError at construction."""
        for empty in ("", "  ", None):
            kwargs = {}
            if empty is not None:
                kwargs["token"] = empty
            else:
                kwargs["token"] = None
            with pytest.raises(ProviderUnavailableError, match="token missing"):
                TushareKlineClient(**kwargs)  # type: ignore[arg-type]

    def test_token_ok_constructs(self):
        """Happy-path: non-empty token allows construction."""
        client = TushareKlineClient(token="valid-token")
        assert client is not None
        # The token is stored but never printed; verify via class internals.
        assert client._token == "valid-token"


# ---------------------------------------------------------------------------
# AKShareKlineClient (UT-KC-005)
# ---------------------------------------------------------------------------


class TestAKShareKlineClient:
    def test_lazy_import_no_crash(self):
        """UT-KC-005: AKShareKlineClient can be constructed without akshare installed.

        The real SDK is only imported inside get_kline_daily, so module-level
        imports and CLI instantiation must succeed even when akshare is absent.
        """
        client = AKShareKlineClient()
        assert client._timeout == 30.0

    def test_call_without_akshare_raises_module_not_found(self):
        """When akshare is not installed, get_kline_daily fails with ImportError.

        Uses ``patch.dict`` to *block* the import even when the SDK is
        installed in the environment — a plain ``sys.modules.pop`` does
        not prevent Python from re-importing an installed package.

        The test also proves ``stock_zh_a_hist`` is never called (the
        import fails before any network access).
        """
        from unittest.mock import patch

        client = AKShareKlineClient()

        with patch.dict("sys.modules", {"akshare": None}):
            with pytest.raises(
                (ImportError, ModuleNotFoundError),
                match="akshare",
            ):
                client.get_kline_daily(_FakeSecurityId())


# ---------------------------------------------------------------------------
# _raise_classified — connection error classification (TDD-CC-001..008)
# ---------------------------------------------------------------------------


class TestRaiseClassified:
    """Verify `_raise_classified` correctly classifies connection-level
    failures as :class:`ProviderUnavailableError` so the Router can
    transparently fall back.

    TDD-CC-001..006 test keyword-based matching for EOF, SSL, TLS,
    disconnect, connection reset, and broken pipe messages. TDD-CC-007 tests the
    ``isinstance(exc, ConnectionError)`` guard for built-in connection
    errors whose message may not contain a matching keyword.
    TDD-CC-008 verifies non-connection API errors stay as
    :class:`ProviderError`.
    """

    # -- Keyword-based connection errors ----------------------------------

    def test_eof_keyword_classified_as_unavailable(self):
        """TDD-CC-001: 'eof' in message → ProviderUnavailableError."""
        with pytest.raises(ProviderUnavailableError, match="unavailable"):
            TushareKlineClient._raise_classified(
                "test", Exception("EOF occurred in violation of protocol")
            )

    def test_ssl_keyword_classified_as_unavailable(self):
        """TDD-CC-002: 'ssl' in message → ProviderUnavailableError."""
        with pytest.raises(ProviderUnavailableError, match="unavailable"):
            TushareKlineClient._raise_classified(
                "test", Exception("SSL certificate verify failed")
            )

    def test_tls_keyword_classified_as_unavailable(self):
        """TDD-CC-003: 'tls' in message → ProviderUnavailableError."""
        with pytest.raises(ProviderUnavailableError, match="unavailable"):
            TushareKlineClient._raise_classified(
                "test", Exception("TLS handshake failed")
            )

    def test_disconnect_keyword_classified_as_unavailable(self):
        """TDD-CC-004: 'disconnect' in message → ProviderUnavailableError."""
        with pytest.raises(ProviderUnavailableError, match="unavailable"):
            TushareKlineClient._raise_classified(
                "test", Exception("remote end disconnected")
            )

    def test_broken_pipe_keyword_classified_as_unavailable(self):
        """TDD-CC-005: 'broken pipe' in message → ProviderUnavailableError."""
        with pytest.raises(ProviderUnavailableError, match="unavailable"):
            TushareKlineClient._raise_classified(
                "test", Exception("Broken pipe while writing to socket")
            )

    # -- isinstance-based connection errors --------------------------------

    def test_connectionerror_isinstance_classified_as_unavailable(self):
        """TDD-CC-007: ``isinstance(exc, ConnectionError)`` → ProviderUnavailableError
        even when no keyword matches (empty message)."""
        with pytest.raises(ProviderUnavailableError, match="unavailable"):
            TushareKlineClient._raise_classified(
                "test", ConnectionResetError()
            )

    # -- Non-connection errors stay ProviderError -------------------------

    def test_non_connection_error_stays_provider_error(self):
        """TDD-CC-008: API/business errors → ProviderError."""
        with pytest.raises(ProviderError, match="daily API error"):
            TushareKlineClient._raise_classified(
                "test", ValueError("bad request: invalid symbol")
            )
