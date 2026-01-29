"""
Cache management for Hardcover Sync plugin.

This module provides caching for:
- Calibre book ID <-> Hardcover book ID mappings
- User's Hardcover library for faster lookups
- ISBN to Hardcover ID mappings

The cache is stored per-library using Calibre's database.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from calibre.library.database2 import LibraryDatabase2  # noqa: F401

# Cache expiry time (how long before we refresh from Hardcover)
CACHE_EXPIRY_HOURS = 24


@dataclass
class CachedBook:
    """Cached information about a Hardcover book."""

    hardcover_id: int
    edition_id: int | None
    title: str
    isbn: str | None
    cached_at: datetime


class HardcoverCache:
    """
    Cache for Hardcover book data.

    This cache is designed to minimize API calls by storing:
    - ISBN -> Hardcover ID mappings
    - User library data

    The cache is stored in the Calibre library's plugin data.
    """

    def __init__(self, db=None):
        """
        Initialize the cache.

        Args:
            db: Optional Calibre database instance.
        """
        self._db = db
        self._isbn_cache: dict[str, CachedBook] = {}
        self._library_cache: dict[int, dict] = {}  # hardcover_id -> user_book data
        self._library_cached_at: datetime | None = None

    def set_database(self, db):
        """Set the database instance and load cached data."""
        self._db = db
        self._load_cache()

    def _load_cache(self):
        """Load cache from database storage."""
        if not self._db:
            return

        try:
            # Try to load from plugin data
            from calibre.utils.serialize import json_loads

            data = self._db.new_api.pref("hardcover_sync_cache", default=None)
            if data:
                cache_data = json_loads(data)
                self._load_isbn_cache(cache_data.get("isbn_cache", {}))
                self._load_library_cache(cache_data.get("library_cache", {}))
        except Exception:  # noqa: S110
            # If loading fails, start with empty cache
            pass

    def _save_cache(self):
        """Save cache to database storage."""
        if not self._db:
            return

        try:
            from calibre.utils.serialize import json_dumps

            cache_data = {
                "isbn_cache": self._serialize_isbn_cache(),
                "library_cache": self._serialize_library_cache(),
            }
            self._db.new_api.set_pref("hardcover_sync_cache", json_dumps(cache_data))
        except Exception:  # noqa: S110
            # If saving fails, silently continue (cache is non-critical)
            pass

    def _load_isbn_cache(self, data: dict):
        """Load ISBN cache from serialized data."""
        for isbn, book_data in data.items():
            try:
                cached_at = datetime.fromisoformat(book_data["cached_at"])
                if not self._is_expired(cached_at):
                    self._isbn_cache[isbn] = CachedBook(
                        hardcover_id=book_data["hardcover_id"],
                        edition_id=book_data.get("edition_id"),
                        title=book_data["title"],
                        isbn=isbn,
                        cached_at=cached_at,
                    )
            except (KeyError, ValueError):
                continue

    def _serialize_isbn_cache(self) -> dict:
        """Serialize ISBN cache to dict."""
        result = {}
        for isbn, book in self._isbn_cache.items():
            if not self._is_expired(book.cached_at):
                result[isbn] = {
                    "hardcover_id": book.hardcover_id,
                    "edition_id": book.edition_id,
                    "title": book.title,
                    "cached_at": book.cached_at.isoformat(),
                }
        return result

    def _load_library_cache(self, data: dict):
        """Load library cache from serialized data."""
        cached_at = data.get("cached_at")
        if cached_at:
            try:
                self._library_cached_at = datetime.fromisoformat(cached_at)
                if not self._is_expired(self._library_cached_at):
                    self._library_cache = {int(k): v for k, v in data.get("books", {}).items()}
            except ValueError:
                pass

    def _serialize_library_cache(self) -> dict:
        """Serialize library cache to dict."""
        if not self._library_cached_at or self._is_expired(self._library_cached_at):
            return {}

        return {
            "cached_at": self._library_cached_at.isoformat(),
            "books": {str(k): v for k, v in self._library_cache.items()},
        }

    def _is_expired(self, cached_at: datetime) -> bool:
        """Check if a cache entry is expired."""
        return datetime.now() - cached_at > timedelta(hours=CACHE_EXPIRY_HOURS)

    # =========================================================================
    # ISBN Cache Methods
    # =========================================================================

    def get_by_isbn(self, isbn: str) -> CachedBook | None:
        """
        Get cached Hardcover book by ISBN.

        Args:
            isbn: The ISBN (10 or 13 digits, may include dashes).

        Returns:
            CachedBook if found and not expired, None otherwise.
        """
        clean_isbn = isbn.replace("-", "").replace(" ", "")
        book = self._isbn_cache.get(clean_isbn)

        if book and not self._is_expired(book.cached_at):
            return book

        # Remove expired entry
        if book:
            del self._isbn_cache[clean_isbn]

        return None

    def set_isbn(
        self,
        isbn: str,
        hardcover_id: int,
        edition_id: int | None,
        title: str,
    ):
        """
        Cache an ISBN -> Hardcover ID mapping.

        Args:
            isbn: The ISBN (will be cleaned).
            hardcover_id: The Hardcover book ID.
            edition_id: Optional Hardcover edition ID.
            title: The book title.
        """
        clean_isbn = isbn.replace("-", "").replace(" ", "")
        self._isbn_cache[clean_isbn] = CachedBook(
            hardcover_id=hardcover_id,
            edition_id=edition_id,
            title=title,
            isbn=clean_isbn,
            cached_at=datetime.now(),
        )
        self._save_cache()

    def remove_isbn(self, isbn: str):
        """Remove an ISBN from the cache."""
        clean_isbn = isbn.replace("-", "").replace(" ", "")
        if clean_isbn in self._isbn_cache:
            del self._isbn_cache[clean_isbn]
            self._save_cache()

    # =========================================================================
    # Library Cache Methods
    # =========================================================================

    def get_library_book(self, hardcover_id: int) -> dict | None:
        """
        Get cached user_book data by Hardcover book ID.

        Args:
            hardcover_id: The Hardcover book ID.

        Returns:
            Dict with user_book data if found, None otherwise.
        """
        if self._library_cached_at and self._is_expired(self._library_cached_at):
            self.clear_library_cache()
            return None

        return self._library_cache.get(hardcover_id)

    def set_library(self, user_books: list[dict]):
        """
        Cache the user's library.

        Args:
            user_books: List of user_book dictionaries from the API.
        """
        self._library_cache = {ub["book_id"]: ub for ub in user_books}
        self._library_cached_at = datetime.now()
        self._save_cache()

    def update_library_book(self, hardcover_id: int, user_book_data: dict):
        """Update a single book in the library cache."""
        self._library_cache[hardcover_id] = user_book_data
        self._save_cache()

    def remove_library_book(self, hardcover_id: int):
        """Remove a book from the library cache."""
        if hardcover_id in self._library_cache:
            del self._library_cache[hardcover_id]
            self._save_cache()

    def clear_library_cache(self):
        """Clear the library cache."""
        self._library_cache = {}
        self._library_cached_at = None
        self._save_cache()

    def is_library_cached(self) -> bool:
        """Check if the library is cached and not expired."""
        return (
            self._library_cached_at is not None
            and not self._is_expired(self._library_cached_at)
            and len(self._library_cache) > 0
        )

    # =========================================================================
    # Utility Methods
    # =========================================================================

    def clear_all(self):
        """Clear all caches."""
        self._isbn_cache = {}
        self._library_cache = {}
        self._library_cached_at = None
        self._save_cache()


# Global cache instance
_cache: HardcoverCache | None = None


def get_cache(db=None) -> HardcoverCache:
    """
    Get the global cache instance.

    Args:
        db: Optional database to set on the cache.

    Returns:
        The global HardcoverCache instance.
    """
    global _cache
    if _cache is None:
        _cache = HardcoverCache(db)
    elif db is not None:
        _cache.set_database(db)
    return _cache
