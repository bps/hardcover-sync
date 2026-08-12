"""
Sync logic for Hardcover Sync plugin.

This module contains the core business logic for syncing data between
Hardcover and Calibre, extracted from the dialog classes for testability.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from html import unescape
from html.parser import HTMLParser
from typing import Any

from .models import Book, Edition, UserBook
from .config import READING_STATUSES, get_column_mappings, get_status_mapping_conflicts


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


class _ReviewHTMLParser(HTMLParser):
    """Convert the small HTML subset used by Calibre comments to plain text."""

    _BLOCK_TAGS = {"br", "div", "li", "p"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._BLOCK_TAGS and self.parts:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def normalize_review_text(text: str | None) -> str:
    """Normalize Calibre HTML comments and Hardcover text for comparison/writes."""
    if not text:
        return ""
    parser = _ReviewHTMLParser()
    parser.feed(text)
    lines = [line.strip() for line in unescape("".join(parser.parts)).splitlines()]
    return "\n".join(line for line in lines if line)


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
    edition_id: int | None = None  # Edition associated with a progress update
    apply: bool = True


def build_sync_to_payloads(
    changes: list[SyncToChange], status_mappings: dict
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build Hardcover user-book and read payloads from selected changes."""
    user_book_data: dict[str, Any] = {}
    read_data: dict[str, Any] = {}
    has_page_progress = any(change.field == "progress" for change in changes)

    for change in changes:
        if change.field == "status" and change.new_value:
            status_id = int(change.api_value) if change.api_value is not None else None
            if status_id is None:
                status_id = get_status_from_calibre(change.new_value, status_mappings)
            if status_id:
                user_book_data["status_id"] = status_id
        elif change.field == "rating":
            user_book_data["rating"] = (
                float(change.api_value) if change.api_value is not None else None
            )
        elif change.field == "progress":
            read_data["progress_pages"] = (
                int(change.api_value) if change.api_value is not None else None
            )
            if change.edition_id is not None:
                read_data["edition_id"] = change.edition_id
        elif change.field == "progress_percent" and not has_page_progress:
            read_data["progress_pages"] = (
                int(change.api_value) if change.api_value is not None else None
            )
            if change.edition_id is not None:
                read_data["edition_id"] = change.edition_id
        elif change.field == "date_started":
            read_data["started_at"] = change.api_value or change.new_value
        elif change.field == "date_read":
            read_data["finished_at"] = change.api_value or change.new_value
        elif change.field == "review":
            user_book_data["review"] = change.api_value or change.new_value

    return user_book_data, read_data


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


def normalize_progress_percent(value: Any, datatype: str | None = None) -> int | float | None:
    """Normalize a percentage for comparison and storage in a Calibre column."""
    if value is None or value == "":
        return None

    numeric_value = float(value)
    if datatype == "int":
        # Do not round incomplete progress up to 100%.
        return int(numeric_value)
    return round(numeric_value, 1)


def _positive_int(value: Any) -> int | None:
    """Return a positive integer ID, or None."""
    try:
        result = int(value)
    except (TypeError, ValueError):
        return None
    return result if result > 0 else None


def _find_edition(book: Book, edition_id: int) -> Edition | None:
    """Find an edition in a resolved book."""
    return next((edition for edition in book.editions or [] if edition.id == edition_id), None)


def _progress_basis(
    identifiers: dict[str, str],
    book: Book,
    user_book: UserBook | None,
) -> tuple[int | None, int | None, str | None]:
    """Choose the edition and page count used to convert percentage progress."""
    latest_read = user_book.latest_read if user_book else None
    if latest_read:
        if latest_read.edition_id:
            edition = latest_read.edition or _find_edition(book, latest_read.edition_id)
            if edition and edition.pages and edition.pages > 0:
                return latest_read.edition_id, edition.pages, None
            if edition is None:
                return latest_read.edition_id, None, "the current read edition was not found"
            return (
                latest_read.edition_id,
                None,
                "the current Hardcover read edition has no page count",
            )
        if book.pages and book.pages > 0:
            # Preserve Hardcover's existing no-edition basis for this read.
            return None, book.pages, None
        return None, None, "the current Hardcover read has no usable book page count"

    linked_edition_id = _positive_int(identifiers.get("hardcover-edition"))
    if linked_edition_id:
        edition = _find_edition(book, linked_edition_id)
        if edition is None:
            return linked_edition_id, None, "the linked Hardcover edition was not found"
        if edition.pages and edition.pages > 0:
            return linked_edition_id, edition.pages, None
        return linked_edition_id, None, "the linked Hardcover edition has no page count"

    if user_book and user_book.edition_id:
        edition = user_book.edition or _find_edition(book, user_book.edition_id)
        if edition is None:
            return user_book.edition_id, None, "the selected Hardcover edition was not found"
        if edition.pages and edition.pages > 0:
            return user_book.edition_id, edition.pages, None
        return user_book.edition_id, None, "the selected Hardcover edition has no page count"

    if book.pages and book.pages > 0:
        # With no edition selected, Hardcover itself computes progress against book.pages.
        return None, book.pages, None

    return None, None, "Hardcover has no edition page count"


def _progress_edition_id(identifiers: dict[str, str], user_book: UserBook | None) -> int | None:
    """Choose an edition for a direct page-progress update without changing an existing read."""
    latest_read = user_book.latest_read if user_book else None
    if latest_read:
        return latest_read.edition_id
    return _positive_int(identifiers.get("hardcover-edition")) or (
        user_book.edition_id if user_book else None
    )


def get_status_from_calibre(calibre_status: str, status_mappings: dict) -> int | None:
    """Get the unambiguous Hardcover status ID for a Calibre value.

    Blank mappings use Hardcover's default status names. If configured and
    default values collide, the value is ambiguous and is not synchronized.
    """
    matches = [
        status_id
        for status_id, default_name in READING_STATUSES.items()
        if (status_mappings.get(str(status_id)) or default_name) == calibre_status
    ]
    return matches[0] if len(matches) == 1 else None


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


@dataclass
class _SyncFromContext:
    user_book: UserBook
    calibre_id: int
    calibre_title: str
    columns: dict[str, str]
    prefs: dict
    get_value: Callable[[int, str], Any]
    get_metadata: Callable[[str], dict | None] | None

    def change(
        self,
        field: str,
        old_value: str | None,
        new_value: str | None,
        *,
        raw_value: str | None = None,
    ) -> SyncChange:
        return SyncChange(
            calibre_id=self.calibre_id,
            calibre_title=self.calibre_title,
            hardcover_book_id=self.user_book.book_id,
            field=field,
            old_value=old_value,
            new_value=new_value,
            raw_value=raw_value,
        )


def _compare_sync_from_status(context: _SyncFromContext) -> list[SyncChange]:
    column = context.columns.get("status")
    status_id = context.user_book.status_id
    included_statuses = context.prefs.get("sync_statuses", [])
    if not column or not status_id or (included_statuses and status_id not in included_statuses):
        return []
    new_value = get_status_from_hardcover(status_id, context.prefs.get("status_mappings", {}))
    current = context.get_value(context.calibre_id, column)
    if not new_value or current == new_value:
        return []
    return [context.change("status", current or "(empty)", new_value)]


def _compare_sync_from_rating(context: _SyncFromContext) -> list[SyncChange]:
    column = context.columns.get("rating")
    rating = context.user_book.rating
    if not context.prefs.get("sync_rating", True) or not column or rating is None:
        return []
    current = context.get_value(context.calibre_id, column)
    metadata = context.get_metadata(column) if context.get_metadata else None
    new_rating, _ = convert_rating_to_calibre(rating, column, metadata)
    if str(current) == new_rating:
        return []
    current_stars = convert_rating_from_calibre(current, column, metadata)
    return [
        context.change(
            "rating",
            format_rating_as_stars(current_stars),
            format_rating_as_stars(rating),
            raw_value=new_rating,
        )
    ]


def _compare_sync_from_progress(context: _SyncFromContext) -> list[SyncChange]:
    if not context.prefs.get("sync_progress", True):
        return []
    changes = []
    pages_column = context.columns.get("progress")
    pages = context.user_book.current_progress_pages
    if pages_column and pages is not None:
        current = context.get_value(context.calibre_id, pages_column)
        new_value = str(pages)
        if str(current) != new_value:
            changes.append(
                context.change(
                    "progress",
                    str(current) if current else "(empty)",
                    new_value,
                )
            )

    percent_column = context.columns.get("progress_percent")
    percent = context.user_book.current_progress_percent
    if percent_column and percent is not None:
        current = context.get_value(context.calibre_id, percent_column)
        metadata = context.get_metadata(percent_column) if context.get_metadata else None
        datatype = metadata.get("datatype") if metadata else None
        new_percent = normalize_progress_percent(percent, datatype)
        try:
            current_percent = normalize_progress_percent(current, datatype)
        except (TypeError, ValueError):
            current_percent = None
        if current_percent != new_percent:
            changes.append(
                context.change(
                    "progress_percent",
                    f"{current_percent}%" if current_percent is not None else "(empty)",
                    f"{new_percent}%",
                    raw_value=str(new_percent),
                )
            )
    return changes


def _compare_sync_from_dates(context: _SyncFromContext) -> list[SyncChange]:
    if not context.prefs.get("sync_dates", True):
        return []
    changes = []
    date_fields = (
        ("date_started", context.user_book.latest_started_at),
        ("date_read", context.user_book.latest_finished_at),
    )
    for field_name, hardcover_date in date_fields:
        column = context.columns.get(field_name)
        new_date = extract_date(hardcover_date)
        if not column or not new_date:
            continue
        current = context.get_value(context.calibre_id, column)
        current_date = extract_date(str(current)) if current else None
        if current_date != new_date:
            changes.append(context.change(field_name, current_date or "(empty)", new_date))
    return changes


def _compare_sync_from_is_read(context: _SyncFromContext) -> list[SyncChange]:
    column = context.columns.get("is_read")
    status_id = context.user_book.status_id
    included_statuses = context.prefs.get("sync_statuses", [])
    if not column or not status_id or (included_statuses and status_id not in included_statuses):
        return []
    new_value = status_id == 3
    current = context.get_value(context.calibre_id, column)
    current_value = bool(current) if current is not None else False
    if current_value == new_value:
        return []
    return [
        context.change(
            "is_read",
            "Yes" if current_value else "No",
            "Yes" if new_value else "No",
            raw_value="Yes" if new_value else "",
        )
    ]


def _compare_sync_from_review(context: _SyncFromContext) -> list[SyncChange]:
    column = context.columns.get("review")
    review = context.user_book.review
    if not context.prefs.get("sync_review", True) or not column or not review:
        return []
    current = context.get_value(context.calibre_id, column)
    if normalize_review_text(current) == normalize_review_text(review):
        return []
    return [
        context.change(
            "review",
            truncate_for_display(current),
            truncate_for_display(review),
        )
    ]


def build_sync_from_values(
    user_book: UserBook,
    prefs: dict,
    get_column_metadata: Callable[[str], dict | None] | None = None,
) -> list[tuple[str, Any]]:
    """Build Calibre column writes for a newly imported Hardcover book."""
    columns = get_column_mappings(prefs)
    values: list[tuple[str, Any]] = []
    included_statuses = prefs.get("sync_statuses", [])
    status_enabled = not included_statuses or user_book.status_id in included_statuses

    status_column = columns.get("status")
    if status_column and user_book.status_id and status_enabled:
        status_value = get_status_from_hardcover(
            user_book.status_id, prefs.get("status_mappings", {})
        )
        if status_value:
            values.append((status_column, status_value))

    rating_column = columns.get("rating")
    if prefs.get("sync_rating", True) and rating_column and user_book.rating is not None:
        metadata = get_column_metadata(rating_column) if get_column_metadata else None
        rating_value, _ = convert_rating_to_calibre(user_book.rating, rating_column, metadata)
        values.append((rating_column, rating_value))

    if prefs.get("sync_progress", True):
        pages_column = columns.get("progress")
        if pages_column and user_book.current_progress_pages is not None:
            values.append((pages_column, user_book.current_progress_pages))
        percent_column = columns.get("progress_percent")
        if percent_column and user_book.current_progress_percent is not None:
            values.append((percent_column, round(user_book.current_progress_percent, 1)))

    if prefs.get("sync_dates", True):
        for field_name, date_value in (
            ("date_started", user_book.latest_started_at),
            ("date_read", user_book.latest_finished_at),
        ):
            column = columns.get(field_name)
            normalized_date = extract_date(date_value)
            if column and normalized_date:
                values.append((column, normalized_date))

    is_read_column = columns.get("is_read")
    if is_read_column and user_book.status_id and status_enabled:
        values.append((is_read_column, user_book.status_id == 3))

    review_column = columns.get("review")
    if prefs.get("sync_review", True) and review_column and user_book.review:
        values.append((review_column, user_book.review))

    return values


_SYNC_FROM_COMPARATORS = (
    _compare_sync_from_status,
    _compare_sync_from_rating,
    _compare_sync_from_progress,
    _compare_sync_from_dates,
    _compare_sync_from_is_read,
    _compare_sync_from_review,
)


def find_sync_from_changes(
    hardcover_books: list[UserBook],
    hc_to_calibre: dict[str, int],
    get_calibre_value: Callable[[int, str], Any],
    get_calibre_title: Callable[[int], str],
    prefs: dict,
    get_column_metadata: Callable[[str], dict | None] | None = None,
) -> list[SyncChange]:
    """Find changes needed to make linked Calibre books match Hardcover."""
    changes = []
    columns = get_column_mappings(prefs)
    for user_book in hardcover_books:
        slug = user_book.book.slug if user_book.book else None
        calibre_id = hc_to_calibre.get(slug) if slug else None
        if not calibre_id:
            continue
        context = _SyncFromContext(
            user_book=user_book,
            calibre_id=calibre_id,
            calibre_title=get_calibre_title(calibre_id),
            columns=columns,
            prefs=prefs,
            get_value=get_calibre_value,
            get_metadata=get_column_metadata,
        )
        for compare in _SYNC_FROM_COMPARATORS:
            changes.extend(compare(context))
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
    api_error_messages: list[str] = field(default_factory=list)
    books_with_changes: int = 0
    warnings: list[str] = field(default_factory=list)


@dataclass
class _SyncToContext:
    calibre_id: int
    calibre_title: str
    hardcover_book: Book
    user_book: UserBook | None
    identifiers: dict[str, str]
    columns: dict[str, str]
    prefs: dict
    get_value: Callable[[int, str], Any]
    get_metadata: Callable[[str], dict | None] | None
    warnings: list[str]

    @property
    def user_book_id(self) -> int | None:
        return self.user_book.id if self.user_book else None

    def change(
        self,
        field: str,
        old_value: str | None,
        new_value: str | None,
        *,
        api_value: Any = None,
        edition_id: int | None = None,
    ) -> SyncToChange:
        return SyncToChange(
            calibre_id=self.calibre_id,
            calibre_title=self.calibre_title,
            hardcover_book_id=self.hardcover_book.id,
            user_book_id=self.user_book_id,
            field=field,
            old_value=old_value,
            new_value=new_value,
            api_value=api_value,
            edition_id=edition_id,
        )


def _compare_sync_to_status(context: _SyncToContext) -> list[SyncToChange]:
    column = context.columns.get("status")
    if not column:
        return []
    calibre_status = context.get_value(context.calibre_id, column)
    if not calibre_status:
        return []
    mappings = context.prefs.get("status_mappings", {})
    new_status_id = get_status_from_calibre(calibre_status, mappings)
    included_statuses = context.prefs.get("sync_statuses", [])
    if not new_status_id:
        if calibre_status in get_status_mapping_conflicts(mappings):
            context.warnings.append(
                f"{context.calibre_title}: skipped ambiguous status value {calibre_status!r}"
            )
        return []
    if included_statuses and new_status_id not in included_statuses:
        return []
    current_status_id = context.user_book.status_id if context.user_book else None
    if current_status_id == new_status_id:
        return []
    current_status = (
        get_status_from_hardcover(current_status_id, mappings) if current_status_id else None
    )
    return [
        context.change(
            "status",
            current_status or "(not in library)",
            calibre_status,
            api_value=new_status_id,
        )
    ]


def _compare_sync_to_rating(context: _SyncToContext) -> list[SyncToChange]:
    column = context.columns.get("rating")
    if not context.prefs.get("sync_rating", True) or not column:
        return []
    calibre_rating = context.get_value(context.calibre_id, column)
    if calibre_rating is None:
        return []
    metadata = context.get_metadata(column) if context.get_metadata else None
    new_rating = convert_rating_from_calibre(calibre_rating, column, metadata)
    if new_rating is None:
        context.warnings.append(
            f"{context.calibre_title}: skipped rating because it is not numeric"
        )
        return []
    current_rating = context.user_book.rating if context.user_book else None
    if new_rating == current_rating:
        return []
    return [
        context.change(
            "rating",
            format_rating_as_stars(current_rating),
            format_rating_as_stars(new_rating),
            api_value=new_rating,
        )
    ]


def _compare_sync_to_progress(context: _SyncToContext) -> list[SyncToChange]:
    if not context.prefs.get("sync_progress", True):
        return []
    pages_column = context.columns.get("progress")
    calibre_pages = context.get_value(context.calibre_id, pages_column) if pages_column else None
    if calibre_pages is not None:
        current_pages = context.user_book.current_progress_pages if context.user_book else None
        if calibre_pages == current_pages:
            return []
        return [
            context.change(
                "progress",
                str(current_pages) if current_pages is not None else "(empty)",
                str(calibre_pages),
                api_value=calibre_pages,
                edition_id=_progress_edition_id(context.identifiers, context.user_book),
            )
        ]

    percent_column = context.columns.get("progress_percent")
    if not percent_column:
        return []
    calibre_percent = context.get_value(context.calibre_id, percent_column)
    if calibre_percent is None or calibre_percent == "":
        return []
    metadata = context.get_metadata(percent_column) if context.get_metadata else None
    datatype = metadata.get("datatype") if metadata else None
    try:
        normalized_percent = normalize_progress_percent(calibre_percent, datatype)
    except (TypeError, ValueError):
        normalized_percent = None
    if normalized_percent is None:
        context.warnings.append(
            f"{context.calibre_title}: skipped percentage progress because it is not numeric"
        )
        return []
    if not 0 <= float(normalized_percent) <= 100:
        context.warnings.append(
            f"{context.calibre_title}: skipped percentage progress outside the 0-100 range"
        )
        return []

    edition_id, page_count, warning = _progress_basis(
        context.identifiers, context.hardcover_book, context.user_book
    )
    if page_count is None:
        context.warnings.append(
            f"{context.calibre_title}: skipped percentage progress because {warning}"
        )
        return []
    current_percent = context.user_book.current_progress_percent if context.user_book else None
    current_pages = context.user_book.current_progress_pages if context.user_book else None
    if current_pages is not None:
        current_percent = current_pages / page_count * 100
    normalized_current = normalize_progress_percent(current_percent, datatype)
    target_pages = round(page_count * float(normalized_percent) / 100)
    if normalized_percent == normalized_current or target_pages == current_pages:
        return []
    return [
        context.change(
            "progress_percent",
            f"{normalized_current}%" if normalized_current is not None else "(empty)",
            f"{normalized_percent}%",
            api_value=target_pages,
            edition_id=edition_id,
        )
    ]


def _compare_sync_to_dates(context: _SyncToContext) -> list[SyncToChange]:
    if not context.prefs.get("sync_dates", True):
        return []
    changes = []
    date_fields = (
        (
            "date_started",
            context.user_book.latest_started_at if context.user_book else None,
        ),
        (
            "date_read",
            context.user_book.latest_finished_at if context.user_book else None,
        ),
    )
    for field_name, hardcover_date in date_fields:
        column = context.columns.get(field_name)
        calibre_date = context.get_value(context.calibre_id, column) if column else None
        if not calibre_date:
            continue
        new_date = str(calibre_date)[:10]
        current_date = hardcover_date[:10] if hardcover_date else None
        if new_date != current_date:
            changes.append(
                context.change(
                    field_name,
                    current_date or "(empty)",
                    new_date,
                    api_value=new_date,
                )
            )
    return changes


def _compare_sync_to_review(context: _SyncToContext) -> list[SyncToChange]:
    column = context.columns.get("review")
    if not context.prefs.get("sync_review", True) or not column:
        return []
    review = normalize_review_text(context.get_value(context.calibre_id, column))
    if not review:
        return []
    current_review = context.user_book.review if context.user_book else None
    if review == normalize_review_text(current_review):
        return []
    return [
        context.change(
            "review",
            truncate_for_display(current_review),
            truncate_for_display(review),
            api_value=review,
        )
    ]


_SYNC_TO_COMPARATORS = (
    _compare_sync_to_status,
    _compare_sync_to_rating,
    _compare_sync_to_progress,
    _compare_sync_to_dates,
    _compare_sync_to_review,
)


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
    """Find changes needed to make Hardcover match linked Calibre books."""
    result = SyncToResult()
    columns = get_column_mappings(prefs)

    for index, book_id in enumerate(book_ids, start=1):
        if on_progress:
            on_progress(index)
        identifiers = get_identifiers(book_id)
        hardcover_identifier = identifiers.get("hardcover")
        if not hardcover_identifier:
            result.not_linked_count += 1
            continue

        title = get_calibre_title(book_id)
        try:
            hardcover_book = resolve_book(hardcover_identifier)
        except Exception as error:
            result.api_errors += 1
            result.api_error_messages.append(f"{title}: {error}")
            continue
        if not hardcover_book:
            result.not_linked_count += 1
            continue

        try:
            user_book = get_user_book(hardcover_book.id)
        except Exception as error:
            result.api_errors += 1
            result.api_error_messages.append(f"{title}: {error}")
            continue

        result.linked_count += 1
        if user_book:
            result.hardcover_data[hardcover_book.id] = user_book
        context = _SyncToContext(
            calibre_id=book_id,
            calibre_title=title,
            hardcover_book=hardcover_book,
            user_book=user_book,
            identifiers=identifiers,
            columns=columns,
            prefs=prefs,
            get_value=get_calibre_value,
            get_metadata=get_column_metadata,
            warnings=result.warnings,
        )
        book_changes = []
        for compare in _SYNC_TO_COMPARATORS:
            book_changes.extend(compare(context))
        if (
            user_book is None
            and book_changes
            and not any(change.field == "status" for change in book_changes)
        ):
            result.warnings.append(
                f"{title}: skipped changes because adding a book requires a mapped status"
            )
            continue
        if book_changes:
            result.changes.extend(book_changes)
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
        return int(float(value))
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
