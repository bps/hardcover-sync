"""
Data models for Hardcover Sync plugin.

This module contains the dataclasses representing Hardcover API entities.
These are separated from the API client for cleaner architecture.
"""

from dataclasses import dataclass
from typing import Any

__all__ = [
    "Author",
    "Book",
    "Edition",
    "List",
    "User",
    "UserBook",
    "UserBookRead",
    "clean_isbn",
]


def clean_isbn(isbn: str) -> str:
    """Clean an ISBN by removing dashes and spaces."""
    return isbn.replace("-", "").replace(" ", "")


@dataclass
class User:
    """Represents a Hardcover user."""

    id: int
    username: str
    name: str | None = None
    books_count: int = 0
    image: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "User":
        """Create a User from API response data."""
        return cls(
            id=data["id"],
            username=data["username"],
            name=data.get("name"),
            books_count=data.get("books_count", 0),
            image=data.get("image"),
        )


@dataclass
class Author:
    """Represents a book author."""

    id: int
    name: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Author":
        """Create an Author from API response data."""
        return cls(id=data["id"], name=data["name"])


@dataclass
class Edition:
    """Represents a book edition."""

    id: int
    isbn_13: str | None = None
    isbn_10: str | None = None
    title: str | None = None
    pages: int | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Edition":
        """Create an Edition from API response data."""
        return cls(
            id=data["id"],
            isbn_13=data.get("isbn_13"),
            isbn_10=data.get("isbn_10"),
            title=data.get("title"),
            pages=data.get("pages"),
        )


@dataclass
class Book:
    """Represents a Hardcover book."""

    id: int
    title: str
    slug: str | None = None
    release_date: str | None = None
    authors: list[Author] | None = None
    editions: list[Edition] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any], editions: list["Edition"] | None = None) -> "Book":
        """Create a Book from API response data.

        Args:
            data: Book data from API response.
            editions: Optional pre-parsed editions list (used when editions come from
                      a separate part of the response, e.g., ISBN lookup).
        """
        authors = []
        for contrib in data.get("contributions", []):
            author_data = contrib.get("author", {})
            if author_data:
                authors.append(Author.from_dict(author_data))

        if editions is None:
            editions = []
            for ed in data.get("editions", []):
                editions.append(Edition.from_dict(ed))

        return cls(
            id=data["id"],
            title=data["title"],
            slug=data.get("slug"),
            release_date=data.get("release_date"),
            authors=authors if authors else None,
            editions=editions if editions else None,
        )


@dataclass
class UserBookRead:
    """Represents a single reading session for a book.

    Hardcover supports multiple reads of the same book (re-reads).
    Each read has its own start/finish dates and progress.
    """

    id: int
    started_at: str | None = None
    finished_at: str | None = None
    paused_at: str | None = None
    progress: float | None = None  # 0.0-1.0 percentage
    progress_pages: int | None = None
    edition_id: int | None = None

    @property
    def progress_percent(self) -> float | None:
        """Get progress as a percentage (0-100)."""
        if self.progress is not None:
            return self.progress * 100
        return None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "UserBookRead":
        """Create a UserBookRead from API response data."""
        return cls(
            id=data["id"],
            started_at=data.get("started_at"),
            finished_at=data.get("finished_at"),
            paused_at=data.get("paused_at"),
            progress=data.get("progress"),
            progress_pages=data.get("progress_pages"),
            edition_id=data.get("edition_id"),
        )


@dataclass
class UserBook:
    """Represents a book in a user's library."""

    id: int
    book_id: int
    edition_id: int | None = None
    status_id: int | None = None
    rating: float | None = None
    review: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    book: Book | None = None
    edition: Edition | None = None
    reads: list[UserBookRead] | None = None

    # Deprecated fields - use reads instead
    # Kept for backward compatibility but always None from API
    progress: float | None = None
    progress_pages: int | None = None
    started_at: str | None = None
    finished_at: str | None = None

    @property
    def latest_read(self) -> UserBookRead | None:
        """Get the most recent reading session (first in list, sorted by started_at desc)."""
        if self.reads:
            return self.reads[0]
        return None

    @property
    def first_read(self) -> UserBookRead | None:
        """Get the first/oldest reading session."""
        if self.reads:
            return self.reads[-1]
        return None

    @property
    def latest_started_at(self) -> str | None:
        """Get the start date from the most recent read."""
        read = self.latest_read
        return read.started_at if read else None

    @property
    def latest_finished_at(self) -> str | None:
        """Get the finish date from the most recent read."""
        read = self.latest_read
        return read.finished_at if read else None

    @property
    def first_started_at(self) -> str | None:
        """Get the start date from the first read (when they first started the book)."""
        read = self.first_read
        return read.started_at if read else None

    @property
    def first_finished_at(self) -> str | None:
        """Get the finish date from the first read (when they first finished)."""
        read = self.first_read
        return read.finished_at if read else None

    @property
    def current_progress_pages(self) -> int | None:
        """Get progress pages from the most recent read."""
        read = self.latest_read
        return read.progress_pages if read else None

    @property
    def current_progress(self) -> float | None:
        """Get progress (0.0-1.0) from the most recent read."""
        read = self.latest_read
        return read.progress if read else None

    @property
    def current_progress_percent(self) -> float | None:
        """Get progress as percentage (0-100) from the most recent read."""
        read = self.latest_read
        return read.progress_percent if read else None

    @property
    def read_count(self) -> int:
        """Get the number of times this book has been read/started."""
        return len(self.reads) if self.reads else 0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "UserBook":
        """Create a UserBook from API response data."""
        # Parse nested book
        book = None
        book_data = data.get("book")
        if book_data:
            book = Book.from_dict(book_data)

        # Parse nested edition
        edition = None
        edition_data = data.get("edition")
        if edition_data:
            edition = Edition.from_dict(edition_data)

        # Parse reads list
        reads = []
        reads_data = data.get("user_book_reads", [])
        for r in reads_data:
            reads.append(UserBookRead.from_dict(r))

        return cls(
            id=data["id"],
            book_id=data["book_id"],
            edition_id=data.get("edition_id"),
            status_id=data.get("status_id"),
            rating=data.get("rating"),
            review=data.get("review_raw"),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
            book=book,
            edition=edition,
            reads=reads,
        )


@dataclass
class List:
    """Represents a Hardcover list."""

    id: int
    name: str
    slug: str | None = None
    description: str | None = None
    books_count: int = 0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "List":
        """Create a List from API response data."""
        return cls(
            id=data["id"],
            name=data["name"],
            slug=data.get("slug"),
            description=data.get("description"),
            books_count=data.get("books_count", 0),
        )
