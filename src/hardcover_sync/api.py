"""
Hardcover API client using GraphQL.

This module provides the HardcoverAPI class for interacting with
the Hardcover.app GraphQL API.
"""

from datetime import date
from typing import Any

from gql import Client, gql  # noqa: E402
from gql.graphql_request import GraphQLRequest  # noqa: E402
from gql.transport.exceptions import TransportQueryError  # noqa: E402
from gql.transport.requests import RequestsHTTPTransport  # noqa: E402

from . import queries  # noqa: E402
from .models import (  # noqa: E402
    Author,
    Book,
    Edition,
    List,
    ListBookMembership,
    User,
    UserBook,
    UserBookRead,
    clean_isbn,
)

# API Configuration
API_URL = "https://api.hardcover.app/v1/graphql"
DEFAULT_TIMEOUT = 30  # seconds


class HardcoverAPIError(Exception):
    """Base exception for Hardcover API errors."""

    pass


class AuthenticationError(HardcoverAPIError):
    """Raised when authentication fails."""

    pass


class RateLimitError(HardcoverAPIError):
    """Raised when rate limit is exceeded."""

    pass


class HardcoverAPI:
    """
    Client for the Hardcover GraphQL API.

    Usage:
        api = HardcoverAPI(token="your-api-token")
        user = api.get_me()
        print(f"Logged in as @{user.username}")

    Dry-run mode:
        api = HardcoverAPI(token="your-api-token", dry_run=True)
        # Mutations will be logged but not executed
    """

    def __init__(self, token: str, timeout: int = DEFAULT_TIMEOUT, dry_run: bool = False):
        """
        Initialize the API client.

        Args:
            token: The Hardcover API token.
            timeout: Request timeout in seconds (default 30).
            dry_run: If True, mutations are logged but not executed.
        """
        self.token = token
        self.timeout = timeout
        self.dry_run = dry_run
        self._client: Client | None = None
        self._user: User | None = None
        self._dry_run_log: list[dict] = []  # Log of operations that would have been performed

    @property
    def client(self) -> Client:
        """Get or create the GraphQL client."""
        if self._client is None:
            transport = RequestsHTTPTransport(
                url=API_URL,
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=self.timeout,
            )
            self._client = Client(transport=transport, fetch_schema_from_transport=False)
        return self._client

    def _execute(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        """
        Execute a GraphQL query.

        Args:
            query: The GraphQL query string.
            variables: Optional query variables.

        Returns:
            The query result data.

        Raises:
            AuthenticationError: If the token is invalid.
            RateLimitError: If rate limit is exceeded.
            HardcoverAPIError: For other API errors.
        """
        try:
            request = GraphQLRequest(gql(query), variable_values=variables)
            result = self.client.execute(request)
            return result
        except TransportQueryError as e:
            error_msg = str(e)
            if "unauthorized" in error_msg.lower() or "invalid" in error_msg.lower():
                raise AuthenticationError("Invalid API token") from e
            if "rate limit" in error_msg.lower():
                raise RateLimitError("Rate limit exceeded (60 requests/minute)") from e
            raise HardcoverAPIError(f"API error: {error_msg}") from e
        except Exception as e:
            raise HardcoverAPIError(f"Request failed: {e}") from e

    def _execute_mutation(
        self,
        mutation: str,
        variables: dict[str, Any],
        operation_name: str,
        dry_run_result: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Execute a GraphQL mutation with dry-run support.

        In dry-run mode, the mutation is logged but not executed.

        Args:
            mutation: The GraphQL mutation string.
            variables: Mutation variables.
            operation_name: Human-readable name for logging.
            dry_run_result: Mock result to return in dry-run mode.

        Returns:
            The mutation result (real or mocked).
        """
        if self.dry_run:
            self._dry_run_log.append(
                {
                    "operation": operation_name,
                    "variables": variables,
                    "would_execute": mutation[:100] + "..." if len(mutation) > 100 else mutation,
                }
            )
            return dry_run_result

        return self._execute(mutation, variables)

    def get_dry_run_log(self) -> list[dict]:
        """
        Get the log of operations that would have been performed in dry-run mode.

        Returns:
            List of operation dictionaries with keys: operation, variables, would_execute
        """
        return self._dry_run_log.copy()

    def clear_dry_run_log(self):
        """Clear the dry-run log."""
        self._dry_run_log = []

    def _ensure_user_id(self, user_id: int | None = None) -> int:
        """Resolve the user ID, defaulting to the current authenticated user.

        Args:
            user_id: Explicit user ID, or None to use the current user.

        Returns:
            The resolved user ID.
        """
        if user_id is not None:
            return user_id
        if self._user is None:
            self.get_me()
        return self._user.id

    # =========================================================================
    # User Methods
    # =========================================================================

    def get_me(self) -> User:
        """
        Get the current authenticated user.

        Returns:
            User object with the current user's information.

        Raises:
            AuthenticationError: If the token is invalid.
        """
        result = self._execute(queries.ME_QUERY)
        me = result.get("me")
        if not me:
            raise AuthenticationError("Could not fetch user information")

        # Handle case where 'me' is returned as a list (API schema variation)
        if isinstance(me, list):
            if not me:
                raise AuthenticationError("Could not fetch user information")
            me = me[0]

        self._user = User.from_dict(me)
        return self._user

    def validate_token(self) -> tuple[bool, User | None]:
        """
        Validate the API token.

        Returns:
            Tuple of (is_valid, user) where user is None if invalid.
        """
        try:
            user = self.get_me()
            return True, user
        except (AuthenticationError, HardcoverAPIError):
            return False, None

    # =========================================================================
    # Book Lookup Methods
    # =========================================================================

    def find_book_by_isbn(self, isbn: str) -> Book | None:
        """
        Find a book by ISBN-13 or ISBN-10.

        Args:
            isbn: The ISBN to search for (13 or 10 digits).

        Returns:
            Book object if found, None otherwise.
        """
        isbn = clean_isbn(isbn)

        # Try ISBN-13 first
        if len(isbn) == 13:
            result = self._execute(queries.BOOK_BY_ISBN_QUERY, {"isbn": isbn})
            editions = result.get("editions", [])
        elif len(isbn) == 10:
            result = self._execute(queries.BOOK_BY_ISBN_10_QUERY, {"isbn": isbn})
            editions = result.get("editions", [])
        else:
            return None

        if not editions:
            return None

        edition_data = editions[0]
        book_data = edition_data.get("book", {})

        # Create edition from the response
        edition = Edition.from_dict(edition_data)

        # Create book with the edition we found
        return Book.from_dict(book_data, editions=[edition])

    def search_books(self, query: str) -> list[Book]:
        """
        Search for books by title or author.

        Args:
            query: The search query string.

        Returns:
            List of matching Book objects.
        """
        import json

        result = self._execute(queries.BOOK_SEARCH_QUERY, {"query": query})
        search_data = result.get("search", {}).get("results", {})

        # Handle Typesense response structure: results is a dict with 'hits' array
        # Each hit has a 'document' containing the actual book data
        if isinstance(search_data, dict):
            hits = search_data.get("hits", [])
            search_results = [hit.get("document", {}) for hit in hits]
        elif isinstance(search_data, list):
            # Fallback for legacy format where results was a list
            search_results = search_data
        else:
            search_results = []

        books = []
        for item in search_results:
            if not item:  # Skip null results
                continue

            # Handle case where results come back as JSON strings (JSONB serialization)
            if isinstance(item, str):
                try:
                    item = json.loads(item)
                except json.JSONDecodeError:
                    continue

            # Typesense returns author_names as an array of strings
            authors = []
            author_names = item.get("author_names", [])
            if author_names:
                for idx, name in enumerate(author_names):
                    # Use negative IDs since we don't have real author IDs from search
                    authors.append(Author(id=-(idx + 1), name=name))

            # Typesense returns isbns as an array of strings
            editions = []
            isbns = item.get("isbns", [])
            if isbns:
                for idx, isbn in enumerate(isbns):
                    # Determine if it's ISBN-10 or ISBN-13 based on length
                    clean_isbn = isbn.replace("-", "")
                    if len(clean_isbn) == 13:
                        editions.append(Edition(id=-(idx + 1), isbn_13=clean_isbn))
                    elif len(clean_isbn) == 10:
                        editions.append(Edition(id=-(idx + 1), isbn_10=clean_isbn))

            # release_year is returned as an integer (e.g., 2020)
            release_year = item.get("release_year")
            release_date = str(release_year) if release_year else None

            books.append(
                Book(
                    id=int(item["id"]),
                    title=item["title"],
                    slug=item.get("slug"),
                    release_date=release_date,
                    authors=authors,
                    editions=editions,
                )
            )

        return books

    def get_book_by_id(self, book_id: int) -> Book | None:
        """
        Get a book by its Hardcover ID.

        Args:
            book_id: The Hardcover book ID.

        Returns:
            Book object if found, None otherwise.
        """
        result = self._execute(queries.BOOK_BY_ID_QUERY, {"id": book_id})
        books = result.get("books", [])

        if not books:
            return None

        return Book.from_dict(books[0])

    def get_book_by_slug(self, slug: str) -> Book | None:
        """
        Get a book by its Hardcover slug.

        Args:
            slug: The Hardcover book slug (e.g. "the-hobbit").

        Returns:
            Book object if found, None otherwise.
        """
        result = self._execute(queries.BOOK_BY_SLUG_QUERY, {"slug": slug})
        books = result.get("books", [])

        if not books:
            return None

        return Book.from_dict(books[0])

    # =========================================================================
    # User Library Methods
    # =========================================================================

    def get_user_books(
        self, user_id: int | None = None, limit: int = 100, offset: int = 0
    ) -> list[UserBook]:
        """
        Get books from a user's library.

        Args:
            user_id: The user ID (defaults to current user).
            limit: Maximum number of books to return.
            offset: Pagination offset.

        Returns:
            List of UserBook objects.
        """
        user_id = self._ensure_user_id(user_id)

        result = self._execute(
            queries.USER_BOOKS_QUERY,
            {"user_id": user_id, "limit": limit, "offset": offset},
        )

        return [UserBook.from_dict(ub) for ub in result.get("user_books", [])]

    def get_user_book(self, book_id: int, user_id: int | None = None) -> UserBook | None:
        """
        Get a specific book from the user's library.

        Args:
            book_id: The Hardcover book ID.
            user_id: The user ID (defaults to current user).

        Returns:
            UserBook if found, None otherwise.
        """
        user_id = self._ensure_user_id(user_id)

        result = self._execute(
            queries.USER_BOOK_BY_BOOK_ID_QUERY,
            {"user_id": user_id, "book_id": book_id},
        )

        user_books = result.get("user_books", [])
        if not user_books:
            return None

        return UserBook.from_dict(user_books[0])

    def get_user_books_by_slugs(
        self, slugs: list[str], user_id: int | None = None
    ) -> list[UserBook]:
        """
        Get user books for a list of Hardcover book slugs.

        Fetches in batches to avoid query size limits.

        Args:
            slugs: List of Hardcover book slugs.
            user_id: The user ID (defaults to current user).

        Returns:
            List of UserBook objects for the matching books.
        """
        user_id = self._ensure_user_id(user_id)

        all_user_books = []
        batch_size = 100

        for i in range(0, len(slugs), batch_size):
            batch = slugs[i : i + batch_size]
            result = self._execute(
                queries.USER_BOOKS_BY_SLUGS_QUERY,
                {"user_id": user_id, "slugs": batch},
            )
            all_user_books.extend(UserBook.from_dict(ub) for ub in result.get("user_books", []))

        return all_user_books

    def add_book_to_library(
        self,
        book_id: int,
        status_id: int,
        edition_id: int | None = None,
        rating: float | None = None,
        started_at: date | str | None = None,
        finished_at: date | str | None = None,
        review: str | None = None,
    ) -> UserBook:
        """
        Add a book to the user's library.

        Args:
            book_id: The Hardcover book ID.
            status_id: The reading status (1-6).
            edition_id: Optional edition ID.
            rating: Optional rating (0-5).
            started_at: Optional start date (sets first_started_reading_date).
            finished_at: Optional finish date (sets last_read_date).
            review: Optional review text.

        Returns:
            The created UserBook.

        Note:
            For tracking reading progress (pages), use insert_user_book_read() after
            creating the user_book.
        """
        # Build the UserBookCreateInput object
        user_book_input: dict[str, Any] = {
            "book_id": book_id,
            "status_id": status_id,
        }

        if edition_id is not None:
            user_book_input["edition_id"] = edition_id
        if rating is not None:
            user_book_input["rating"] = rating
        if started_at is not None:
            user_book_input["first_started_reading_date"] = (
                str(started_at) if isinstance(started_at, date) else started_at
            )
        if finished_at is not None:
            user_book_input["last_read_date"] = (
                str(finished_at) if isinstance(finished_at, date) else finished_at
            )
        # Note: review is stored as review_slate (jsonb) - simple text not directly supported

        result = self._execute_mutation(
            queries.INSERT_USER_BOOK_MUTATION,
            {"object": user_book_input},
            operation_name="add_book_to_library",
            dry_run_result={
                "insert_user_book": {
                    "id": -1,
                    "user_book": {
                        "id": -1,
                        "book_id": book_id,
                        "status_id": status_id,
                        "rating": rating,
                        "updated_at": None,
                    },
                }
            },
        )
        ub = result.get("insert_user_book", {}).get("user_book", {})

        return UserBook(
            id=ub["id"],
            book_id=ub["book_id"],
            status_id=ub.get("status_id"),
            rating=ub.get("rating"),
            updated_at=ub.get("updated_at"),
        )

    def update_user_book(
        self,
        user_book_id: int,
        status_id: int | None = None,
        rating: float | None = None,
        started_at: date | str | None = None,
        finished_at: date | str | None = None,
        review: str | None = None,
    ) -> UserBook:
        """
        Update a book in the user's library.

        Args:
            user_book_id: The user_book ID to update.
            status_id: Optional new status (1-6).
            rating: Optional new rating (0-5).
            started_at: Optional new start date (sets first_started_reading_date).
            finished_at: Optional new finish date (sets last_read_date).
            review: Optional new review text (not currently supported by API).

        Returns:
            The updated UserBook.

        Note:
            For tracking reading progress (pages), use insert_user_book_read() or
            update_user_book_read() instead.
        """
        # Build the UserBookUpdateInput object
        user_book_input: dict[str, Any] = {}

        if status_id is not None:
            user_book_input["status_id"] = status_id
        if rating is not None:
            user_book_input["rating"] = rating
        if started_at is not None:
            user_book_input["first_started_reading_date"] = (
                str(started_at) if isinstance(started_at, date) else started_at
            )
        if finished_at is not None:
            user_book_input["last_read_date"] = (
                str(finished_at) if isinstance(finished_at, date) else finished_at
            )
        # Note: review is stored as review_slate (jsonb) - simple text not directly supported

        result = self._execute_mutation(
            queries.UPDATE_USER_BOOK_MUTATION,
            {"id": user_book_id, "object": user_book_input},
            operation_name="update_user_book",
            dry_run_result={
                "update_user_book": {
                    "id": user_book_id,
                    "user_book": {
                        "id": user_book_id,
                        "book_id": -1,
                        "status_id": status_id,
                        "rating": rating,
                        "updated_at": None,
                    },
                }
            },
        )
        ub = result.get("update_user_book", {}).get("user_book", {})

        if not ub:
            raise HardcoverAPIError("Update failed - no data returned")

        return UserBook(
            id=ub["id"],
            book_id=ub["book_id"],
            status_id=ub.get("status_id"),
            rating=ub.get("rating"),
            updated_at=ub.get("updated_at"),
        )

    def remove_book_from_library(self, user_book_id: int) -> bool:
        """
        Remove a book from the user's library.

        Args:
            user_book_id: The user_book ID to remove.

        Returns:
            True if successful.
        """
        result = self._execute_mutation(
            queries.DELETE_USER_BOOK_MUTATION,
            {"id": user_book_id},
            operation_name="remove_book_from_library",
            dry_run_result={"delete_user_book": {"id": user_book_id}},
        )
        # The new API returns {id, book_id, user_id} on success
        deleted_id = result.get("delete_user_book", {}).get("id")
        return deleted_id is not None

    def _build_read_input(
        self,
        started_at: date | str | None = None,
        finished_at: date | str | None = None,
        progress: float | None = None,
        progress_pages: int | None = None,
        edition_id: int | None = None,
    ) -> dict[str, Any]:
        """Build a read input dict for insert/update user book read mutations."""
        read_input: dict[str, Any] = {}

        if started_at is not None:
            read_input["started_at"] = (
                str(started_at) if isinstance(started_at, date) else started_at
            )
        if finished_at is not None:
            read_input["finished_at"] = (
                str(finished_at) if isinstance(finished_at, date) else finished_at
            )
        if progress is not None:
            read_input["progress"] = progress
        if progress_pages is not None:
            read_input["progress_pages"] = progress_pages
        if edition_id is not None:
            read_input["edition_id"] = edition_id

        return read_input

    # =========================================================================
    # User Book Read Methods (Progress Tracking)
    # =========================================================================

    def insert_user_book_read(
        self,
        user_book_id: int,
        started_at: date | str | None = None,
        finished_at: date | str | None = None,
        progress: float | None = None,
        progress_pages: int | None = None,
        edition_id: int | None = None,
    ) -> UserBookRead:
        """
        Create a new reading session for a book.

        Args:
            user_book_id: The user_book ID to add a read to.
            started_at: When reading started.
            finished_at: When reading finished.
            progress: Progress as decimal (0.0-1.0).
            progress_pages: Progress in pages.
            edition_id: Optional specific edition being read.

        Returns:
            The created UserBookRead.
        """
        read_input = self._build_read_input(
            started_at=started_at,
            finished_at=finished_at,
            progress=progress,
            progress_pages=progress_pages,
            edition_id=edition_id,
        )

        result = self._execute_mutation(
            queries.INSERT_USER_BOOK_READ_MUTATION,
            {"user_book_id": user_book_id, "user_book_read": read_input},
            operation_name="insert_user_book_read",
            dry_run_result={
                "insert_user_book_read": {
                    "id": -1,
                    "user_book_read": {
                        "id": -1,
                        "started_at": read_input.get("started_at"),
                        "finished_at": read_input.get("finished_at"),
                        "paused_at": None,
                        "progress": progress,
                        "progress_pages": progress_pages,
                        "edition_id": edition_id,
                    },
                }
            },
        )
        read_data = result.get("insert_user_book_read", {}).get("user_book_read", {})
        return UserBookRead.from_dict(read_data)

    def update_user_book_read(
        self,
        read_id: int,
        started_at: date | str | None = None,
        finished_at: date | str | None = None,
        progress: float | None = None,
        progress_pages: int | None = None,
        edition_id: int | None = None,
    ) -> UserBookRead:
        """
        Update an existing reading session.

        Args:
            read_id: The user_book_read ID to update.
            started_at: When reading started.
            finished_at: When reading finished.
            progress: Progress as decimal (0.0-1.0).
            progress_pages: Progress in pages.
            edition_id: Optional specific edition being read.

        Returns:
            The updated UserBookRead.
        """
        read_input = self._build_read_input(
            started_at=started_at,
            finished_at=finished_at,
            progress=progress,
            progress_pages=progress_pages,
            edition_id=edition_id,
        )

        result = self._execute_mutation(
            queries.UPDATE_USER_BOOK_READ_MUTATION,
            {"id": read_id, "object": read_input},
            operation_name="update_user_book_read",
            dry_run_result={
                "update_user_book_read": {
                    "id": read_id,
                    "user_book_read": {
                        "id": read_id,
                        "started_at": read_input.get("started_at"),
                        "finished_at": read_input.get("finished_at"),
                        "paused_at": None,
                        "progress": progress,
                        "progress_pages": progress_pages,
                        "edition_id": edition_id,
                    },
                }
            },
        )
        read_data = result.get("update_user_book_read", {}).get("user_book_read", {})

        if not read_data:
            raise HardcoverAPIError("Update failed - no data returned")

        return UserBookRead.from_dict(read_data)

    def delete_user_book_read(self, read_id: int) -> bool:
        """
        Delete a reading session.

        Args:
            read_id: The user_book_read ID to delete.

        Returns:
            True if successful.
        """
        result = self._execute_mutation(
            queries.DELETE_USER_BOOK_READ_MUTATION,
            {"id": read_id},
            operation_name="delete_user_book_read",
            dry_run_result={"delete_user_book_read": {"id": read_id}},
        )
        deleted_id = result.get("delete_user_book_read", {}).get("id")
        return deleted_id is not None

    # =========================================================================
    # List Methods
    # =========================================================================

    def get_user_lists(self, user_id: int | None = None) -> list[List]:
        """
        Get the user's lists.

        Args:
            user_id: The user ID (defaults to current user).

        Returns:
            List of List objects.
        """
        user_id = self._ensure_user_id(user_id)

        result = self._execute(queries.USER_LISTS_QUERY, {"user_id": user_id})

        return [List.from_dict(lst) for lst in result.get("lists", [])]

    def get_book_lists(self, book_id: int, user_id: int | None = None) -> list[List]:
        """
        Get which of the user's lists contain a specific book.

        Args:
            book_id: The Hardcover book ID.
            user_id: The user ID (defaults to current user).

        Returns:
            List of List objects that contain this book.
        """
        user_id = self._ensure_user_id(user_id)

        result = self._execute(
            queries.BOOK_LISTS_QUERY,
            {"book_id": book_id, "user_id": user_id},
        )

        lists = []
        for lb in result.get("list_books", []):
            lst = lb.get("list", {})
            if lst:
                lists.append(List.from_dict(lst))

        return lists

    def get_book_list_memberships(
        self, book_id: int, user_id: int | None = None
    ) -> list[ListBookMembership]:
        """
        Get list membership details for a book, including list_book IDs for removal.

        Args:
            book_id: The Hardcover book ID.
            user_id: The user ID (defaults to current user).

        Returns:
            List of ListBookMembership objects.
        """
        user_id = self._ensure_user_id(user_id)

        result = self._execute(
            queries.BOOK_LISTS_QUERY,
            {"book_id": book_id, "user_id": user_id},
        )

        memberships = []
        for lb in result.get("list_books", []):
            if lb.get("list"):
                memberships.append(ListBookMembership.from_dict(lb))

        return memberships

    def add_book_to_list(self, list_id: int, book_id: int) -> int:
        """
        Add a book to a list.

        Args:
            list_id: The list ID.
            book_id: The Hardcover book ID.

        Returns:
            The list_book ID.
        """
        result = self._execute_mutation(
            queries.ADD_BOOK_TO_LIST_MUTATION,
            {"list_id": list_id, "book_id": book_id},
            operation_name="add_book_to_list",
            dry_run_result={"insert_list_book": {"id": -1}},
        )
        return result.get("insert_list_book", {}).get("id")

    def remove_book_from_list(self, list_book_id: int) -> bool:
        """
        Remove a book from a list.

        Args:
            list_book_id: The list_book ID (not the book ID).

        Returns:
            True if successful.
        """
        result = self._execute_mutation(
            queries.REMOVE_BOOK_FROM_LIST_MUTATION,
            {"list_book_id": list_book_id},
            operation_name="remove_book_from_list",
            dry_run_result={"delete_list_book": {"affected_rows": 1}},
        )
        affected = result.get("delete_list_book", {}).get("affected_rows", 0)
        return affected > 0
