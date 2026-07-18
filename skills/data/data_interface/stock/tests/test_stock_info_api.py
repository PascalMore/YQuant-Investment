from __future__ import annotations

import pytest

from skills.data.data_interface.stock import stock_info_api


class FakeCollection:
    def __init__(self, docs: dict[str, dict]):
        self.docs = docs
        self.find_one_calls = 0
        self.find_calls = 0

    def find_one(self, query, projection=None):
        self.find_one_calls += 1
        for condition in query["$or"]:
            field, value = next(iter(condition.items()))
            for doc in self.docs.values():
                if doc.get(field) == value:
                    return {k: v for k, v in doc.items() if k != "_id"}
        return None

    def find(self, query, projection=None):
        self.find_calls += 1
        return [{k: v for k, v in doc.items() if k != "_id"} for doc in self.docs.values()]


class FakeDatabase:
    def __init__(self, collection: FakeCollection):
        self.collection = collection

    def __getitem__(self, name):
        assert name == "stock_basic_info"
        return self.collection


class FakeClient:
    def __init__(self, collection: FakeCollection):
        self.collection = collection
        self.closed = False

    def __getitem__(self, name):
        assert name == "tradingagents"
        return FakeDatabase(self.collection)

    def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def clear_stock_info_state(monkeypatch):
    stock_info_api.clear_stock_info_cache()
    monkeypatch.setenv("MONGODB_URI", "mongodb://example.invalid/")
    monkeypatch.setenv("MONGODB_DATABASE", "tradingagents")
    monkeypatch.delenv("MONGO_URI", raising=False)
    monkeypatch.delenv("MONGODB_CONNECTION_STRING", raising=False)
    monkeypatch.delenv("MONGODB_HOST", raising=False)
    yield
    stock_info_api.clear_stock_info_cache()


@pytest.fixture
def fake_collection(monkeypatch):
    collection = FakeCollection(
        {
            "600519.SH": {
                "code": "600519",
                "full_symbol": "600519.SH",
                "name": "贵州茅台",
                "list_date": "20010827",
            },
            "000858.SZ": {
                "symbol": "000858",
                "ts_code": "000858.SZ",
                "stock_name": "五粮液",
                "listDate": "19980427",
            },
        }
    )

    def fake_mongo_client(uri, serverSelectionTimeoutMS):
        assert uri == "mongodb://example.invalid/"
        assert serverSelectionTimeoutMS == 5000
        return FakeClient(collection)

    monkeypatch.setattr(stock_info_api, "MongoClient", fake_mongo_client)
    return collection


def test_get_stock_name_accepts_wind_and_bare_formats(fake_collection):
    assert stock_info_api.get_stock_name("600519.SH") == "贵州茅台"
    assert stock_info_api.get_stock_name("600519") == "贵州茅台"
    assert stock_info_api.get_stock_name("000858.SZ") == "五粮液"
    assert stock_info_api.get_stock_name("000858") == "五粮液"


def test_get_stock_info_returns_normalized_fields(fake_collection):
    info = stock_info_api.get_stock_info("000858")

    assert info == {
        "symbol": "000858",
        "ts_code": "000858.SZ",
        "stock_name": "五粮液",
        "listDate": "19980427",
        "code": "000858.SZ",
        "name": "五粮液",
        "market": "SZ",
        "list_date": "19980427",
    }


@pytest.mark.parametrize("code", [None, "", "   ", "ABC", "12345", "900000.SH"])
def test_invalid_or_empty_code_returns_none_without_db(code, monkeypatch):
    def fail_mongo_client(*args, **kwargs):
        raise AssertionError("MongoDB should not be called for invalid code")

    monkeypatch.setattr(stock_info_api, "MongoClient", fail_mongo_client)

    assert stock_info_api.get_stock_info(code) is None
    assert stock_info_api.get_stock_name(code) is None
    assert stock_info_api.is_valid_a_share_code(code) is False


def test_missing_code_returns_none(fake_collection):
    assert stock_info_api.get_stock_info("600000") is None
    assert stock_info_api.get_stock_name("600000") is None


def test_batch_get_stock_names_returns_input_code_mapping(fake_collection):
    assert stock_info_api.batch_get_stock_names(["600519.SH", "000858", "600000", "bad"]) == {
        "600519.SH": "贵州茅台",
        "000858": "五粮液",
    }


def test_get_all_stock_names_returns_cached_canonical_mapping(fake_collection):
    assert stock_info_api.get_all_stock_names() == {
        "600519.SH": "贵州茅台",
        "000858.SZ": "五粮液",
    }
    assert stock_info_api.get_all_stock_names()["600519.SH"] == "贵州茅台"

    assert fake_collection.find_calls == 1


def test_same_normalized_code_uses_lru_cache(fake_collection):
    assert stock_info_api.get_stock_name("600519.SH") == "贵州茅台"
    assert stock_info_api.get_stock_name("600519") == "贵州茅台"

    assert fake_collection.find_one_calls == 1


def test_mongodb_failure_degrades_to_none(monkeypatch):
    def failing_mongo_client(*args, **kwargs):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(stock_info_api, "MongoClient", failing_mongo_client)

    assert stock_info_api.get_stock_info("600519.SH") is None
    assert stock_info_api.get_stock_name("600519.SH") is None
