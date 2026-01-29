"""
Hardcover API client using GraphQL.

This module provides the HardcoverAPI class for interacting with
the Hardcover.app GraphQL API.
"""

import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

# Add plugin directory to path for bundled dependencies
# This is needed because Calibre's plugin system uses a custom namespace
_plugin_dir = Path(__file__).parent
if str(_plugin_dir) not in sys.path:
    sys.path.insert(0, str(_plugin_dir))

from gql import Client, gql  # noqa: E402
from gql.graphql_request import GraphQLRequest  # noqa: E402
from gql.transport.exceptions import TransportQueryError  # noqa: E402
from gql.transport.requests import RequestsHTTPTransport  # noqa: E402

from . import queries  # noqa: E402

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


@dataclass
class User:
    """Represents a Hardcover user."""

    id: int
    username: str
    name: str | None = None
    books_count: int = 0
    image: str | None = None


@dataclass
class Author:
    """Represents a book author."""

    id: int
    name: str


@dataclass
class Edition:
    """Represents a book edition."""

    id: int
    isbn_13: str | None = None
    isbn_10: str | None = None
    title: str | None = None
    pages: int | None = None


@dataclass
class Book:
    """Represents a Hardcover book."""

    id: int
    title: str
    slug: str | None = None
    release_date: str | None = None
    authors: list[Author] | None = None
    editions: list[Edition] | None = None


@dataclass
class UserBook:
    """Represents a book in a user's library."""

    id: int
    book_id: int
    edition_id: int | None = None
    status_id: int | None = None
    rating: float | None = None
    progress: float | None = None
    progress_pages: int | None = None
    started_at: str | None = None
    finished_at: str | None = None
    review: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    book: Book | None = None
    edition: Edition | None = None


@dataclass
class List:
    """Represents a Hardcover list."""

    id: int
    name: str
    slug: str | None = None
    description: str | None = None
    books_count: int = 0


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

        self._user = User(
            id=me["id"],
            username=me["username"],
            name=me.get("name"),
            books_count=me.get("books_count", 0),
        )
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
        # Clean ISBN
        isbn = isbn.replace("-", "").replace(" ", "")

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

        edition = editions[0]
        book_data = edition.get("book", {})

        authors = []
        for contrib in book_data.get("contributions", []):
            author_data = contrib.get("author", {})
            if author_data:
                authors.append(Author(id=author_data["id"], name=author_data["name"]))

        return Book(
            id=book_data["id"],
            title=book_data["title"],
            slug=book_data.get("slug"),
            authors=authors,
            editions=[
                Edition(
                    id=edition["id"],
                    isbn_13=edition.get("isbn_13"),
                    isbn_10=edition.get("isbn_10"),
                    title=edition.get("title"),
                )
            ],
        )

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

        book_data = books[0]

        authors = []
        for contrib in book_data.get("contributions", []):
            author_data = contrib.get("author", {})
            if author_data:
                authors.append(Author(id=author_data["id"], name=author_data["name"]))

        editions = []
        for ed in book_data.get("editions", []):
            editions.append(
                Edition(
                    id=ed["id"],
                    isbn_13=ed.get("isbn_13"),
                    isbn_10=ed.get("isbn_10"),
                    title=ed.get("title"),
                    pages=ed.get("pages"),
                )
            )

        return Book(
            id=book_data["id"],
            title=book_data["title"],
            slug=book_data.get("slug"),
            release_date=book_data.get("release_date"),
            authors=authors,
            editions=editions,
        )

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
        if user_id is None:
            if self._user is None:
                self.get_me()
            user_id = self._user.id

        result = self._execute(
            queries.USER_BOOKS_QUERY,
            {"user_id": user_id, "limit": limit, "offset": offset},
        )

        user_books = []
        for ub in result.get("user_books", []):
            book_data = ub.get("book", {})
            edition_data = ub.get("edition", {})

            book = None
            if book_data:
                authors = []
                for contrib in book_data.get("contributions", []):
                    author_data = contrib.get("author", {})
                    if author_data:
                        authors.append(Author(id=author_data["id"], name=author_data["name"]))

                book = Book(
                    id=book_data["id"],
                    title=book_data["title"],
                    slug=book_data.get("slug"),
                    authors=authors,
                )

            edition = None
            if edition_data:
                edition = Edition(
                    id=edition_data["id"],
                    isbn_13=edition_data.get("isbn_13"),
                    isbn_10=edition_data.get("isbn_10"),
                    title=edition_data.get("title"),
                    pages=edition_data.get("pages"),
                )

            user_books.append(
                UserBook(
                    id=ub["id"],
                    book_id=ub["book_id"],
                    edition_id=ub.get("edition_id"),
                    status_id=ub.get("status_id"),
                    rating=ub.get("rating"),
                    progress=ub.get("progress"),
                    progress_pages=ub.get("progress_pages"),
                    started_at=ub.get("started_at"),
                    finished_at=ub.get("finished_at"),
                    review=ub.get("review"),
                    created_at=ub.get("created_at"),
                    updated_at=ub.get("updated_at"),
                    book=book,
                    edition=edition,
                )
            )

        return user_books

    def get_user_book(self, book_id: int, user_id: int | None = None) -> UserBook | None:
        """
        Get a specific book from the user's library.

        Args:
            book_id: The Hardcover book ID.
            user_id: The user ID (defaults to current user).

        Returns:
            UserBook if found, None otherwise.
        """
        if user_id is None:
            if self._user is None:
                self.get_me()
            user_id = self._user.id

        result = self._execute(
            queries.USER_BOOK_BY_BOOK_ID_QUERY,
            {"user_id": user_id, "book_id": book_id},
        )

        user_books = result.get("user_books", [])
        if not user_books:
            return None

        ub = user_books[0]
        return UserBook(
            id=ub["id"],
            book_id=ub["book_id"],
            edition_id=ub.get("edition_id"),
            status_id=ub.get("status_id"),
            rating=ub.get("rating"),
            progress=ub.get("progress"),
            progress_pages=ub.get("progress_pages"),
            started_at=ub.get("started_at"),
            finished_at=ub.get("finished_at"),
            review=ub.get("review"),
            created_at=ub.get("created_at"),
            updated_at=ub.get("updated_at"),
        )

    def add_book_to_library(
        self,
        book_id: int,
        status_id: int,
        edition_id: int | None = None,
        rating: float | None = None,
        progress_pages: int | None = None,
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
            progress_pages: Optional page progress.
            started_at: Optional start date.
            finished_at: Optional finish date.
            review: Optional review text.

        Returns:
            The created UserBook.
        """
        variables: dict[str, Any] = {
            "book_id": book_id,
            "status_id": status_id,
        }

        if edition_id is not None:
            variables["edition_id"] = edition_id
        if rating is not None:
            variables["rating"] = rating
        if progress_pages is not None:
            variables["progress_pages"] = progress_pages
        if started_at is not None:
            variables["started_at"] = (
                str(started_at) if isinstance(started_at, date) else started_at
            )
        if finished_at is not None:
            variables["finished_at"] = (
                str(finished_at) if isinstance(finished_at, date) else finished_at
            )
        if review is not None:
            variables["review"] = review

        result = self._execute_mutation(
            queries.INSERT_USER_BOOK_MUTATION,
            variables,
            operation_name="add_book_to_library",
            dry_run_result={
                "insert_user_book": {
                    "id": -1,
                    "book_id": book_id,
                    "status_id": status_id,
                    "rating": rating,
                    "updated_at": None,
                }
            },
        )
        ub = result.get("insert_user_book", {})

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
        progress_pages: int | None = None,
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
            progress_pages: Optional new page progress.
            started_at: Optional new start date.
            finished_at: Optional new finish date.
            review: Optional new review text.

        Returns:
            The updated UserBook.
        """
        variables: dict[str, Any] = {"id": user_book_id}

        if status_id is not None:
            variables["status_id"] = status_id
        if rating is not None:
            variables["rating"] = rating
        if progress_pages is not None:
            variables["progress_pages"] = progress_pages
        if started_at is not None:
            variables["started_at"] = (
                str(started_at) if isinstance(started_at, date) else started_at
            )
        if finished_at is not None:
            variables["finished_at"] = (
                str(finished_at) if isinstance(finished_at, date) else finished_at
            )
        if review is not None:
            variables["review"] = review

        result = self._execute_mutation(
            queries.UPDATE_USER_BOOK_MUTATION,
            variables,
            operation_name="update_user_book",
            dry_run_result={
                "update_user_book": {
                    "returning": [
                        {
                            "id": user_book_id,
                            "book_id": -1,
                            "status_id": status_id,
                            "rating": rating,
                            "updated_at": None,
                        }
                    ]
                }
            },
        )
        returning = result.get("update_user_book", {}).get("returning", [])

        if not returning:
            raise HardcoverAPIError("Update failed - no data returned")

        ub = returning[0]
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
            dry_run_result={"delete_user_book": {"affected_rows": 1}},
        )
        affected = result.get("delete_user_book", {}).get("affected_rows", 0)
        return affected > 0

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
        if user_id is None:
            if self._user is None:
                self.get_me()
            user_id = self._user.id

        result = self._execute(queries.USER_LISTS_QUERY, {"user_id": user_id})

        lists = []
        for lst in result.get("lists", []):
            lists.append(
                List(
                    id=lst["id"],
                    name=lst["name"],
                    slug=lst.get("slug"),
                    description=lst.get("description"),
                    books_count=lst.get("books_count", 0),
                )
            )

        return lists

    def get_book_lists(self, book_id: int, user_id: int | None = None) -> list[List]:
        """
        Get which of the user's lists contain a specific book.

        Args:
            book_id: The Hardcover book ID.
            user_id: The user ID (defaults to current user).

        Returns:
            List of List objects that contain this book.
        """
        if user_id is None:
            if self._user is None:
                self.get_me()
            user_id = self._user.id

        result = self._execute(
            queries.BOOK_LISTS_QUERY,
            {"book_id": book_id, "user_id": user_id},
        )

        lists = []
        for lb in result.get("list_books", []):
            lst = lb.get("list", {})
            if lst:
                lists.append(
                    List(
                        id=lst["id"],
                        name=lst["name"],
                        slug=lst.get("slug"),
                    )
                )

        return lists

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
