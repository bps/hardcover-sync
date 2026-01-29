"""
Tests for the cache module.
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock


from hardcover_sync.cache import (
    CACHE_EXPIRY_HOURS,
    CachedBook,
    HardcoverCache,
    get_cache,
)


class TestCachedBook:
    """Tests for the CachedBook dataclass."""

    def test_create_cached_book(self):
        """Test creating a CachedBook."""
        book = CachedBook(
            hardcover_id=123,
            edition_id=456,
            title="Test Book",
            isbn="9780123456789",
            cached_at=datetime.now(),
        )
        assert book.hardcover_id == 123
        assert book.edition_id == 456
        assert book.title == "Test Book"


class TestHardcoverCache:
    """Tests for the HardcoverCache class."""

    def test_init_empty(self):
        """Test initializing an empty cache."""
        cache = HardcoverCache()
        assert cache.get_by_isbn("9780123456789") is None
        assert not cache.is_library_cached()

    def test_set_and_get_isbn(self):
        """Test setting and getting ISBN cache."""
        cache = HardcoverCache()
        cache.set_isbn("9780123456789", 100, 200, "Test Book")

        result = cache.get_by_isbn("9780123456789")
        assert result is not None
        assert result.hardcover_id == 100
        assert result.edition_id == 200
        assert result.title == "Test Book"

    def test_isbn_cleaning(self):
        """Test that ISBNs are cleaned of dashes and spaces."""
        cache = HardcoverCache()
        cache.set_isbn("978-0-123-45678-9", 100, None, "Test")

        # Should find with any format
        assert cache.get_by_isbn("9780123456789") is not None
        assert cache.get_by_isbn("978-0-123-45678-9") is not None
        assert cache.get_by_isbn("978 0 123 45678 9") is not None

    def test_isbn_expiry(self):
        """Test that expired ISBN entries are removed."""
        cache = HardcoverCache()

        # Create an expired entry
        expired_time = datetime.now() - timedelta(hours=CACHE_EXPIRY_HOURS + 1)
        cache._isbn_cache["9780123456789"] = CachedBook(
            hardcover_id=100,
            edition_id=None,
            title="Expired",
            isbn="9780123456789",
            cached_at=expired_time,
        )

        # Should return None and remove the entry
        assert cache.get_by_isbn("9780123456789") is None
        assert "9780123456789" not in cache._isbn_cache

    def test_remove_isbn(self):
        """Test removing an ISBN from cache."""
        cache = HardcoverCache()
        cache.set_isbn("9780123456789", 100, None, "Test")

        cache.remove_isbn("9780123456789")
        assert cache.get_by_isbn("9780123456789") is None

    def test_library_cache(self):
        """Test library caching."""
        cache = HardcoverCache()

        user_books = [
            {"book_id": 1, "status_id": 3, "rating": 5},
            {"book_id": 2, "status_id": 1, "rating": None},
        ]
        cache.set_library(user_books)

        assert cache.is_library_cached()
        assert cache.get_library_book(1) == {"book_id": 1, "status_id": 3, "rating": 5}
        assert cache.get_library_book(2) == {"book_id": 2, "status_id": 1, "rating": None}
        assert cache.get_library_book(999) is None

    def test_library_cache_expiry(self):
        """Test that expired library cache is cleared."""
        cache = HardcoverCache()
        cache.set_library([{"book_id": 1}])

        # Expire the cache
        cache._library_cached_at = datetime.now() - timedelta(hours=CACHE_EXPIRY_HOURS + 1)

        assert not cache.is_library_cached()
        assert cache.get_library_book(1) is None

    def test_update_library_book(self):
        """Test updating a single book in library cache."""
        cache = HardcoverCache()
        cache.set_library([{"book_id": 1, "status_id": 1}])

        cache.update_library_book(1, {"book_id": 1, "status_id": 3})
        assert cache.get_library_book(1)["status_id"] == 3

    def test_remove_library_book(self):
        """Test removing a book from library cache."""
        cache = HardcoverCache()
        cache.set_library([{"book_id": 1}, {"book_id": 2}])

        cache.remove_library_book(1)
        assert cache.get_library_book(1) is None
        assert cache.get_library_book(2) is not None

    def test_clear_library_cache(self):
        """Test clearing the library cache."""
        cache = HardcoverCache()
        cache.set_library([{"book_id": 1}])

        cache.clear_library_cache()
        assert not cache.is_library_cached()

    def test_clear_all(self):
        """Test clearing all caches."""
        cache = HardcoverCache()
        cache.set_isbn("9780123456789", 100, None, "Test")
        cache.set_library([{"book_id": 1}])

        cache.clear_all()

        assert cache.get_by_isbn("9780123456789") is None
        assert not cache.is_library_cached()


class TestGetCache:
    """Tests for the get_cache function."""

    def test_get_cache_singleton(self):
        """Test that get_cache returns a singleton."""
        # Reset the global cache
        import hardcover_sync.cache as cache_module

        cache_module._cache = None

        cache1 = get_cache()
        cache2 = get_cache()

        assert cache1 is cache2

    def test_get_cache_with_db(self):
        """Test setting database on cache."""
        import hardcover_sync.cache as cache_module

        cache_module._cache = None

        mock_db = MagicMock()
        mock_db.new_api.pref.return_value = None

        cache = get_cache(mock_db)
        assert cache._db is mock_db
