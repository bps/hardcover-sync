"""
Sync logic for Hardcover Sync plugin.

This module contains the core business logic for syncing data between
Hardcover and Calibre, extracted from the dialog classes for testability.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .models import UserBook
from .config import READING_STATUSES, STATUS_IDS, get_column_mappings


# Display names for sync field types
FIELD_DISPLAY_NAMES = {
    "status": "Reading Status",
    "rating": "Rating",
    "progress": "Progress (pages)",
    "progress_percent": "Progress (%)",
    "date_started": "Date Started",
    "date_read": "Date Read",
    "is_read": "Is Read",
    "review": "Review",
}


def truncate_for_display(text: str | None, *, max_length: int = 50, empty: str = "(empty)") -> str:
    """Truncate text for display in change previews.

    Args:
        text: The text to truncate, or None.
        max_length: Maximum length before truncation.
        empty: Placeholder when text is falsy.

    Returns:
        The truncated text with "..." suffix, or the empty placeholder.
    """
    if not text:
        return empty
    if len(text) > max_length:
        return text[:max_length] + "..."
    return text


@dataclass
class BaseSyncChange:
    """Shared fields for sync change dataclasses."""

    calibre_id: int
    calibre_title: str
    hardcover_book_id: int
    field: str  # status, rating, progress, progress_percent, date_started, date_read, review
    old_value: str | None
    new_value: str | None

    @property
    def display_field(self) -> str:
        """Get a display-friendly field name."""
        return FIELD_DISPLAY_NAMES.get(self.field, self.field)


@dataclass
class SyncChange(BaseSyncChange):
    """Represents a change to be synced from Hardcover to Calibre."""

    raw_value: str | None = None  # Raw value for applying (if different from display)
    apply: bool = True  # Whether to apply this change
    hardcover_slug: str | None = None  # Slug for identifier storage

    @property
    def api_value(self) -> str | None:
        """Get the value to apply to Calibre."""
        return self.raw_value if self.raw_value is not None else self.new_value


@dataclass
class SyncToChange(BaseSyncChange):
    """Represents a change to be synced from Calibre to Hardcover."""

    user_book_id: int | None = None  # None if book not in Hardcover library
    api_value: Any = None  # The value to send to the API
    apply: bool = True


@dataclass
class NewBookAction:
    """Represents a new book to create in Calibre from Hardcover."""

    hardcover_book_id: int
    title: str
    authors: list[str]
    user_book: UserBook
    isbn: str | None = None
    release_date: str | None = None
    apply: bool = True
    hardcover_slug: str | None = None  # Slug for identifier storage

    @property
    def author_string(self) -> str:
        """Get authors as a comma-separated string."""
        return ", ".join(self.authors) if self.authors else "Unknown"


def format_rating_as_stars(rating: float | None) -> str:
    """
    Format a rating (0-5) as star characters for display.

    Args:
        rating: Rating value from 0-5, or None.

    Returns:
        String of star characters (e.g., "★★★☆☆" for 3 stars).
    """
    if rating is None:
        return "(no rating)"

    full_stars = int(rating)
    half_star = rating - full_stars >= 0.5
    empty_stars = 5 - full_stars - (1 if half_star else 0)

    result = "★" * full_stars
    if half_star:
        result += "½"
    result += "☆" * empty_stars

    return result or "☆☆☆☆☆"


def _is_calibre_rating_column(column_name: str, column_metadata: dict | None = None) -> bool:
    """Check if a Calibre column uses the built-in 0-10 rating scale.

    This is true for the built-in ``rating`` column and for custom columns
    whose ``datatype`` is ``"rating"``.
    """
    if column_name == "rating":
        return True
    return bool(
        column_name.startswith("#")
        and column_metadata
        and column_metadata.get("datatype") == "rating"
    )


def convert_rating_to_calibre(
    hc_rating: float,
    column_name: str,
    column_metadata: dict | None = None,
) -> tuple[str, float | None]:
    """
    Convert a Hardcover rating (0-5) to Calibre format.

    Args:
        hc_rating: Hardcover rating (0-5 scale).
        column_name: The Calibre column name.
        column_metadata: Optional metadata about custom columns.

    Returns:
        Tuple of (raw_value_string, display_rating_for_stars).
    """
    if _is_calibre_rating_column(column_name, column_metadata):
        # Rating columns use 0-10 internally (displayed as stars)
        return str(int(hc_rating * 2)), hc_rating
    # Other column types (int, float) - store as 0-5
    return str(hc_rating), hc_rating


def convert_rating_from_calibre(
    calibre_rating: Any,
    column_name: str,
    column_metadata: dict | None = None,
) -> float | None:
    """
    Convert a Calibre rating to Hardcover format (0-5).

    Args:
        calibre_rating: The Calibre rating value.
        column_name: The Calibre column name.
        column_metadata: Optional metadata about custom columns.

    Returns:
        Rating in 0-5 scale, or None.
    """
    if calibre_rating is None:
        return None

    try:
        rating = float(calibre_rating)
    except (ValueError, TypeError):
        return None

    if _is_calibre_rating_column(column_name, column_metadata):
        # Rating columns use 0-10, convert to 0-5
        return rating / 2
    return rating


def get_status_from_hardcover(status_id: int, status_mappings: dict) -> str | None:
    """
    Get the Calibre status value for a Hardcover status ID.

    Args:
        status_id: Hardcover status ID (1-6).
        status_mappings: User-configured status mappings (str(id) -> calibre_value).

    Returns:
        Calibre status string, or None if not mapped.
    """
    # Check user-configured mapping first
    mapped = status_mappings.get(str(status_id))
    if mapped:
        return mapped

    # Fall back to default status names
    return READING_STATUSES.get(status_id)


def get_status_from_calibre(calibre_status: str, status_mappings: dict) -> int | None:
    """
    Get the Hardcover status ID for a Calibre status value.

    Args:
        calibre_status: Calibre status string.
        status_mappings: User-configured status mappings (str(id) -> calibre_value).

    Returns:
        Hardcover status ID (1-6), or None if not mapped.
    """
    # Build reverse mapping
    calibre_to_hc = {v: int(k) for k, v in status_mappings.items()}

    # Check user-configured mapping first
    if calibre_status in calibre_to_hc:
        return calibre_to_hc[calibre_status]

    # Fall back to default status names
    return STATUS_IDS.get(calibre_status)


def extract_date(date_str: str | None) -> str | None:
    """
    Extract a date string from various formats.

    Args:
        date_str: Date string in various formats (ISO, with time, etc.).

    Returns:
        Date in YYYY-MM-DD format, or None.
    """
    if not date_str:
        return None

    # Handle ISO format with time
    if "T" in date_str:
        return date_str.split("T")[0]

    # Handle space-separated datetime
    if " " in date_str:
        return date_str.split(" ")[0]

    return date_str


def find_sync_from_changes(
    hardcover_books: list[UserBook],
    hc_to_calibre: dict[str, int],
    get_calibre_value: Callable[[int, str], Any],
    get_calibre_title: Callable[[int], str],
    prefs: dict,
    get_column_metadata: Callable[[str], dict | None] | None = None,
) -> list[SyncChange]:
    """
    Find all changes to sync from Hardcover to Calibre.

    Args:
        hardcover_books: List of UserBook objects from Hardcover.
        hc_to_calibre: Mapping of Hardcover book slug -> Calibre book ID.
        get_calibre_value: Function(calibre_id, column) -> value.
        get_calibre_title: Function(calibre_id) -> title string.
        prefs: Plugin preferences dict.
        get_column_metadata: Optional function(column) -> metadata dict.

    Returns:
        List of SyncChange objects representing needed updates.
    """
    changes = []

    # Get column mappings
    col = get_column_mappings(prefs)
    status_col = col.get("status", "")
    rating_col = col.get("rating", "")
    progress_col = col.get("progress", "")
    progress_percent_col = col.get("progress_percent", "")
    date_started_col = col.get("date_started", "")
    date_read_col = col.get("date_read", "")
    is_read_col = col.get("is_read", "")
    review_col = col.get("review", "")

    # Get sync options
    sync_rating = prefs.get("sync_rating", True)
    sync_progress = prefs.get("sync_progress", True)
    sync_dates = prefs.get("sync_dates", True)
    sync_review = prefs.get("sync_review", True)

    # Get status mappings
    status_mappings = prefs.get("status_mappings", {})

    for hc_book in hardcover_books:
        hc_slug = hc_book.book.slug if hc_book.book else None
        calibre_id = hc_to_calibre.get(hc_slug) if hc_slug else None
        if not calibre_id:
            continue

        calibre_title = get_calibre_title(calibre_id)

        # Check status
        if status_col and hc_book.status_id:
            hc_status_value = get_status_from_hardcover(hc_book.status_id, status_mappings)
            if hc_status_value:
                current = get_calibre_value(calibre_id, status_col)
                if current != hc_status_value:
                    changes.append(
                        SyncChange(
                            calibre_id=calibre_id,
                            calibre_title=calibre_title,
                            hardcover_book_id=hc_book.book_id,
                            field="status",
                            old_value=current or "(empty)",
                            new_value=hc_status_value,
                        )
                    )

        # Check rating
        if sync_rating and rating_col and hc_book.rating is not None:
            current = get_calibre_value(calibre_id, rating_col)
            col_meta = get_column_metadata(rating_col) if get_column_metadata else None
            new_rating, _ = convert_rating_to_calibre(hc_book.rating, rating_col, col_meta)
            current_for_stars = convert_rating_from_calibre(current, rating_col, col_meta)

            if str(current) != new_rating:
                changes.append(
                    SyncChange(
                        calibre_id=calibre_id,
                        calibre_title=calibre_title,
                        hardcover_book_id=hc_book.book_id,
                        field="rating",
                        old_value=format_rating_as_stars(current_for_stars),
                        new_value=format_rating_as_stars(hc_book.rating),
                        raw_value=new_rating,
                    )
                )

        # Check progress
        current_progress = hc_book.current_progress_pages
        if sync_progress and progress_col and current_progress is not None:
            current = get_calibre_value(calibre_id, progress_col)
            new_progress = str(current_progress)
            if str(current) != new_progress:
                changes.append(
                    SyncChange(
                        calibre_id=calibre_id,
                        calibre_title=calibre_title,
                        hardcover_book_id=hc_book.book_id,
                        field="progress",
                        old_value=str(current) if current else "(empty)",
                        new_value=new_progress,
                    )
                )

        # Check progress percent
        current_progress_pct = hc_book.current_progress_percent
        if sync_progress and progress_percent_col and current_progress_pct is not None:
            current = get_calibre_value(calibre_id, progress_percent_col)
            new_progress_pct = round(current_progress_pct, 1)
            current_rounded = round(float(current), 1) if current else None
            if current_rounded != new_progress_pct:
                changes.append(
                    SyncChange(
                        calibre_id=calibre_id,
                        calibre_title=calibre_title,
                        hardcover_book_id=hc_book.book_id,
                        field="progress_percent",
                        old_value=f"{current_rounded}%"
                        if current_rounded is not None
                        else "(empty)",
                        new_value=f"{new_progress_pct}%",
                        raw_value=str(new_progress_pct),
                    )
                )

        # Check dates (use latest_* properties to get dates from reads list)
        if sync_dates:
            started_at = hc_book.latest_started_at
            finished_at = hc_book.latest_finished_at

            if date_started_col and started_at:
                new_date = extract_date(started_at)
                if new_date:
                    current = get_calibre_value(calibre_id, date_started_col)
                    current_date = extract_date(str(current)) if current else None
                    if current_date != new_date:
                        changes.append(
                            SyncChange(
                                calibre_id=calibre_id,
                                calibre_title=calibre_title,
                                hardcover_book_id=hc_book.book_id,
                                field="date_started",
                                old_value=current_date or "(empty)",
                                new_value=new_date,
                            )
                        )

            if date_read_col and finished_at:
                new_date = extract_date(finished_at)
                if new_date:
                    current = get_calibre_value(calibre_id, date_read_col)
                    current_date = extract_date(str(current)) if current else None
                    if current_date != new_date:
                        changes.append(
                            SyncChange(
                                calibre_id=calibre_id,
                                calibre_title=calibre_title,
                                hardcover_book_id=hc_book.book_id,
                                field="date_read",
                                old_value=current_date or "(empty)",
                                new_value=new_date,
                            )
                        )

        # Check is_read boolean (Yes when status is "Read", i.e. status_id == 3)
        if is_read_col:
            is_read = hc_book.status_id == 3
            current = get_calibre_value(calibre_id, is_read_col)
            # Normalize current value to boolean for comparison
            current_bool = bool(current) if current is not None else False
            if current_bool != is_read:
                changes.append(
                    SyncChange(
                        calibre_id=calibre_id,
                        calibre_title=calibre_title,
                        hardcover_book_id=hc_book.book_id,
                        field="is_read",
                        old_value="Yes" if current_bool else "No",
                        new_value="Yes" if is_read else "No",
                        raw_value="Yes" if is_read else "",
                    )
                )

        # Check review
        if sync_review and review_col and hc_book.review:
            current = get_calibre_value(calibre_id, review_col)
            if current != hc_book.review:
                changes.append(
                    SyncChange(
                        calibre_id=calibre_id,
                        calibre_title=calibre_title,
                        hardcover_book_id=hc_book.book_id,
                        field="review",
                        old_value=truncate_for_display(current),
                        new_value=truncate_for_display(hc_book.review),
                    )
                )

    return changes


@dataclass
class SyncToResult:
    """Result of analyzing books for sync-to-Hardcover changes.

    Attributes:
        changes: List of SyncToChange objects representing needed updates.
        hardcover_data: Mapping of Hardcover book ID -> UserBook for apply phase.
        linked_count: Number of books that were linked to Hardcover.
        not_linked_count: Number of books skipped (not linked).
        api_errors: Number of API errors encountered.
        books_with_changes: Number of books that had at least one change.
    """

    changes: list[SyncToChange] = field(default_factory=list)
    hardcover_data: dict[int, UserBook] = field(default_factory=dict)
    linked_count: int = 0
    not_linked_count: int = 0
    api_errors: int = 0
    books_with_changes: int = 0


def find_sync_to_changes(
    book_ids: list[int],
    get_identifiers: Callable[[int], dict[str, str]],
    get_calibre_value: Callable[[int, str], Any],
    get_calibre_title: Callable[[int], str],
    resolve_book: Callable[[str], Any],
    get_user_book: Callable[[int], UserBook | None],
    prefs: dict,
    get_column_metadata: Callable[[str], dict | None] | None = None,
    on_progress: Callable[[int], None] | None = None,
) -> SyncToResult:
    """
    Find all changes to sync from Calibre to Hardcover.

    This is the sync-to counterpart of find_sync_from_changes(). It compares
    Calibre column values against Hardcover data and produces SyncToChange
    objects for each difference found.

    Args:
        book_ids: List of Calibre book IDs to analyze.
        get_identifiers: Function(calibre_id) -> identifiers dict.
        get_calibre_value: Function(calibre_id, column) -> value.
        get_calibre_title: Function(calibre_id) -> title string.
        resolve_book: Function(slug_or_id) -> Book | None.
        get_user_book: Function(hardcover_book_id) -> UserBook | None.
        prefs: Plugin preferences dict.
        get_column_metadata: Optional function(column) -> metadata dict.
        on_progress: Optional callback(index) called after each book is processed.

    Returns:
        SyncToResult with changes, hardcover_data, and statistics.
    """
    result = SyncToResult()

    # Get column mappings
    col = get_column_mappings(prefs)
    status_col = col.get("status", "")
    rating_col = col.get("rating", "")
    progress_col = col.get("progress", "")
    progress_percent_col = col.get("progress_percent", "")
    date_started_col = col.get("date_started", "")
    date_read_col = col.get("date_read", "")
    review_col = col.get("review", "")

    # Get status mappings (reverse: Calibre value -> Hardcover ID)
    status_mappings = prefs.get("status_mappings", {})
    calibre_to_hc_status = {v: int(k) for k, v in status_mappings.items()}

    for i, book_id in enumerate(book_ids):
        if on_progress:
            on_progress(i + 1)

        # Check if book is linked to Hardcover
        identifiers = get_identifiers(book_id)
        hc_id_str = identifiers.get("hardcover")
        if not hc_id_str:
            result.not_linked_count += 1
            continue

        hc_book = resolve_book(hc_id_str)
        if not hc_book:
            result.not_linked_count += 1
            continue
        hc_book_id = hc_book.id

        result.linked_count += 1
        calibre_title = get_calibre_title(book_id)

        # Fetch current Hardcover data for this book
        hc_user_book: UserBook | None = None
        try:
            hc_user_book = get_user_book(hc_book_id)
            if hc_user_book:
                result.hardcover_data[hc_book_id] = hc_user_book
        except Exception:  # noqa: S110
            result.api_errors += 1

        user_book_id = hc_user_book.id if hc_user_book else None

        # Track if this book has any Calibre data to sync
        book_has_changes = False

        # Compare status
        if status_col:
            calibre_status = get_calibre_value(book_id, status_col)
            if calibre_status:
                hc_status_id = calibre_to_hc_status.get(calibre_status)
                if hc_status_id is None:
                    # Try direct match with status name
                    hc_status_id = STATUS_IDS.get(calibre_status)

                if hc_status_id:
                    hc_current_status = (
                        READING_STATUSES.get(hc_user_book.status_id)
                        if hc_user_book and hc_user_book.status_id
                        else None
                    )
                    if hc_current_status != calibre_status:
                        result.changes.append(
                            SyncToChange(
                                calibre_id=book_id,
                                calibre_title=calibre_title,
                                hardcover_book_id=hc_book_id,
                                user_book_id=user_book_id,
                                field="status",
                                old_value=hc_current_status or "(not in library)",
                                new_value=calibre_status,
                            )
                        )
                        book_has_changes = True

        # Compare rating
        if rating_col:
            calibre_rating = get_calibre_value(book_id, rating_col)
            if calibre_rating is not None:
                # Convert Calibre rating to Hardcover scale (0-5)
                col_info = get_column_metadata(rating_col) if get_column_metadata else None
                hc_new_rating = convert_rating_from_calibre(calibre_rating, rating_col, col_info)

                hc_current_rating = hc_user_book.rating if hc_user_book else None
                if hc_new_rating != hc_current_rating:
                    result.changes.append(
                        SyncToChange(
                            calibre_id=book_id,
                            calibre_title=calibre_title,
                            hardcover_book_id=hc_book_id,
                            user_book_id=user_book_id,
                            field="rating",
                            old_value=format_rating_as_stars(hc_current_rating),
                            new_value=format_rating_as_stars(hc_new_rating),
                            api_value=hc_new_rating,
                        )
                    )
                    book_has_changes = True

        # Compare progress (pages)
        if progress_col:
            calibre_progress = get_calibre_value(book_id, progress_col)
            if calibre_progress is not None:
                hc_current_progress = hc_user_book.current_progress_pages if hc_user_book else None
                if calibre_progress != hc_current_progress:
                    result.changes.append(
                        SyncToChange(
                            calibre_id=book_id,
                            calibre_title=calibre_title,
                            hardcover_book_id=hc_book_id,
                            user_book_id=user_book_id,
                            field="progress",
                            old_value=str(hc_current_progress)
                            if hc_current_progress is not None
                            else "(empty)",
                            new_value=str(calibre_progress),
                        )
                    )
                    book_has_changes = True

        # Compare progress (percent)
        if progress_percent_col:
            calibre_progress_pct = get_calibre_value(book_id, progress_percent_col)
            if calibre_progress_pct is not None:
                hc_current_pct = hc_user_book.current_progress_percent if hc_user_book else None
                # Round for comparison
                calibre_rounded = round(float(calibre_progress_pct), 1)
                hc_rounded = round(hc_current_pct, 1) if hc_current_pct is not None else None
                if calibre_rounded != hc_rounded:
                    result.changes.append(
                        SyncToChange(
                            calibre_id=book_id,
                            calibre_title=calibre_title,
                            hardcover_book_id=hc_book_id,
                            user_book_id=user_book_id,
                            field="progress_percent",
                            old_value=f"{hc_rounded}%" if hc_rounded is not None else "(empty)",
                            new_value=f"{calibre_rounded}%",
                            api_value=calibre_rounded / 100,  # Convert to 0.0-1.0 for API
                        )
                    )
                    book_has_changes = True

        # Compare date started
        if date_started_col:
            calibre_date = get_calibre_value(book_id, date_started_col)
            if calibre_date:
                calibre_date_str = str(calibre_date)[:10]
                hc_current_date = (
                    hc_user_book.latest_started_at[:10]
                    if hc_user_book and hc_user_book.latest_started_at
                    else None
                )
                if calibre_date_str != hc_current_date:
                    result.changes.append(
                        SyncToChange(
                            calibre_id=book_id,
                            calibre_title=calibre_title,
                            hardcover_book_id=hc_book_id,
                            user_book_id=user_book_id,
                            field="date_started",
                            old_value=hc_current_date or "(empty)",
                            new_value=calibre_date_str,
                        )
                    )
                    book_has_changes = True

        # Compare date read
        if date_read_col:
            calibre_date = get_calibre_value(book_id, date_read_col)
            if calibre_date:
                calibre_date_str = str(calibre_date)[:10]
                hc_current_date = (
                    hc_user_book.latest_finished_at[:10]
                    if hc_user_book and hc_user_book.latest_finished_at
                    else None
                )
                if calibre_date_str != hc_current_date:
                    result.changes.append(
                        SyncToChange(
                            calibre_id=book_id,
                            calibre_title=calibre_title,
                            hardcover_book_id=hc_book_id,
                            user_book_id=user_book_id,
                            field="date_read",
                            old_value=hc_current_date or "(empty)",
                            new_value=calibre_date_str,
                        )
                    )
                    book_has_changes = True

        # Compare review
        if review_col:
            calibre_review = get_calibre_value(book_id, review_col)
            if calibre_review:
                hc_current_review = hc_user_book.review if hc_user_book else None
                if calibre_review != hc_current_review:
                    result.changes.append(
                        SyncToChange(
                            calibre_id=book_id,
                            calibre_title=calibre_title,
                            hardcover_book_id=hc_book_id,
                            user_book_id=user_book_id,
                            field="review",
                            old_value=truncate_for_display(hc_current_review),
                            new_value=truncate_for_display(calibre_review),
                        )
                    )
                    book_has_changes = True

        if book_has_changes:
            result.books_with_changes += 1

    return result


def find_new_books(
    hardcover_books: list[UserBook],
    hc_to_calibre: dict[str, int],
    sync_statuses: list[int] | None = None,
) -> list[NewBookAction]:
    """
    Find Hardcover books that aren't in Calibre yet.

    Args:
        hardcover_books: List of UserBook objects from Hardcover.
        hc_to_calibre: Mapping of Hardcover book slug -> Calibre book ID.
        sync_statuses: List of status IDs to include (empty/None = all).

    Returns:
        List of NewBookAction objects for books to create.
    """
    new_books = []

    for hc_book in hardcover_books:
        # Skip books without book metadata
        if not hc_book.book:
            continue

        # Skip books that are already linked to Calibre
        hc_slug = hc_book.book.slug
        if hc_slug and hc_slug in hc_to_calibre:
            continue

        # Skip if status is not in the sync filter (when filter is set)
        if sync_statuses and hc_book.status_id not in sync_statuses:
            continue

        # Extract metadata
        title = hc_book.book.title
        authors = []
        if hc_book.book.authors:
            authors = [a.name for a in hc_book.book.authors]

        # Get ISBN from editions
        isbn = None
        if hc_book.edition and hc_book.edition.isbn_13:
            isbn = hc_book.edition.isbn_13
        elif hc_book.edition and hc_book.edition.isbn_10:
            isbn = hc_book.edition.isbn_10
        elif hc_book.book.editions:
            for ed in hc_book.book.editions:
                if ed.isbn_13:
                    isbn = ed.isbn_13
                    break
                elif ed.isbn_10:
                    isbn = ed.isbn_10
                    break

        new_books.append(
            NewBookAction(
                hardcover_book_id=hc_book.book_id,
                hardcover_slug=hc_book.book.slug,
                title=title,
                authors=authors,
                user_book=hc_book,
                isbn=isbn,
                release_date=hc_book.book.release_date,
            )
        )

    return new_books


def coerce_value_for_column(value: Any, datatype: str) -> Any:
    """Coerce a string value to the type expected by Calibre for a given column datatype.

    This handles the conversion from string API values (as stored in SyncChange)
    to the native Python types that Calibre's db.set_field() expects.

    Args:
            value: The string value to coerce, a bool, or None.
            datatype: The Calibre column datatype (e.g., "int", "float", "datetime",
                                "rating", "bool", "text", "comments").

    Returns:
            The coerced value in the appropriate Python type.
    """
    if value is None or (isinstance(value, str) and value == ""):
        return None

    if datatype == "int":
        return int(value)
    elif datatype == "float":
        return float(value)
    elif datatype == "datetime":
        from datetime import datetime

        return datetime.fromisoformat(str(value))
    elif datatype == "rating":
        return int(float(value))
    elif datatype == "bool":
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("yes", "true", "1")
        return bool(value)
    else:
        # text, comments, etc. - return as-is
        return value
