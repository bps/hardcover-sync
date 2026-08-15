"""Tests for the session-local ISBN cache."""

from datetime import datetime, timedelta

import hardcover_sync.cache as cache_module
from hardcover_sync.cache import CachedBook, HardcoverCache, get_cache


class MutableClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value


class TestHardcoverCache:
    def setup_method(self):
        self.clock = MutableClock(datetime(2025, 1, 1, 12, 0, 0))
        self.cache = HardcoverCache(now=self.clock)

    def test_set_and_get_normalizes_isbn(self):
        self.cache.set_isbn("978-0-123 45678-9", 10, 20, "Test Book")

        result = self.cache.get_by_isbn("9780123456789")

        assert result == CachedBook(
            hardcover_id=10,
            edition_id=20,
            title="Test Book",
            isbn="9780123456789",
            cached_at=self.clock.value,
        )

    def test_missing_isbn_returns_none(self):
        assert self.cache.get_by_isbn("9780123456789") is None

    def test_expired_entry_is_removed(self):
        self.cache.set_isbn("9780123456789", 10, None, "Test Book")
        self.clock.value += timedelta(hours=24, seconds=1)

        assert self.cache.get_by_isbn("9780123456789") is None
        assert self.cache._isbn_cache == {}

    def test_expiry_boundary_is_inclusive(self):
        self.cache.set_isbn("9780123456789", 10, None, "Test Book")
        self.clock.value += timedelta(hours=24)

        assert self.cache.get_by_isbn("9780123456789") is not None

    def test_custom_expiry(self):
        cache = HardcoverCache(expiry=timedelta(minutes=5), now=self.clock)
        cache.set_isbn("9780123456789", 10, None, "Test Book")
        self.clock.value += timedelta(minutes=6)

        assert cache.get_by_isbn("9780123456789") is None

    def test_remove_isbn(self):
        self.cache.set_isbn("9780123456789", 10, None, "Test Book")

        self.cache.remove_isbn("978-0-123-45678-9")

        assert self.cache.get_by_isbn("9780123456789") is None

    def test_remove_missing_isbn_is_safe(self):
        self.cache.remove_isbn("9780123456789")

    def test_clear_all(self):
        self.cache.set_isbn("9780123456789", 10, None, "One")
        self.cache.set_isbn("9789876543210", 11, None, "Two")

        self.cache.clear_all()

        assert self.cache.get_by_isbn("9780123456789") is None
        assert self.cache.get_by_isbn("9789876543210") is None


class TestGetCache:
    def setup_method(self):
        cache_module._cache = None

    def teardown_method(self):
        cache_module._cache = None

    def test_returns_singleton(self):
        assert get_cache() is get_cache()

    def test_creates_cache_lazily(self):
        assert cache_module._cache is None

        result = get_cache()

        assert isinstance(result, HardcoverCache)
        assert cache_module._cache is result
