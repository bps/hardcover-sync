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

    def test_get_cache_updates_existing_db(self):
        """Test that get_cache updates db on existing cache."""
        import hardcover_sync.cache as cache_module

        cache_module._cache = None

        mock_db1 = MagicMock()
        mock_db1.new_api.pref.return_value = None
        mock_db2 = MagicMock()
        mock_db2.new_api.pref.return_value = None

        cache1 = get_cache(mock_db1)
        cache2 = get_cache(mock_db2)

        assert cache1 is cache2
        assert cache2._db is mock_db2


class TestCacheSerialization:
    """Tests for cache serialization/deserialization."""

    def test_serialize_isbn_cache(self):
        """Test ISBN cache serialization."""
        cache = HardcoverCache()
        cache.set_isbn("9780123456789", 100, 200, "Test Book")

        result = cache._serialize_isbn_cache()
        assert "9780123456789" in result
        assert result["9780123456789"]["hardcover_id"] == 100
        assert result["9780123456789"]["edition_id"] == 200
        assert result["9780123456789"]["title"] == "Test Book"
        assert "cached_at" in result["9780123456789"]

    def test_serialize_isbn_cache_excludes_expired(self):
        """Test that expired entries are excluded from serialization."""
        cache = HardcoverCache()

        # Add an expired entry directly
        expired_time = datetime.now() - timedelta(hours=CACHE_EXPIRY_HOURS + 1)
        cache._isbn_cache["9780123456789"] = CachedBook(
            hardcover_id=100,
            edition_id=None,
            title="Expired",
            isbn="9780123456789",
            cached_at=expired_time,
        )

        result = cache._serialize_isbn_cache()
        assert "9780123456789" not in result

    def test_load_isbn_cache(self):
        """Test ISBN cache deserialization."""
        cache = HardcoverCache()

        data = {
            "9780123456789": {
                "hardcover_id": 100,
                "edition_id": 200,
                "title": "Test Book",
                "cached_at": datetime.now().isoformat(),
            }
        }
        cache._load_isbn_cache(data)

        book = cache.get_by_isbn("9780123456789")
        assert book is not None
        assert book.hardcover_id == 100
        assert book.edition_id == 200

    def test_load_isbn_cache_skips_expired(self):
        """Test that expired entries are skipped during load."""
        cache = HardcoverCache()

        expired_time = datetime.now() - timedelta(hours=CACHE_EXPIRY_HOURS + 1)
        data = {
            "9780123456789": {
                "hardcover_id": 100,
                "edition_id": None,
                "title": "Expired",
                "cached_at": expired_time.isoformat(),
            }
        }
        cache._load_isbn_cache(data)

        assert cache.get_by_isbn("9780123456789") is None

    def test_load_isbn_cache_skips_invalid(self):
        """Test that invalid entries are skipped during load."""
        cache = HardcoverCache()

        data = {
            "9780123456789": {"invalid": "data"},  # Missing required fields
            "9780111111111": {
                "hardcover_id": 200,
                "title": "Valid",
                "cached_at": "not-a-date",  # Invalid date
            },
        }
        cache._load_isbn_cache(data)

        assert cache.get_by_isbn("9780123456789") is None
        assert cache.get_by_isbn("9780111111111") is None

    def test_serialize_library_cache(self):
        """Test library cache serialization."""
        cache = HardcoverCache()
        cache.set_library([{"book_id": 1, "status_id": 3}])

        result = cache._serialize_library_cache()
        assert "cached_at" in result
        assert "books" in result
        assert "1" in result["books"]  # Keys are stringified
        assert result["books"]["1"]["status_id"] == 3

    def test_serialize_library_cache_empty_when_expired(self):
        """Test that expired library cache serializes to empty."""
        cache = HardcoverCache()
        cache.set_library([{"book_id": 1}])

        # Expire the cache
        cache._library_cached_at = datetime.now() - timedelta(hours=CACHE_EXPIRY_HOURS + 1)

        result = cache._serialize_library_cache()
        assert result == {}

    def test_serialize_library_cache_empty_when_not_set(self):
        """Test that unset library cache serializes to empty."""
        cache = HardcoverCache()
        result = cache._serialize_library_cache()
        assert result == {}

    def test_load_library_cache(self):
        """Test library cache deserialization."""
        cache = HardcoverCache()

        data = {
            "cached_at": datetime.now().isoformat(),
            "books": {"1": {"book_id": 1, "status_id": 3}},
        }
        cache._load_library_cache(data)

        assert cache.is_library_cached()
        assert cache.get_library_book(1) is not None

    def test_load_library_cache_skips_expired(self):
        """Test that expired library cache is not loaded."""
        cache = HardcoverCache()

        expired_time = datetime.now() - timedelta(hours=CACHE_EXPIRY_HOURS + 1)
        data = {
            "cached_at": expired_time.isoformat(),
            "books": {"1": {"book_id": 1}},
        }
        cache._load_library_cache(data)

        assert not cache.is_library_cached()

    def test_load_library_cache_invalid_date(self):
        """Test that invalid cached_at is handled."""
        cache = HardcoverCache()

        data = {
            "cached_at": "not-a-date",
            "books": {"1": {"book_id": 1}},
        }
        cache._load_library_cache(data)

        assert not cache.is_library_cached()

    def test_load_library_cache_no_cached_at(self):
        """Test that missing cached_at is handled."""
        cache = HardcoverCache()

        data = {"books": {"1": {"book_id": 1}}}
        cache._load_library_cache(data)

        assert not cache.is_library_cached()


class TestCacheEdgeCases:
    """Tests for edge cases in cache operations."""

    def test_remove_isbn_nonexistent(self):
        """Test removing an ISBN that doesn't exist."""
        cache = HardcoverCache()
        # Should not raise
        cache.remove_isbn("9780123456789")

    def test_remove_library_book_nonexistent(self):
        """Test removing a library book that doesn't exist."""
        cache = HardcoverCache()
        cache.set_library([{"book_id": 1}])
        # Should not raise
        cache.remove_library_book(999)
        # Original book should still be there
        assert cache.get_library_book(1) is not None

    def test_cached_book_without_edition_id(self):
        """Test CachedBook with None edition_id."""
        book = CachedBook(
            hardcover_id=123,
            edition_id=None,
            title="Test Book",
            isbn="9780123456789",
            cached_at=datetime.now(),
        )
        assert book.edition_id is None

    def test_is_library_cached_false_when_empty(self):
        """Test is_library_cached returns False when empty even with timestamp."""
        cache = HardcoverCache()
        cache._library_cached_at = datetime.now()
        cache._library_cache = {}

        assert not cache.is_library_cached()


# =============================================================================
# Coverage Gap Tests
# =============================================================================


class TestLoadCacheNullDb:
    """Test _load_cache early return when db is None."""

    def test_load_cache_with_none_db(self):
        """Cache remains empty when db is None."""
        cache = HardcoverCache(db=None)
        assert cache.get_by_isbn("9780123456789") is None
        assert not cache.is_library_cached()


class TestLoadCacheFromDatabase:
    """Test _load_cache loading from database prefs."""

    def test_load_cache_from_db_prefs(self):
        """Cache loads ISBN and library data from database prefs."""
        import sys
        from types import ModuleType
        from unittest.mock import patch

        isbn_cached_at = datetime.now().isoformat()
        library_cached_at = datetime.now().isoformat()
        cache_data = {
            "isbn_cache": {
                "9780123456789": {
                    "hardcover_id": 100,
                    "edition_id": 200,
                    "title": "Test Book",
                    "cached_at": isbn_cached_at,
                },
            },
            "library_cache": {
                "cached_at": library_cached_at,
                "books": {"1": {"book_id": 1, "status_id": 3}},
            },
        }

        # Create a fake calibre.utils.serialize module
        fake_serialize = ModuleType("calibre.utils.serialize")
        fake_serialize.json_loads = lambda data: cache_data  # type: ignore[attr-defined]

        mock_db = MagicMock()
        mock_db.new_api.pref.return_value = b"serialized"

        with patch.dict(
            sys.modules,
            {
                "calibre": ModuleType("calibre"),
                "calibre.utils": ModuleType("calibre.utils"),
                "calibre.utils.serialize": fake_serialize,
            },
        ):
            cache = HardcoverCache()
            cache.set_database(mock_db)

        assert cache.get_by_isbn("9780123456789") is not None
        assert cache.get_by_isbn("9780123456789").hardcover_id == 100
        assert cache.is_library_cached()
        assert cache.get_library_book(1) is not None

    def test_load_cache_from_db_prefs_none_data(self):
        """When pref returns None, caches remain empty."""
        mock_db = MagicMock()
        mock_db.new_api.pref.return_value = None

        cache = HardcoverCache(db=mock_db)

        assert cache.get_by_isbn("9780123456789") is None
        assert not cache.is_library_cached()


class TestSaveCache:
    """Test _save_cache serialization and persistence."""

    def test_save_cache_happy_path(self):
        """Cache is serialized and saved to DB prefs."""
        import sys
        from types import ModuleType
        from unittest.mock import patch

        mock_db = MagicMock()
        mock_db.new_api.pref.return_value = None

        cache = HardcoverCache(db=mock_db)
        cache.set_isbn("9780123456789", 100, 200, "Test Book")

        fake_serialize = ModuleType("calibre.utils.serialize")
        fake_serialize.json_dumps = MagicMock(return_value=b"serialized")  # type: ignore[attr-defined]

        with patch.dict(
            sys.modules,
            {
                "calibre": ModuleType("calibre"),
                "calibre.utils": ModuleType("calibre.utils"),
                "calibre.utils.serialize": fake_serialize,
            },
        ):
            cache._save_cache()

        fake_serialize.json_dumps.assert_called_once()
        mock_db.new_api.set_pref.assert_called_once_with("hardcover_sync_cache", b"serialized")

    def test_save_cache_error_does_not_propagate(self):
        """If set_pref raises, the error is silently swallowed."""
        import sys
        from types import ModuleType
        from unittest.mock import patch

        mock_db = MagicMock()
        mock_db.new_api.pref.return_value = None

        cache = HardcoverCache(db=mock_db)
        cache.set_isbn("9780123456789", 100, 200, "Test Book")

        fake_serialize = ModuleType("calibre.utils.serialize")
        fake_serialize.json_dumps = MagicMock(return_value=b"serialized")  # type: ignore[attr-defined]

        mock_db.new_api.set_pref.side_effect = RuntimeError("disk full")

        with patch.dict(
            sys.modules,
            {
                "calibre": ModuleType("calibre"),
                "calibre.utils": ModuleType("calibre.utils"),
                "calibre.utils.serialize": fake_serialize,
            },
        ):
            # Should not raise
            cache._save_cache()

    def test_save_cache_skipped_when_no_db(self):
        """_save_cache returns early when db is None."""
        cache = HardcoverCache(db=None)
        # Should not raise
        cache._save_cache()
