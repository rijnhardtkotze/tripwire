"""Exceptions raised by the Investec API wrapper."""

from __future__ import annotations


class InvestecError(Exception):
    """Base exception for all Investec wrapper errors."""


class InvestecConfigError(InvestecError):
    """Raised when the client is missing required configuration.

    For example, when no credentials are supplied and none can be found
    in the environment.
    """


class InvestecAuthError(InvestecError):
    """Raised when authentication with the Investec API fails.

    This typically indicates invalid credentials or an expired/rejected
    OAuth2 token request.
    """


class InvestecAPIError(InvestecError):
    """Raised when the Investec API returns an unsuccessful response.

    Attributes:
        status_code: The HTTP status code returned by the API.
        response_body: The raw response body, useful for debugging.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        response_body: str | None = None,
    ) -> None:
        """Store the error message alongside HTTP status and response body."""
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body
