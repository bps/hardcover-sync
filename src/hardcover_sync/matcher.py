"""
Book matching logic for Hardcover Sync plugin.

This module provides functions to match Calibre books to Hardcover books:
- ISBN matching (primary method)
- Title/author search (fallback)
- Identifier extraction from Calibre books
"""

from dataclasses import dataclass

from .api import HardcoverAPI
from .cache import get_cache
from .models import Book


@dataclass
class MatchResult:
    """Result of a book matching attempt."""

    book: Book | None
    match_type: str  # "isbn", "search", "identifier", "none"
    confidence: float  # 0.0 to 1.0
    message: str


def get_calibre_book_identifiers(db, book_id: int) -> dict[str, str]:
    """
    Get all identifiers for a Calibre book.

    Args:
        db: Calibre database API.
        book_id: The Calibre book ID.

    Returns:
        Dict of identifier type -> value.
    """
    return db.field_for("identifiers", book_id) or {}


def get_calibre_book_isbn(db, book_id: int) -> str | None:
    """
    Get the ISBN for a Calibre book.

    Tries ISBN-13 first, then ISBN-10.

    Args:
        db: Calibre database API.
        book_id: The Calibre book ID.

    Returns:
        ISBN string if found, None otherwise.
    """
    identifiers = get_calibre_book_identifiers(db, book_id)

    # Try ISBN-13 first
    isbn = identifiers.get("isbn")
    if isbn:
        return isbn

    # Some books might have isbn13 or isbn10 specifically
    isbn = identifiers.get("isbn13")
    if isbn:
        return isbn

    isbn = identifiers.get("isbn10")
    if isbn:
        return isbn

    return None


def get_hardcover_id(db, book_id: int) -> int | None:
    """
    Get the Hardcover ID for a Calibre book.

    Args:
        db: Calibre database API.
        book_id: The Calibre book ID.

    Returns:
        Hardcover book ID if linked, None otherwise.
    """
    identifiers = get_calibre_book_identifiers(db, book_id)
    hc_id = identifiers.get("hardcover")
    if hc_id:
        try:
            return int(hc_id)
        except ValueError:
            pass
    return None


def get_hardcover_edition_id(db, book_id: int) -> int | None:
    """
    Get the Hardcover edition ID for a Calibre book.

    Args:
        db: Calibre database API.
        book_id: The Calibre book ID.

    Returns:
        Hardcover edition ID if linked, None otherwise.
    """
    identifiers = get_calibre_book_identifiers(db, book_id)
    ed_id = identifiers.get("hardcover-edition")
    if ed_id:
        try:
            return int(ed_id)
        except ValueError:
            pass
    return None


def set_hardcover_id(
    db,
    book_id: int,
    hardcover_id: int,
    edition_id: int | None = None,
):
    """
    Set the Hardcover ID for a Calibre book.

    Args:
        db: Calibre database API.
        book_id: The Calibre book ID.
        hardcover_id: The Hardcover book ID.
        edition_id: Optional Hardcover edition ID.
    """
    identifiers = get_calibre_book_identifiers(db, book_id)
    identifiers["hardcover"] = str(hardcover_id)

    if edition_id is not None:
        identifiers["hardcover-edition"] = str(edition_id)
    elif "hardcover-edition" in identifiers:
        del identifiers["hardcover-edition"]

    db.set_field("identifiers", {book_id: identifiers})


def remove_hardcover_id(db, book_id: int):
    """
    Remove the Hardcover ID from a Calibre book.

    Args:
        db: Calibre database API.
        book_id: The Calibre book ID.
    """
    identifiers = get_calibre_book_identifiers(db, book_id)

    changed = False
    if "hardcover" in identifiers:
        del identifiers["hardcover"]
        changed = True
    if "hardcover-edition" in identifiers:
        del identifiers["hardcover-edition"]
        changed = True

    if changed:
        db.set_field("identifiers", {book_id: identifiers})


def match_by_isbn(api: HardcoverAPI, isbn: str) -> MatchResult:
    """
    Match a book by ISBN.

    Args:
        api: HardcoverAPI instance.
        isbn: The ISBN to search for.

    Returns:
        MatchResult with the matched book or None.
    """
    # Check cache first
    cache = get_cache()
    cached = cache.get_by_isbn(isbn)
    if cached:
        # Return cached result - we need to fetch full book data though
        book = api.get_book_by_id(cached.hardcover_id)
        if book:
            return MatchResult(
                book=book,
                match_type="isbn",
                confidence=1.0,
                message=f"Found in cache: {book.title}",
            )

    # Search by ISBN
    book = api.find_book_by_isbn(isbn)
    if book:
        # Cache the result
        edition_id = book.editions[0].id if book.editions else None
        cache.set_isbn(isbn, book.id, edition_id, book.title)

        return MatchResult(
            book=book,
            match_type="isbn",
            confidence=1.0,
            message=f"Matched by ISBN: {book.title}",
        )

    return MatchResult(
        book=None,
        match_type="none",
        confidence=0.0,
        message=f"No book found for ISBN: {isbn}",
    )


def match_by_search(
    api: HardcoverAPI,
    title: str,
    authors: list[str] | None = None,
) -> list[MatchResult]:
    """
    Search for book matches by title and author.

    Args:
        api: HardcoverAPI instance.
        title: The book title.
        authors: Optional list of author names.

    Returns:
        List of MatchResult objects, sorted by confidence.
    """
    # Build search query
    query = title
    if authors:
        # Add first author to improve search
        query = f"{title} {authors[0]}"

    books = api.search_books(query)

    results = []
    for book in books:
        confidence = _calculate_match_confidence(book, title, authors)
        results.append(
            MatchResult(
                book=book,
                match_type="search",
                confidence=confidence,
                message=_format_book_description(book),
            )
        )

    # Sort by confidence descending
    results.sort(key=lambda r: r.confidence, reverse=True)
    return results


def _calculate_match_confidence(
    book: Book,
    title: str,
    authors: list[str] | None,
) -> float:
    """
    Calculate confidence score for a book match.

    Args:
        book: The Hardcover book.
        title: The search title.
        authors: The search authors.

    Returns:
        Confidence score from 0.0 to 1.0.
    """
    score = 0.0

    # Title matching (up to 0.6)
    title_lower = title.lower()
    book_title_lower = book.title.lower()

    if title_lower == book_title_lower:
        score += 0.6
    elif title_lower in book_title_lower or book_title_lower in title_lower:
        score += 0.4
    else:
        # Check word overlap
        title_words = set(title_lower.split())
        book_words = set(book_title_lower.split())
        overlap = len(title_words & book_words)
        if overlap > 0:
            score += 0.2 * min(overlap / len(title_words), 1.0)

    # Author matching (up to 0.4)
    if authors and book.authors:
        author_lower = authors[0].lower()
        for book_author in book.authors:
            book_author_lower = book_author.name.lower()
            if author_lower == book_author_lower:
                score += 0.4
                break
            elif author_lower in book_author_lower or book_author_lower in author_lower:
                score += 0.3
                break
            else:
                # Check last name match
                author_parts = author_lower.split()
                book_parts = book_author_lower.split()
                if author_parts and book_parts:
                    if author_parts[-1] == book_parts[-1]:
                        score += 0.2
                        break

    return min(score, 1.0)


def _format_book_description(book: Book) -> str:
    """Format a book for display."""
    parts = [book.title]

    if book.authors:
        author_names = ", ".join(a.name for a in book.authors[:2])
        if len(book.authors) > 2:
            author_names += " et al."
        parts.append(f"by {author_names}")

    if book.release_date:
        year = book.release_date[:4]
        parts.append(f"({year})")

    return " ".join(parts)


def match_calibre_book(
    api: HardcoverAPI,
    db,
    book_id: int,
) -> MatchResult:
    """
    Attempt to match a Calibre book to Hardcover.

    Tries in order:
    1. Existing Hardcover identifier
    2. ISBN lookup
    3. Title/author search (returns first high-confidence match)

    Args:
        api: HardcoverAPI instance.
        db: Calibre database API.
        book_id: The Calibre book ID.

    Returns:
        MatchResult with the best match found.
    """
    # Check if already linked
    hc_id = get_hardcover_id(db, book_id)
    if hc_id:
        book = api.get_book_by_id(hc_id)
        if book:
            return MatchResult(
                book=book,
                match_type="identifier",
                confidence=1.0,
                message=f"Already linked: {book.title}",
            )

    # Try ISBN
    isbn = get_calibre_book_isbn(db, book_id)
    if isbn:
        result = match_by_isbn(api, isbn)
        if result.book:
            return result

    # Try title/author search
    title = db.field_for("title", book_id)
    authors = db.field_for("authors", book_id) or []

    if title:
        results = match_by_search(api, title, authors)
        if results and results[0].confidence >= 0.7:
            return results[0]

        # Return best match even if low confidence
        if results:
            return results[0]

    return MatchResult(
        book=None,
        match_type="none",
        confidence=0.0,
        message="Could not find a match",
    )


def search_for_calibre_book(
    api: HardcoverAPI,
    db,
    book_id: int,
) -> list[MatchResult]:
    """
    Search for possible Hardcover matches for a Calibre book.

    Returns all matches for user selection.

    Args:
        api: HardcoverAPI instance.
        db: Calibre database API.
        book_id: The Calibre book ID.

    Returns:
        List of MatchResult objects.
    """
    results = []

    # Try ISBN first
    isbn = get_calibre_book_isbn(db, book_id)
    if isbn:
        result = match_by_isbn(api, isbn)
        if result.book:
            results.append(result)

    # Search by title/author
    title = db.field_for("title", book_id)
    authors = db.field_for("authors", book_id) or []

    if title:
        search_results = match_by_search(api, title, authors)
        # Add search results, avoiding duplicates
        seen_ids = {r.book.id for r in results if r.book}
        for sr in search_results:
            if sr.book and sr.book.id not in seen_ids:
                results.append(sr)
                seen_ids.add(sr.book.id)

    return results
