"""
GraphQL queries and mutations for the Hardcover API.

This module contains all the GraphQL operations used by the plugin:
- User authentication/validation
- Book lookup (by ISBN, search)
- User library management
- Reading status updates
- List management
"""

# =============================================================================
# User Queries
# =============================================================================

ME_QUERY = """
query Me {
    me {
        id
        username
        name
        books_count
    }
}
"""

# =============================================================================
# Book Lookup Queries
# =============================================================================


def _book_by_isbn_query(field: str) -> str:
    """Generate a book-by-ISBN query for the given edition field (isbn_13 or isbn_10)."""
    label = "BookByISBN" if field == "isbn_13" else "BookByISBN10"
    return f"""
query {label}($isbn: String!) {{
    editions(where: {{{field}: {{_eq: $isbn}}}}, limit: 1) {{
        id
        isbn_10
        isbn_13
        title
        book {{
            id
            title
            slug
            contributions {{
                author {{
                    id
                    name
                }}
            }}
        }}
    }}
}}
"""


BOOK_BY_ISBN_QUERY = _book_by_isbn_query("isbn_13")

BOOK_BY_ISBN_10_QUERY = _book_by_isbn_query("isbn_10")

BOOK_SEARCH_QUERY = """
query SearchBooks($query: String!) {
    search(query: $query, query_type: "Book", per_page: 20) {
        results
    }
}
"""


def _book_query(where_clause: str, label: str, param: str) -> str:
    """Generate a book lookup query with the given filter."""
    return f"""
query {label}({param}) {{
    books(where: {{{where_clause}}}) {{
        id
        title
        slug
        release_date
        contributions {{
            author {{
                id
                name
            }}
        }}
        editions {{
            id
            isbn_13
            isbn_10
            title
            pages
        }}
    }}
}}
"""


BOOK_BY_ID_QUERY = _book_query("id: {_eq: $id}", "BookById", "$id: Int!")

BOOK_BY_SLUG_QUERY = _book_query("slug: {_eq: $slug}", "BookBySlug", "$slug: String!")

# =============================================================================
# User Library Queries
# =============================================================================

# Shared field selections for user_book queries
_USER_BOOK_FIELDS = """
        id
        book_id
        edition_id
        status_id
        rating
        review_raw
        created_at
        updated_at"""

_USER_BOOK_READS_FIELDS = """
        user_book_reads(order_by: {started_at: desc}) {
            id
            started_at
            finished_at
            paused_at
            progress
            progress_pages
            edition_id
        }"""

_BOOK_SUBQUERY = """
        book {
            id
            title
            slug
            release_date
            contributions {
                author {
                    id
                    name
                }
            }
        }
        edition {
            id
            isbn_13
            isbn_10
            title
            pages
        }"""

USER_BOOKS_QUERY = f"""
query UserBooks($user_id: Int!, $limit: Int!, $offset: Int!) {{
    user_books(
        where: {{user_id: {{_eq: $user_id}}}},
        limit: $limit,
        offset: $offset,
        order_by: {{updated_at: desc}}
    ) {{{_USER_BOOK_FIELDS}{_BOOK_SUBQUERY}{_USER_BOOK_READS_FIELDS}
    }}
}}
"""

USER_BOOK_BY_BOOK_ID_QUERY = f"""
query UserBookByBookId($user_id: Int!, $book_id: Int!) {{
    user_books(
        where: {{
            user_id: {{_eq: $user_id}},
            book_id: {{_eq: $book_id}}
        }},
        limit: 1
    ) {{{_USER_BOOK_FIELDS}{_USER_BOOK_READS_FIELDS}
    }}
}}
"""

USER_BOOKS_BY_SLUGS_QUERY = f"""
query UserBooksBySlugs($user_id: Int!, $slugs: [String!]!) {{
    user_books(
        where: {{
            user_id: {{_eq: $user_id}},
            book: {{slug: {{_in: $slugs}}}}
        }},
        order_by: {{updated_at: desc}}
    ) {{{_USER_BOOK_FIELDS}{_BOOK_SUBQUERY}{_USER_BOOK_READS_FIELDS}
    }}
}}
"""

# =============================================================================
# User Library Mutations
# =============================================================================

INSERT_USER_BOOK_MUTATION = """
mutation InsertUserBook($object: UserBookCreateInput!) {
    insert_user_book(object: $object) {
        id
        user_book {
            id
            book_id
            status_id
            rating
            updated_at
        }
    }
}
"""

UPDATE_USER_BOOK_MUTATION = """
mutation UpdateUserBook($id: Int!, $object: UserBookUpdateInput!) {
    update_user_book(id: $id, object: $object) {
        id
        user_book {
            id
            book_id
            status_id
            rating
            updated_at
        }
    }
}
"""

DELETE_USER_BOOK_MUTATION = """
mutation DeleteUserBook($id: Int!) {
    delete_user_book(id: $id) {
        id
        book_id
        user_id
    }
}
"""

# =============================================================================
# Lists Queries
# =============================================================================

USER_LISTS_QUERY = """
query UserLists($user_id: Int!) {
    lists(where: {user_id: {_eq: $user_id}}) {
        id
        name
        slug
        description
        books_count
        created_at
        updated_at
    }
}
"""

LIST_BOOKS_QUERY = """
query ListBooks($list_id: Int!, $limit: Int!, $offset: Int!) {
    list_books(
        where: {list_id: {_eq: $list_id}},
        limit: $limit,
        offset: $offset
    ) {
        id
        book_id
        position
        book {
            id
            title
            slug
        }
    }
}
"""

BOOK_LISTS_QUERY = """
query BookLists($book_id: Int!, $user_id: Int!) {
    list_books(
        where: {
            book_id: {_eq: $book_id},
            list: {user_id: {_eq: $user_id}}
        }
    ) {
        id
        list_id
        list {
            id
            name
            slug
        }
    }
}
"""

# =============================================================================
# Lists Mutations
# =============================================================================

ADD_BOOK_TO_LIST_MUTATION = """
mutation AddBookToList($list_id: Int!, $book_id: Int!) {
    insert_list_book(object: {list_id: $list_id, book_id: $book_id}) {
        id
        list_id
        book_id
    }
}
"""

REMOVE_BOOK_FROM_LIST_MUTATION = """
mutation RemoveBookFromList($list_book_id: Int!) {
    delete_list_book(where: {id: {_eq: $list_book_id}}) {
        affected_rows
    }
}
"""

# =============================================================================
# User Book Read Mutations (Progress Tracking)
# =============================================================================

INSERT_USER_BOOK_READ_MUTATION = """
mutation InsertUserBookRead($user_book_id: Int!, $user_book_read: DatesReadInput!) {
    insert_user_book_read(user_book_id: $user_book_id, user_book_read: $user_book_read) {
        id
        user_book_read {
            id
            started_at
            finished_at
            paused_at
            progress
            progress_pages
            edition_id
        }
    }
}
"""

UPDATE_USER_BOOK_READ_MUTATION = """
mutation UpdateUserBookRead($id: Int!, $object: DatesReadInput!) {
    update_user_book_read(id: $id, object: $object) {
        id
        user_book_read {
            id
            started_at
            finished_at
            paused_at
            progress
            progress_pages
            edition_id
        }
    }
}
"""

DELETE_USER_BOOK_READ_MUTATION = """
mutation DeleteUserBookRead($id: Int!) {
    delete_user_book_read(id: $id) {
        id
    }
}
"""
