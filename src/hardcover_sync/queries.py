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

BOOK_BY_ISBN_QUERY = """
query BookByISBN($isbn: String!) {
    editions(where: {isbn_13: {_eq: $isbn}}, limit: 1) {
        id
        isbn_10
        isbn_13
        title
        book {
            id
            title
            slug
            contributions {
                author {
                    id
                    name
                }
            }
        }
    }
}
"""

BOOK_BY_ISBN_10_QUERY = """
query BookByISBN10($isbn: String!) {
    editions(where: {isbn_10: {_eq: $isbn}}, limit: 1) {
        id
        isbn_10
        isbn_13
        title
        book {
            id
            title
            slug
            contributions {
                author {
                    id
                    name
                }
            }
        }
    }
}
"""

BOOK_SEARCH_QUERY = """
query SearchBooks($query: String!) {
    search(query: $query, query_type: "Book", per_page: 20) {
        results
    }
}
"""

BOOK_BY_ID_QUERY = """
query BookById($id: Int!) {
    books(where: {id: {_eq: $id}}) {
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
        editions {
            id
            isbn_13
            isbn_10
            title
            pages
        }
    }
}
"""

# =============================================================================
# User Library Queries
# =============================================================================

USER_BOOKS_QUERY = """
query UserBooks($user_id: Int!, $limit: Int!, $offset: Int!) {
    user_books(
        where: {user_id: {_eq: $user_id}},
        limit: $limit,
        offset: $offset,
        order_by: {updated_at: desc}
    ) {
        id
        book_id
        edition_id
        status_id
        rating
        review
        created_at
        updated_at
        book {
            id
            title
            slug
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
        }
        user_book_reads(order_by: {started_at: desc}) {
            id
            started_at
            finished_at
            progress_pages
            edition_id
        }
    }
}
"""

USER_BOOK_BY_BOOK_ID_QUERY = """
query UserBookByBookId($user_id: Int!, $book_id: Int!) {
    user_books(
        where: {
            user_id: {_eq: $user_id},
            book_id: {_eq: $book_id}
        },
        limit: 1
    ) {
        id
        book_id
        edition_id
        status_id
        rating
        review
        created_at
        updated_at
        user_book_reads(order_by: {started_at: desc}) {
            id
            started_at
            finished_at
            progress_pages
            edition_id
        }
    }
}
"""

# =============================================================================
# User Library Mutations
# =============================================================================

INSERT_USER_BOOK_MUTATION = """
mutation InsertUserBook(
    $book_id: Int!,
    $edition_id: Int,
    $status_id: Int!,
    $rating: numeric,
    $progress_pages: Int,
    $started_at: date,
    $finished_at: date,
    $review: String
) {
    insert_user_book(
        object: {
            book_id: $book_id,
            edition_id: $edition_id,
            status_id: $status_id,
            rating: $rating,
            progress_pages: $progress_pages,
            started_at: $started_at,
            finished_at: $finished_at,
            review: $review
        }
    ) {
        id
        book_id
        status_id
        rating
        updated_at
    }
}
"""

UPDATE_USER_BOOK_MUTATION = """
mutation UpdateUserBook(
    $id: Int!,
    $status_id: Int,
    $rating: numeric,
    $progress_pages: Int,
    $started_at: date,
    $finished_at: date,
    $review: String
) {
    update_user_book(
        where: {id: {_eq: $id}},
        _set: {
            status_id: $status_id,
            rating: $rating,
            progress_pages: $progress_pages,
            started_at: $started_at,
            finished_at: $finished_at,
            review: $review
        }
    ) {
        returning {
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
    delete_user_book(where: {id: {_eq: $id}}) {
        affected_rows
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
