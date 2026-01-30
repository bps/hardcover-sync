"""
Tests for the matcher module.
"""

from unittest.mock import MagicMock, patch


from hardcover_sync.api import Author, Book, Edition
from hardcover_sync.matcher import (
    MatchResult,
    _calculate_match_confidence,
    _format_book_description,
    get_calibre_book_identifiers,
    get_calibre_book_isbn,
    get_hardcover_id,
    get_hardcover_edition_id,
    match_by_isbn,
    match_by_search,
    match_calibre_book,
    remove_hardcover_id,
    search_for_calibre_book,
    set_hardcover_id,
)


class TestMatchResult:
    """Tests for the MatchResult dataclass."""

    def test_create_match_result(self):
        """Test creating a MatchResult."""
        book = Book(id=1, title="Test", slug="test")
        result = MatchResult(
            book=book,
            match_type="isbn",
            confidence=1.0,
            message="Found",
        )
        assert result.book == book
        assert result.match_type == "isbn"
        assert result.confidence == 1.0


class TestCalculateMatchConfidence:
    """Tests for the _calculate_match_confidence function."""

    def test_exact_title_match(self):
        """Test exact title match gives high confidence."""
        book = Book(id=1, title="The Great Gatsby", slug="gatsby")
        confidence = _calculate_match_confidence(book, "The Great Gatsby", None)
        assert confidence >= 0.6

    def test_title_contains_match(self):
        """Test partial title match."""
        book = Book(id=1, title="The Great Gatsby: A Novel", slug="gatsby")
        confidence = _calculate_match_confidence(book, "The Great Gatsby", None)
        assert confidence >= 0.4

    def test_exact_author_match(self):
        """Test exact author match gives high confidence."""
        book = Book(
            id=1,
            title="Different Title",
            slug="test",
            authors=[Author(id=1, name="F. Scott Fitzgerald")],
        )
        confidence = _calculate_match_confidence(book, "Something Else", ["F. Scott Fitzgerald"])
        assert confidence >= 0.4

    def test_partial_author_match(self):
        """Test partial author match (last name)."""
        book = Book(
            id=1,
            title="Something",
            slug="test",
            authors=[Author(id=1, name="F. Scott Fitzgerald")],
        )
        confidence = _calculate_match_confidence(book, "Something", ["Fitzgerald"])
        assert confidence >= 0.2

    def test_full_match(self):
        """Test matching both title and author."""
        book = Book(
            id=1,
            title="The Great Gatsby",
            slug="gatsby",
            authors=[Author(id=1, name="F. Scott Fitzgerald")],
        )
        confidence = _calculate_match_confidence(book, "The Great Gatsby", ["F. Scott Fitzgerald"])
        assert confidence >= 0.9

    def test_no_match(self):
        """Test no match gives low confidence."""
        book = Book(
            id=1,
            title="Completely Different",
            slug="test",
            authors=[Author(id=1, name="Unknown Author")],
        )
        confidence = _calculate_match_confidence(book, "The Great Gatsby", ["F. Scott Fitzgerald"])
        assert confidence < 0.5

    def test_word_overlap(self):
        """Test word overlap scoring."""
        book = Book(id=1, title="Great Expectations", slug="test")
        confidence = _calculate_match_confidence(book, "The Great Gatsby", None)
        # Should get some score for "Great" overlap
        assert confidence > 0


class TestFormatBookDescription:
    """Tests for the _format_book_description function."""

    def test_title_only(self):
        """Test formatting with just a title."""
        book = Book(id=1, title="Test Book", slug="test")
        result = _format_book_description(book)
        assert result == "Test Book"

    def test_with_single_author(self):
        """Test formatting with one author."""
        book = Book(
            id=1,
            title="Test Book",
            slug="test",
            authors=[Author(id=1, name="John Doe")],
        )
        result = _format_book_description(book)
        assert "by John Doe" in result

    def test_with_multiple_authors(self):
        """Test formatting with multiple authors."""
        book = Book(
            id=1,
            title="Test Book",
            slug="test",
            authors=[
                Author(id=1, name="John Doe"),
                Author(id=2, name="Jane Smith"),
                Author(id=3, name="Bob Wilson"),
            ],
        )
        result = _format_book_description(book)
        assert "John Doe" in result
        assert "Jane Smith" in result
        assert "et al." in result

    def test_with_release_date(self):
        """Test formatting with release date."""
        book = Book(
            id=1,
            title="Test Book",
            slug="test",
            release_date="2024-01-15",
        )
        result = _format_book_description(book)
        assert "(2024)" in result


class TestMatchByISBN:
    """Tests for the match_by_isbn function."""

    @patch("hardcover_sync.matcher.get_cache")
    def test_cache_hit(self, mock_get_cache):
        """Test ISBN match from cache."""
        from hardcover_sync.cache import CachedBook
        from datetime import datetime

        mock_cache = MagicMock()
        mock_cache.get_by_isbn.return_value = CachedBook(
            hardcover_id=123,
            edition_id=456,
            title="Cached Book",
            isbn="9780123456789",
            cached_at=datetime.now(),
        )
        mock_get_cache.return_value = mock_cache

        mock_api = MagicMock()
        mock_api.get_book_by_id.return_value = Book(id=123, title="Cached Book", slug="cached")

        result = match_by_isbn(mock_api, "9780123456789")

        assert result.book is not None
        assert result.book.id == 123
        assert result.match_type == "isbn"
        assert result.confidence == 1.0

    @patch("hardcover_sync.matcher.get_cache")
    def test_api_match(self, mock_get_cache):
        """Test ISBN match from API."""
        mock_cache = MagicMock()
        mock_cache.get_by_isbn.return_value = None
        mock_get_cache.return_value = mock_cache

        mock_api = MagicMock()
        mock_api.find_book_by_isbn.return_value = Book(
            id=789,
            title="Found Book",
            slug="found",
            editions=[Edition(id=111, isbn_13="9780123456789")],
        )

        result = match_by_isbn(mock_api, "9780123456789")

        assert result.book is not None
        assert result.book.id == 789
        assert result.confidence == 1.0
        # Should cache the result
        mock_cache.set_isbn.assert_called_once()

    @patch("hardcover_sync.matcher.get_cache")
    def test_no_match(self, mock_get_cache):
        """Test ISBN with no match."""
        mock_cache = MagicMock()
        mock_cache.get_by_isbn.return_value = None
        mock_get_cache.return_value = mock_cache

        mock_api = MagicMock()
        mock_api.find_book_by_isbn.return_value = None

        result = match_by_isbn(mock_api, "9780000000000")

        assert result.book is None
        assert result.match_type == "none"
        assert result.confidence == 0.0


class TestMatchBySearch:
    """Tests for the match_by_search function."""

    def test_search_results(self):
        """Test search returns sorted results."""
        mock_api = MagicMock()
        mock_api.search_books.return_value = [
            Book(
                id=1,
                title="The Great Gatsby",
                slug="gatsby",
                authors=[Author(id=1, name="F. Scott Fitzgerald")],
            ),
            Book(
                id=2,
                title="Gatsby's Girl",
                slug="girl",
                authors=[Author(id=2, name="Someone Else")],
            ),
        ]

        results = match_by_search(mock_api, "The Great Gatsby", ["F. Scott Fitzgerald"])

        assert len(results) == 2
        # First result should have higher confidence
        assert results[0].confidence >= results[1].confidence
        assert results[0].book.id == 1

    def test_empty_search(self):
        """Test empty search results."""
        mock_api = MagicMock()
        mock_api.search_books.return_value = []

        results = match_by_search(mock_api, "nonexistent", None)

        assert results == []


class TestCalibreIdentifiers:
    """Tests for Calibre identifier functions."""

    def test_get_calibre_book_identifiers(self):
        """Test getting identifiers from Calibre."""
        mock_db = MagicMock()
        mock_db.field_for.return_value = {"isbn": "9780123456789", "hardcover": "123"}

        result = get_calibre_book_identifiers(mock_db, 1)

        assert result == {"isbn": "9780123456789", "hardcover": "123"}
        mock_db.field_for.assert_called_once_with("identifiers", 1)

    def test_get_calibre_book_identifiers_empty(self):
        """Test getting identifiers when none exist."""
        mock_db = MagicMock()
        mock_db.field_for.return_value = None

        result = get_calibre_book_identifiers(mock_db, 1)

        assert result == {}

    def test_get_calibre_book_isbn_primary(self):
        """Test getting ISBN from primary isbn field."""
        mock_db = MagicMock()
        mock_db.field_for.return_value = {"isbn": "9780123456789"}

        result = get_calibre_book_isbn(mock_db, 1)

        assert result == "9780123456789"

    def test_get_calibre_book_isbn13(self):
        """Test getting ISBN from isbn13 field."""
        mock_db = MagicMock()
        mock_db.field_for.return_value = {"isbn13": "9780123456789"}

        result = get_calibre_book_isbn(mock_db, 1)

        assert result == "9780123456789"

    def test_get_calibre_book_isbn10(self):
        """Test getting ISBN from isbn10 field."""
        mock_db = MagicMock()
        mock_db.field_for.return_value = {"isbn10": "0123456789"}

        result = get_calibre_book_isbn(mock_db, 1)

        assert result == "0123456789"

    def test_get_calibre_book_isbn_none(self):
        """Test getting ISBN when none exists."""
        mock_db = MagicMock()
        mock_db.field_for.return_value = {}

        result = get_calibre_book_isbn(mock_db, 1)

        assert result is None

    def test_get_hardcover_id(self):
        """Test getting Hardcover ID from identifiers."""
        mock_db = MagicMock()
        mock_db.field_for.return_value = {"hardcover": "123"}

        result = get_hardcover_id(mock_db, 1)

        assert result == 123

    def test_get_hardcover_id_none(self):
        """Test getting Hardcover ID when not set."""
        mock_db = MagicMock()
        mock_db.field_for.return_value = {}

        result = get_hardcover_id(mock_db, 1)

        assert result is None

    def test_get_hardcover_id_invalid(self):
        """Test getting Hardcover ID when value is not numeric."""
        mock_db = MagicMock()
        mock_db.field_for.return_value = {"hardcover": "not-a-number"}

        result = get_hardcover_id(mock_db, 1)

        assert result is None

    def test_get_hardcover_edition_id(self):
        """Test getting Hardcover edition ID from identifiers."""
        mock_db = MagicMock()
        mock_db.field_for.return_value = {"hardcover-edition": "456"}

        result = get_hardcover_edition_id(mock_db, 1)

        assert result == 456

    def test_get_hardcover_edition_id_none(self):
        """Test getting Hardcover edition ID when not set."""
        mock_db = MagicMock()
        mock_db.field_for.return_value = {}

        result = get_hardcover_edition_id(mock_db, 1)

        assert result is None

    def test_get_hardcover_edition_id_invalid(self):
        """Test getting Hardcover edition ID when value is not numeric."""
        mock_db = MagicMock()
        mock_db.field_for.return_value = {"hardcover-edition": "invalid"}

        result = get_hardcover_edition_id(mock_db, 1)

        assert result is None

    def test_set_hardcover_id(self):
        """Test setting Hardcover ID."""
        mock_db = MagicMock()
        mock_db.field_for.return_value = {"isbn": "9780123456789"}

        set_hardcover_id(mock_db, 1, 123)

        mock_db.set_field.assert_called_once_with(
            "identifiers", {1: {"isbn": "9780123456789", "hardcover": "123"}}
        )

    def test_set_hardcover_id_with_edition(self):
        """Test setting Hardcover ID with edition ID."""
        mock_db = MagicMock()
        mock_db.field_for.return_value = {}

        set_hardcover_id(mock_db, 1, 123, edition_id=456)

        mock_db.set_field.assert_called_once_with(
            "identifiers", {1: {"hardcover": "123", "hardcover-edition": "456"}}
        )

    def test_set_hardcover_id_removes_old_edition(self):
        """Test setting Hardcover ID without edition removes old edition."""
        mock_db = MagicMock()
        mock_db.field_for.return_value = {"hardcover": "100", "hardcover-edition": "200"}

        set_hardcover_id(mock_db, 1, 123)

        mock_db.set_field.assert_called_once_with("identifiers", {1: {"hardcover": "123"}})

    def test_remove_hardcover_id(self):
        """Test removing Hardcover ID."""
        mock_db = MagicMock()
        mock_db.field_for.return_value = {"hardcover": "123", "hardcover-edition": "456"}

        remove_hardcover_id(mock_db, 1)

        mock_db.set_field.assert_called_once_with("identifiers", {1: {}})

    def test_remove_hardcover_id_no_change(self):
        """Test removing Hardcover ID when not set."""
        mock_db = MagicMock()
        mock_db.field_for.return_value = {"isbn": "9780123456789"}

        remove_hardcover_id(mock_db, 1)

        mock_db.set_field.assert_not_called()


class TestMatchCalibreBook:
    """Tests for the match_calibre_book function."""

    def test_already_linked(self):
        """Test matching when book is already linked."""
        mock_db = MagicMock()
        mock_db.field_for.return_value = {"hardcover": "123"}

        mock_api = MagicMock()
        mock_api.get_book_by_id.return_value = Book(id=123, title="Linked Book", slug="linked")

        result = match_calibre_book(mock_api, mock_db, 1)

        assert result.book is not None
        assert result.book.id == 123
        assert result.match_type == "identifier"

    @patch("hardcover_sync.matcher.get_cache")
    def test_match_by_isbn_fallback(self, mock_get_cache):
        """Test matching by ISBN when not linked."""
        mock_cache = MagicMock()
        mock_cache.get_by_isbn.return_value = None
        mock_get_cache.return_value = mock_cache

        mock_db = MagicMock()
        mock_db.field_for.side_effect = lambda field, _: (
            {"isbn": "9780123456789"} if field == "identifiers" else None
        )

        mock_api = MagicMock()
        mock_api.find_book_by_isbn.return_value = Book(
            id=789, title="ISBN Match", slug="isbn", editions=[]
        )

        result = match_calibre_book(mock_api, mock_db, 1)

        assert result.book is not None
        assert result.book.id == 789
        assert result.match_type == "isbn"

    @patch("hardcover_sync.matcher.get_cache")
    def test_match_by_search_fallback(self, mock_get_cache):
        """Test matching by search when ISBN not found."""
        mock_cache = MagicMock()
        mock_cache.get_by_isbn.return_value = None
        mock_get_cache.return_value = mock_cache

        mock_db = MagicMock()

        def field_for_side_effect(field, book_id):
            if field == "identifiers":
                return {}
            elif field == "title":
                return "The Great Gatsby"
            elif field == "authors":
                return ["F. Scott Fitzgerald"]
            return None

        mock_db.field_for.side_effect = field_for_side_effect

        mock_api = MagicMock()
        mock_api.find_book_by_isbn.return_value = None
        mock_api.search_books.return_value = [
            Book(
                id=456,
                title="The Great Gatsby",
                slug="gatsby",
                authors=[Author(id=1, name="F. Scott Fitzgerald")],
            )
        ]

        result = match_calibre_book(mock_api, mock_db, 1)

        assert result.book is not None
        assert result.book.id == 456
        assert result.match_type == "search"

    @patch("hardcover_sync.matcher.get_cache")
    def test_no_match_found(self, mock_get_cache):
        """Test when no match can be found."""
        mock_cache = MagicMock()
        mock_cache.get_by_isbn.return_value = None
        mock_get_cache.return_value = mock_cache

        mock_db = MagicMock()

        def field_for_side_effect(field, book_id):
            if field == "identifiers":
                return {}
            elif field == "title":
                return "Unknown Book"
            elif field == "authors":
                return []
            return None

        mock_db.field_for.side_effect = field_for_side_effect

        mock_api = MagicMock()
        mock_api.find_book_by_isbn.return_value = None
        mock_api.search_books.return_value = []

        result = match_calibre_book(mock_api, mock_db, 1)

        assert result.book is None
        assert result.match_type == "none"


class TestSearchForCalibreBook:
    """Tests for the search_for_calibre_book function."""

    @patch("hardcover_sync.matcher.get_cache")
    def test_isbn_and_search_results(self, mock_get_cache):
        """Test getting both ISBN and search results."""
        mock_cache = MagicMock()
        mock_cache.get_by_isbn.return_value = None
        mock_get_cache.return_value = mock_cache

        mock_db = MagicMock()

        def field_for_side_effect(field, book_id):
            if field == "identifiers":
                return {"isbn": "9780123456789"}
            elif field == "title":
                return "Test Book"
            elif field == "authors":
                return ["Test Author"]
            return None

        mock_db.field_for.side_effect = field_for_side_effect

        isbn_book = Book(id=1, title="ISBN Book", slug="isbn", editions=[])
        search_book = Book(id=2, title="Test Book", slug="search")

        mock_api = MagicMock()
        mock_api.find_book_by_isbn.return_value = isbn_book
        mock_api.search_books.return_value = [isbn_book, search_book]

        results = search_for_calibre_book(mock_api, mock_db, 1)

        # Should have ISBN result first, then non-duplicate search results
        assert len(results) == 2
        assert results[0].book.id == 1
        assert results[0].match_type == "isbn"
        assert results[1].book.id == 2

    @patch("hardcover_sync.matcher.get_cache")
    def test_search_only_no_isbn(self, mock_get_cache):
        """Test search when no ISBN exists."""
        mock_cache = MagicMock()
        mock_get_cache.return_value = mock_cache

        mock_db = MagicMock()

        def field_for_side_effect(field, book_id):
            if field == "identifiers":
                return {}
            elif field == "title":
                return "Test Book"
            elif field == "authors":
                return []
            return None

        mock_db.field_for.side_effect = field_for_side_effect

        mock_api = MagicMock()
        mock_api.search_books.return_value = [
            Book(id=1, title="Test Book", slug="test"),
            Book(id=2, title="Another Book", slug="another"),
        ]

        results = search_for_calibre_book(mock_api, mock_db, 1)

        assert len(results) == 2
        assert all(r.match_type == "search" for r in results)


class TestMatchConfidenceEdgeCases:
    """Additional tests for match confidence edge cases."""

    def test_author_last_name_match(self):
        """Test author matching by last name only."""
        book = Book(
            id=1,
            title="Different Title",
            slug="test",
            authors=[Author(id=1, name="John Smith")],
        )
        confidence = _calculate_match_confidence(book, "Another Title", ["Jane Smith"])
        # Should get 0.2 for last name match
        assert confidence >= 0.2

    def test_author_contained_in_book_author(self):
        """Test when search author is contained in book author."""
        book = Book(
            id=1,
            title="Test",
            slug="test",
            authors=[Author(id=1, name="Stephen King Jr.")],
        )
        confidence = _calculate_match_confidence(book, "Test", ["Stephen King"])
        # Should get partial match score
        assert confidence >= 0.3

    def test_no_authors_provided(self):
        """Test matching without any authors."""
        book = Book(
            id=1,
            title="Exact Title",
            slug="test",
            authors=[Author(id=1, name="Some Author")],
        )
        confidence = _calculate_match_confidence(book, "Exact Title", None)
        # Should only get title score
        assert confidence == 0.6

    def test_book_has_no_authors(self):
        """Test matching when book has no authors."""
        book = Book(id=1, title="Exact Title", slug="test", authors=None)
        confidence = _calculate_match_confidence(book, "Exact Title", ["Some Author"])
        # Should only get title score
        assert confidence == 0.6

    def test_empty_authors_list(self):
        """Test matching with empty authors list."""
        book = Book(id=1, title="Exact Title", slug="test", authors=[])
        confidence = _calculate_match_confidence(book, "Exact Title", ["Some Author"])
        # Should only get title score
        assert confidence == 0.6


class TestMatchByISBNEdgeCases:
    """Additional tests for match_by_isbn edge cases."""

    @patch("hardcover_sync.matcher.get_cache")
    def test_cache_hit_but_book_not_found(self, mock_get_cache):
        """Test when cache has entry but API returns None for book."""
        from datetime import datetime

        from hardcover_sync.cache import CachedBook

        mock_cache = MagicMock()
        mock_cache.get_by_isbn.return_value = CachedBook(
            hardcover_id=123,
            edition_id=456,
            title="Cached Book",
            isbn="9780123456789",
            cached_at=datetime.now(),
        )
        mock_get_cache.return_value = mock_cache

        mock_api = MagicMock()
        mock_api.get_book_by_id.return_value = None
        mock_api.find_book_by_isbn.return_value = None

        result = match_by_isbn(mock_api, "9780123456789")

        # Should fall through to API search
        assert result.book is None

    @patch("hardcover_sync.matcher.get_cache")
    def test_api_match_no_editions(self, mock_get_cache):
        """Test API match with book that has no editions."""
        mock_cache = MagicMock()
        mock_cache.get_by_isbn.return_value = None
        mock_get_cache.return_value = mock_cache

        mock_api = MagicMock()
        mock_api.find_book_by_isbn.return_value = Book(
            id=789, title="Found Book", slug="found", editions=None
        )

        result = match_by_isbn(mock_api, "9780123456789")

        assert result.book is not None
        # Should cache with None edition_id
        mock_cache.set_isbn.assert_called_once_with("9780123456789", 789, None, "Found Book")
