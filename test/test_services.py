"""Tests for synchronization orchestration services."""

from unittest.mock import Mock

from hardcover_sync.models import Book, UserBook
from hardcover_sync.services import apply_sync_from_batch, fetch_all_user_books
from hardcover_sync.sync import NewBookAction, SyncChange


def user_book(book_id: int, record_id: int) -> UserBook:
    return UserBook(id=record_id, book_id=book_id)


class TestFetchAllUserBooks:
    def test_paginates_and_deduplicates_by_book_id(self):
        pages = {
            0: [user_book(1, 10), user_book(2, 20)],
            2: [user_book(2, 21), user_book(3, 30)],
            4: [user_book(4, 40)],
        }
        fetch_page = Mock(side_effect=lambda limit, offset: pages[offset])
        on_page = Mock()

        result = fetch_all_user_books(fetch_page, page_size=2, on_page=on_page)

        assert [book.book_id for book in result] == [1, 2, 3, 4]
        assert [book.id for book in result] == [10, 20, 30, 40]
        assert fetch_page.call_count == 3
        assert on_page.call_count == 2

    def test_empty_library(self):
        assert fetch_all_user_books(lambda limit, offset: []) == []


class TestApplySyncFromBatch:
    @staticmethod
    def new_book(title: str) -> NewBookAction:
        hardcover_book = Book(id=100, title=title, slug="test")
        return NewBookAction(
            hardcover_book_id=100,
            title=title,
            authors=[],
            user_book=UserBook(id=10, book_id=100, book=hardcover_book),
        )

    @staticmethod
    def change(title: str) -> SyncChange:
        return SyncChange(
            calibre_id=1,
            calibre_title=title,
            hardcover_book_id=100,
            field="rating",
            old_value="1",
            new_value="2",
        )

    def test_collects_successes_failures_and_progress(self):
        new_books = [self.new_book("Created"), self.new_book("Create failed")]
        changes = [self.change("Updated"), self.change("Update skipped")]
        create_book = Mock(side_effect=[42, RuntimeError("database error")])
        apply_change = Mock(side_effect=[(True, None), (False, "invalid column")])
        on_progress = Mock()

        result = apply_sync_from_batch(
            changes,
            new_books,
            create_book=create_book,
            apply_change=apply_change,
            on_progress=on_progress,
        )

        assert result.created_books == 1
        assert result.applied_changes == 1
        assert result.skipped == 2
        assert result.errors == [
            "Create failed: database error",
            "Update skipped: invalid column",
        ]
        assert on_progress.call_count == 4
