"""A thin, typed wrapper around the Investec Programmable Banking Open API.

The :class:`InvestecClient` handles OAuth2 ``client_credentials``
authentication (including transparent token caching and refresh) and
exposes methods for the core Account Information endpoints as well as
transfers and payments.

Example:
    >>> from tripwire.investec import InvestecClient
    >>> with InvestecClient.from_env() as client:
    ...     for account in client.get_accounts():
    ...         print(account.account_name, client.get_account_balance(account.account_id))
"""

from __future__ import annotations

import base64
import os
import threading
import time
from typing import Any

import httpx

from .exceptions import (
    InvestecAPIError,
    InvestecAuthError,
    InvestecConfigError,
)
from .models import Account, AccountBalance, Transaction

# Public Investec environments. The sandbox is seeded with shared demo
# credentials and is safe to experiment against.
PRODUCTION_BASE_URL = "https://openapi.investec.com"
SANDBOX_BASE_URL = "https://openapisandbox.investec.com"

_TOKEN_PATH = "/identity/v2/oauth2/token"
_API_PREFIX = "/za/pb/v1"

# Refresh the access token slightly before it actually expires to avoid
# racing the server clock on long-lived clients.
_TOKEN_EXPIRY_BUFFER_SECONDS = 60
_DEFAULT_TIMEOUT = 30.0


class InvestecClient:
    """Client for the Investec Programmable Banking Open API.

    Args:
        client_id: OAuth2 client identifier.
        client_secret: OAuth2 client secret.
        api_key: The ``x-api-key`` issued alongside the OAuth credentials.
        base_url: API base URL. Defaults to the production environment;
            pass :data:`SANDBOX_BASE_URL` for the sandbox.
        timeout: Per-request timeout in seconds. Ignored when
            ``http_client`` is supplied (configure the timeout on that
            client instead).
        http_client: An optional pre-configured :class:`httpx.Client`.
            Mainly useful for testing or advanced transport configuration.
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        api_key: str,
        *,
        base_url: str = PRODUCTION_BASE_URL,
        timeout: float = _DEFAULT_TIMEOUT,
        http_client: httpx.Client | None = None,
    ) -> None:
        if not client_id or not client_secret or not api_key:
            raise InvestecConfigError(
                "client_id, client_secret and api_key are all required"
            )

        self._client_id = client_id
        self._client_secret = client_secret
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")

        self._http = http_client or httpx.Client(base_url=self._base_url, timeout=timeout)
        self._owns_http = http_client is None

        self._access_token: str | None = None
        self._token_expires_at: float = 0.0
        self._auth_lock = threading.Lock()

    @classmethod
    def from_env(
        cls,
        *,
        base_url: str | None = None,
        timeout: float = _DEFAULT_TIMEOUT,
        http_client: httpx.Client | None = None,
    ) -> "InvestecClient":
        """Construct a client from environment variables.

        Reads ``INVESTEC_CLIENT_ID``, ``INVESTEC_CLIENT_SECRET`` and
        ``INVESTEC_API_KEY``. ``INVESTEC_BASE_URL`` is used as the base URL
        when ``base_url`` is not supplied explicitly.

        Raises:
            InvestecConfigError: If any required variable is missing.
        """
        # Strip surrounding whitespace so a stray trailing newline in a
        # copied credential surfaces as a clear config error rather than a
        # cryptic 401 from the auth endpoint.
        client_id = os.environ.get("INVESTEC_CLIENT_ID", "").strip()
        client_secret = os.environ.get("INVESTEC_CLIENT_SECRET", "").strip()
        api_key = os.environ.get("INVESTEC_API_KEY", "").strip()
        env_base_url = os.environ.get("INVESTEC_BASE_URL", "").strip()
        resolved_base_url = base_url or env_base_url or PRODUCTION_BASE_URL

        if not client_id or not client_secret or not api_key:
            raise InvestecConfigError(
                "Missing Investec credentials. Set INVESTEC_CLIENT_ID, "
                "INVESTEC_CLIENT_SECRET and INVESTEC_API_KEY."
            )

        return cls(
            client_id=client_id,
            client_secret=client_secret,
            api_key=api_key,
            base_url=resolved_base_url,
            timeout=timeout,
            http_client=http_client,
        )

    # -- Authentication ----------------------------------------------------

    def _url(self, path: str) -> str:
        """Build an absolute URL from ``path``.

        Using absolute URLs (rather than relying on the HTTP client's
        ``base_url``) keeps an injected :class:`httpx.Client` working even
        when it was created without a ``base_url`` configured.
        """
        return f"{self._base_url}{path}"

    def _basic_auth_header(self) -> str:
        """Return the HTTP Basic ``Authorization`` header for the token call."""
        raw = f"{self._client_id}:{self._client_secret}".encode("utf-8")
        return "Basic " + base64.b64encode(raw).decode("ascii")

    def _token_is_valid(self) -> bool:
        """Return True while the cached token is present and not near expiry."""
        return (
            self._access_token is not None
            and time.monotonic() < self._token_expires_at - _TOKEN_EXPIRY_BUFFER_SECONDS
        )

    def authenticate(self, *, force: bool = False) -> str:
        """Obtain (and cache) an OAuth2 access token.

        A cached token is reused until it is close to expiry. Pass
        ``force=True`` to always request a fresh token. Access is guarded by
        a lock so concurrent callers do not race to refresh the token.

        Returns:
            The bearer access token.

        Raises:
            InvestecAuthError: If the token request is rejected.
        """
        with self._auth_lock:
            # Re-check under the lock so that a token refreshed by another
            # thread while we were waiting is reused instead of duplicated.
            if not force and self._token_is_valid():
                assert self._access_token is not None  # for type checkers
                return self._access_token

            try:
                response = self._http.post(
                    self._url(_TOKEN_PATH),
                    headers={
                        "Authorization": self._basic_auth_header(),
                        "x-api-key": self._api_key,
                        "Content-Type": "application/x-www-form-urlencoded",
                        "Accept": "application/json",
                    },
                    data={"grant_type": "client_credentials"},
                )
            except httpx.HTTPError as exc:  # pragma: no cover - network failure path
                raise InvestecAuthError(f"Token request failed: {exc}") from exc

            if response.status_code != httpx.codes.OK:
                raise InvestecAuthError(
                    f"Authentication failed with status {response.status_code}: {response.text}"
                )

            try:
                payload = response.json()
            except ValueError as exc:
                raise InvestecAuthError(
                    f"Token response was not valid JSON: {response.text}"
                ) from exc
            token = payload.get("access_token")
            if not token:
                raise InvestecAuthError("Token response did not contain an access_token")

            expires_in = float(payload.get("expires_in", 0) or 0)
            self._access_token = token
            self._token_expires_at = time.monotonic() + expires_in
            return token

    # -- Request plumbing --------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any | None = None,
    ) -> Any:
        """Send an authenticated request, retrying once on a 401."""
        def send(token: str) -> httpx.Response:
            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            }
            try:
                return self._http.request(
                    method,
                    self._url(f"{_API_PREFIX}{path}"),
                    headers=headers,
                    params=params,
                    json=json,
                )
            except httpx.HTTPError as exc:
                raise InvestecAPIError(f"Request to {path} failed: {exc}") from exc

        response = send(self.authenticate())

        if response.status_code == httpx.codes.UNAUTHORIZED:
            # Token may have been revoked server-side; retry once with a fresh one.
            response = send(self.authenticate(force=True))

        if not response.is_success:
            raise InvestecAPIError(
                f"Investec API returned {response.status_code} for {path}",
                status_code=response.status_code,
                response_body=response.text,
            )

        try:
            return response.json()
        except ValueError as exc:
            raise InvestecAPIError(
                f"Investec API returned invalid JSON for {path}",
                status_code=response.status_code,
                response_body=response.text,
            ) from exc

    @staticmethod
    def _unwrap_data(payload: Any) -> Any:
        """Return the ``data`` envelope from an Investec response payload."""
        if isinstance(payload, dict) and "data" in payload:
            return payload["data"]
        return payload

    # -- Account information ------------------------------------------------

    def get_accounts(self) -> list[Account]:
        """List the accounts accessible to the authenticated profile."""
        data = self._unwrap_data(self._request("GET", "/accounts"))
        accounts = data.get("accounts", []) if isinstance(data, dict) else data
        return [Account.from_dict(item) for item in accounts]

    def get_account_balance(self, account_id: str) -> AccountBalance:
        """Fetch the current balance for ``account_id``."""
        data = self._unwrap_data(
            self._request("GET", f"/accounts/{account_id}/balance")
        )
        return AccountBalance.from_dict(data)

    def get_account_transactions(
        self,
        account_id: str,
        *,
        from_date: str | None = None,
        to_date: str | None = None,
        transaction_type: str | None = None,
    ) -> list[Transaction]:
        """List transactions for ``account_id``.

        Args:
            account_id: The account to query.
            from_date: Inclusive start date in ``YYYY-MM-DD`` format.
            to_date: Inclusive end date in ``YYYY-MM-DD`` format.
            transaction_type: Optional Investec transaction type filter.
        """
        params: dict[str, Any] = {}
        if from_date is not None:
            params["fromDate"] = from_date
        if to_date is not None:
            params["toDate"] = to_date
        if transaction_type is not None:
            params["transactionType"] = transaction_type

        data = self._unwrap_data(
            self._request(
                "GET",
                f"/accounts/{account_id}/transactions",
                params=params or None,
            )
        )
        transactions = data.get("transactions", []) if isinstance(data, dict) else data
        return [Transaction.from_dict(item) for item in transactions]

    # -- Payments and transfers --------------------------------------------

    def transfer_multiple(
        self, account_id: str, transfers: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Transfer funds from ``account_id`` to one or more own accounts.

        Args:
            account_id: The source account.
            transfers: A list of transfer instruction objects as defined by
                the Investec API (e.g. ``beneficiaryAccountId``, ``amount``,
                ``myReference``, ``theirReference``).

        Returns:
            The raw ``data`` envelope from the API response.
        """
        body = {"transferList": transfers}
        return self._unwrap_data(
            self._request(
                "POST", f"/accounts/{account_id}/transfermultiple", json=body
            )
        )

    def pay_multiple(
        self, account_id: str, payments: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Pay one or more beneficiaries from ``account_id``.

        Args:
            account_id: The source account.
            payments: A list of payment instruction objects as defined by
                the Investec API (e.g. ``beneficiaryId``, ``amount``,
                ``myReference``, ``theirReference``).

        Returns:
            The raw ``data`` envelope from the API response.
        """
        body = {"paymentList": payments}
        return self._unwrap_data(
            self._request(
                "POST", f"/accounts/{account_id}/paymultiple", json=body
            )
        )

    # -- Lifecycle ----------------------------------------------------------

    def close(self) -> None:
        """Close the underlying HTTP client if this instance owns it."""
        if self._owns_http:
            self._http.close()

    def __enter__(self) -> "InvestecClient":
        """Enter the context manager, returning this client."""
        return self

    def __exit__(self, *exc_info: object) -> None:
        """Exit the context manager, closing the owned HTTP client."""
        self.close()
