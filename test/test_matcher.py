"""
Tests for the matcher module.
"""

from unittest.mock import MagicMock, patch


from hardcover_sync.api import Author, Book, Edition
from hardcover_sync.matcher import (
    MatchResult,
    _calculate_match_confidence,
    _format_book_description,
    match_by_isbn,
    match_by_search,
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
