"""Small in-memory cache for ISBN lookups during a Calibre session."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from .models import clean_isbn

CACHE_EXPIRY_HOURS = 24


@dataclass
class CachedBook:
    """Cached information about a Hardcover book."""

    hardcover_id: int
    edition_id: int | None
    title: str
    isbn: str
    cached_at: datetime


class HardcoverCache:
    """Session-local cache for ISBN-to-Hardcover matches."""

    def __init__(
        self,
        *,
        expiry: timedelta = timedelta(hours=CACHE_EXPIRY_HOURS),
        now: Callable[[], datetime] = datetime.now,
    ) -> None:
        self._expiry = expiry
        self._now = now
        self._isbn_cache: dict[str, CachedBook] = {}

    def _is_expired(self, cached_at: datetime) -> bool:
        return self._now() - cached_at > self._expiry

    def get_by_isbn(self, isbn: str) -> CachedBook | None:
        """Return an unexpired ISBN match, if present."""
        isbn = clean_isbn(isbn)
        book = self._isbn_cache.get(isbn)
        if book is None:
            return None
        if self._is_expired(book.cached_at):
            del self._isbn_cache[isbn]
            return None
        return book

    def set_isbn(
        self,
        isbn: str,
        hardcover_id: int,
        edition_id: int | None,
        title: str,
    ) -> None:
        """Store an ISBN match for the current session."""
        isbn = clean_isbn(isbn)
        self._isbn_cache[isbn] = CachedBook(
            hardcover_id=hardcover_id,
            edition_id=edition_id,
            title=title,
            isbn=isbn,
            cached_at=self._now(),
        )

    def remove_isbn(self, isbn: str) -> None:
        """Remove an ISBN match if it exists."""
        self._isbn_cache.pop(clean_isbn(isbn), None)

    def clear_all(self) -> None:
        """Clear all session-local matches."""
        self._isbn_cache.clear()


_cache: HardcoverCache | None = None


def get_cache() -> HardcoverCache:
    """Return the process-wide session cache."""
    global _cache
    if _cache is None:
        _cache = HardcoverCache()
    return _cache
