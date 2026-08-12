"""Plain-Python orchestration services used by the Qt sync dialogs."""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Protocol

from .models import UserBook, UserBookRead
from .sync import NewBookAction, SyncChange, SyncToChange, build_sync_to_payloads


class OperationGuard:
    """Prevent a Qt event loop from re-entering a long-running operation."""

    def __init__(self) -> None:
        self.active = False

    def start(self) -> bool:
        if self.active:
            return False
        self.active = True
        return True

    def finish(self) -> None:
        self.active = False


class SyncAPI(Protocol):
    """API operations required by the sync-to apply service."""

    def update_user_book(
        self,
        user_book_id: int,
        status_id: int | None = None,
        rating: float | None = None,
        started_at: date | str | None = None,
        finished_at: date | str | None = None,
        review: str | None = None,
    ) -> UserBook: ...

    def add_book_to_library(
        self,
        book_id: int,
        status_id: int,
        edition_id: int | None = None,
        rating: float | None = None,
        started_at: date | str | None = None,
        finished_at: date | str | None = None,
        review: str | None = None,
    ) -> UserBook: ...

    def update_user_book_read(
        self,
        read_id: int,
        started_at: date | str | None = None,
        finished_at: date | str | None = None,
        progress_pages: int | None = None,
        edition_id: int | None = None,
    ) -> UserBookRead: ...

    def insert_user_book_read(
        self,
        user_book_id: int,
        started_at: date | str | None = None,
        finished_at: date | str | None = None,
        progress_pages: int | None = None,
        edition_id: int | None = None,
    ) -> UserBookRead: ...


@dataclass
class SyncToApplyResult:
    """Per-book outcome for applying sync-to changes."""

    applied: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)


def apply_sync_to_book(
    api: SyncAPI,
    hardcover_book_id: int,
    user_book_id: int | None,
    changes: list[SyncToChange],
    status_mappings: dict,
    current_user_book: UserBook | None = None,
) -> SyncToApplyResult:
    """Apply one book's selected changes and preserve partial-success details."""
    outcome = SyncToApplyResult()
    user_book_data, read_data = build_sync_to_payloads(changes, status_mappings)
    user_changes = [change for change in changes if change.field in {"status", "rating", "review"}]
    read_changes = [
        change
        for change in changes
        if change.field in {"progress", "progress_percent", "date_started", "date_read"}
    ]

    if not user_book_data and not read_data:
        outcome.failed = len(changes)
        outcome.errors.append("No valid update data")
        return outcome

    if user_book_id is not None and user_book_data:
        try:
            api.update_user_book(user_book_id, **user_book_data)
            outcome.applied += len(user_changes)
        except Exception as error:
            outcome.failed += len(user_changes)
            outcome.errors.append(f"Book details: {error}")
    elif user_book_id is None:
        create_data = dict(user_book_data)
        status_id = create_data.pop("status_id", None)
        if status_id is None:
            outcome.failed += len(user_changes) + len(read_changes)
            outcome.errors.append("Add to library: no mapped reading status")
            return outcome
        try:
            created_user_book = api.add_book_to_library(
                book_id=hardcover_book_id,
                status_id=status_id,
                **create_data,
            )
            user_book_id = created_user_book.id
            outcome.applied += len(user_changes)
        except Exception as error:
            outcome.failed += len(user_changes) + len(read_changes)
            outcome.errors.append(f"Add to library: {error}")
            return outcome

    if read_data and user_book_id is not None:
        try:
            if current_user_book and current_user_book.latest_read:
                api.update_user_book_read(current_user_book.latest_read.id, **read_data)
            else:
                api.insert_user_book_read(user_book_id, **read_data)
            outcome.applied += len(read_changes)
        except Exception as error:
            outcome.failed += len(read_changes)
            outcome.errors.append(f"Reading data: {error}")

    return outcome


def fetch_all_user_books(
    fetch_page: Callable[[int, int], list[UserBook]],
    *,
    page_size: int = 100,
    on_page: Callable[[], None] | None = None,
) -> list[UserBook]:
    """Fetch and deduplicate a paginated Hardcover library."""
    books: list[UserBook] = []
    seen_book_ids: set[int] = set()
    offset = 0

    while True:
        page = fetch_page(page_size, offset)
        for user_book in page:
            if user_book.book_id not in seen_book_ids:
                seen_book_ids.add(user_book.book_id)
                books.append(user_book)
        if len(page) < page_size:
            return books
        offset += page_size
        if on_page:
            on_page()


@dataclass
class SyncFromApplyResult:
    """Batch outcome for Calibre writes during sync-from."""

    created_books: int = 0
    applied_changes: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)


def apply_sync_from_batch(
    changes: list[SyncChange],
    new_books: list[NewBookAction],
    *,
    apply_change: Callable[[SyncChange], tuple[bool, str | None]],
    create_book: Callable[[NewBookAction], int | None],
    on_progress: Callable[[], None] | None = None,
) -> SyncFromApplyResult:
    """Apply selected Calibre creates and updates without Qt dependencies."""
    outcome = SyncFromApplyResult()

    for new_book in new_books:
        try:
            if create_book(new_book):
                outcome.created_books += 1
            else:
                outcome.skipped += 1
                outcome.errors.append(f"{new_book.title}: Failed to create book")
        except Exception as error:
            outcome.skipped += 1
            outcome.errors.append(f"{new_book.title}: {error}")
        if on_progress:
            on_progress()

    for change in changes:
        try:
            success, error_message = apply_change(change)
            if success:
                outcome.applied_changes += 1
            else:
                outcome.skipped += 1
                if error_message:
                    outcome.errors.append(f"{change.calibre_title}: {error_message}")
        except Exception as error:
            outcome.skipped += 1
            outcome.errors.append(f"{change.calibre_title}: {error}")
        if on_progress:
            on_progress()

    return outcome
