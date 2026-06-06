"""Tests for the Investec API wrapper.

These exercise the client against a mocked HTTP transport so no real
network calls or credentials are required.
"""

from __future__ import annotations

import base64
from decimal import Decimal

import httpx
import pytest
from pytest_httpx import HTTPXMock

from tripwire.investec import (
    Account,
    AccountBalance,
    InvestecAPIError,
    InvestecAuthError,
    InvestecClient,
    InvestecConfigError,
    Transaction,
)
from tripwire.investec.client import SANDBOX_BASE_URL

BASE_URL = SANDBOX_BASE_URL
TOKEN_URL = f"{BASE_URL}/identity/v2/oauth2/token"


def make_client() -> InvestecClient:
    """Build a sandbox-configured client with dummy credentials."""
    return InvestecClient(
        client_id="id",
        client_secret="secret",
        api_key="key",
        base_url=BASE_URL,
    )


def mock_token(httpx_mock: HTTPXMock, *, expires_in: int = 1800) -> None:
    """Register a successful OAuth2 token response on the mock transport."""
    httpx_mock.add_response(
        method="POST",
        url=TOKEN_URL,
        json={
            "access_token": "test-token",
            "token_type": "Bearer",
            "expires_in": expires_in,
            "scope": "accounts transactions",
        },
    )


def test_requires_all_credentials() -> None:
    """Construction fails when any credential is missing."""
    with pytest.raises(InvestecConfigError):
        InvestecClient(client_id="", client_secret="s", api_key="k")


def test_from_env_missing_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """from_env raises when the required variables are absent."""
    for var in ("INVESTEC_CLIENT_ID", "INVESTEC_CLIENT_SECRET", "INVESTEC_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(InvestecConfigError):
        InvestecClient.from_env()


def test_from_env_reads_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    """from_env reads credentials and base URL from the environment."""
    monkeypatch.setenv("INVESTEC_CLIENT_ID", "cid")
    monkeypatch.setenv("INVESTEC_CLIENT_SECRET", "csecret")
    monkeypatch.setenv("INVESTEC_API_KEY", "apikey")
    monkeypatch.setenv("INVESTEC_BASE_URL", BASE_URL)
    client = InvestecClient.from_env()
    assert client._base_url == BASE_URL


def test_from_env_strips_whitespace(monkeypatch: pytest.MonkeyPatch) -> None:
    """from_env trims surrounding whitespace from credential values."""
    monkeypatch.setenv("INVESTEC_CLIENT_ID", "  cid\n")
    monkeypatch.setenv("INVESTEC_CLIENT_SECRET", "csecret ")
    monkeypatch.setenv("INVESTEC_API_KEY", "\tapikey")
    monkeypatch.delenv("INVESTEC_BASE_URL", raising=False)
    client = InvestecClient.from_env(base_url=BASE_URL)
    assert client._client_id == "cid"
    assert client._client_secret == "csecret"
    assert client._api_key == "apikey"


def test_from_env_strips_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """from_env trims whitespace from INVESTEC_BASE_URL."""
    monkeypatch.setenv("INVESTEC_CLIENT_ID", "cid")
    monkeypatch.setenv("INVESTEC_CLIENT_SECRET", "csecret")
    monkeypatch.setenv("INVESTEC_API_KEY", "apikey")
    monkeypatch.setenv("INVESTEC_BASE_URL", f"  {BASE_URL}\n")
    client = InvestecClient.from_env()
    assert client._base_url == BASE_URL


def test_authenticate_sends_basic_auth_and_api_key(httpx_mock: HTTPXMock) -> None:
    """authenticate sends Basic auth, the API key, and the grant type."""
    mock_token(httpx_mock)
    with make_client() as client:
        token = client.authenticate()

    assert token == "test-token"
    request = httpx_mock.get_request()
    assert request is not None
    expected = "Basic " + base64.b64encode(b"id:secret").decode()
    assert request.headers["Authorization"] == expected
    assert request.headers["x-api-key"] == "key"
    assert b"grant_type=client_credentials" in request.content


def test_works_with_injected_client_without_base_url(httpx_mock: HTTPXMock) -> None:
    """An injected client without base_url still resolves absolute URLs."""
    mock_token(httpx_mock)
    httpx_mock.add_response(
        method="GET",
        url=f"{BASE_URL}/za/pb/v1/accounts",
        json={"data": {"accounts": []}},
    )
    injected = httpx.Client()
    client = InvestecClient(
        client_id="id",
        client_secret="secret",
        api_key="key",
        base_url=BASE_URL,
        http_client=injected,
    )
    try:
        assert client.get_accounts() == []
    finally:
        injected.close()


def test_authenticate_caches_token(httpx_mock: HTTPXMock) -> None:
    """A valid token is cached and reused across calls."""
    mock_token(httpx_mock)
    with make_client() as client:
        first = client.authenticate()
        second = client.authenticate()

    assert first == second
    # Only one token request should have been made thanks to caching.
    assert len(httpx_mock.get_requests()) == 1


def test_authenticate_failure_raises(httpx_mock: HTTPXMock) -> None:
    """A rejected token request raises InvestecAuthError."""
    httpx_mock.add_response(method="POST", url=TOKEN_URL, status_code=401, text="nope")
    with make_client() as client:
        with pytest.raises(InvestecAuthError):
            client.authenticate()


def test_authenticate_invalid_json_raises(httpx_mock: HTTPXMock) -> None:
    """A 200 token response with a non-JSON body raises InvestecAuthError."""
    httpx_mock.add_response(method="POST", url=TOKEN_URL, text="not json")
    with make_client() as client:
        with pytest.raises(InvestecAuthError):
            client.authenticate()


def test_authenticate_non_object_json_raises(httpx_mock: HTTPXMock) -> None:
    """A token response that is valid JSON but not an object raises cleanly."""
    httpx_mock.add_response(method="POST", url=TOKEN_URL, json=["unexpected"])
    with make_client() as client:
        with pytest.raises(InvestecAuthError):
            client.authenticate()


def test_get_accounts(httpx_mock: HTTPXMock) -> None:
    """get_accounts maps the response envelope into Account objects."""
    mock_token(httpx_mock)
    httpx_mock.add_response(
        method="GET",
        url=f"{BASE_URL}/za/pb/v1/accounts",
        json={
            "data": {
                "accounts": [
                    {
                        "accountId": "172878438321",
                        "accountNumber": "10010206147",
                        "accountName": "Mr John Doe",
                        "referenceName": "My Account",
                        "productName": "Private Bank Account",
                    }
                ]
            }
        },
    )
    with make_client() as client:
        accounts = client.get_accounts()

    assert len(accounts) == 1
    assert isinstance(accounts[0], Account)
    assert accounts[0].account_id == "172878438321"
    assert accounts[0].product_name == "Private Bank Account"
    # Authenticated data requests must carry both the bearer token and the API key.
    data_request = httpx_mock.get_requests()[-1]
    assert data_request.headers["Authorization"] == "Bearer test-token"
    assert data_request.headers["x-api-key"] == "key"


def test_get_account_balance(httpx_mock: HTTPXMock) -> None:
    """get_account_balance maps the response into an AccountBalance."""
    mock_token(httpx_mock)
    httpx_mock.add_response(
        method="GET",
        url=f"{BASE_URL}/za/pb/v1/accounts/123/balance",
        json={
            "data": {
                "accountId": "123",
                "currentBalance": 28857.76,
                "availableBalance": 98857.76,
                "currency": "ZAR",
            }
        },
    )
    with make_client() as client:
        balance = client.get_account_balance("123")

    assert isinstance(balance, AccountBalance)
    assert balance.current_balance == Decimal("28857.76")
    assert balance.available_balance == Decimal("98857.76")
    assert balance.currency == "ZAR"


def test_monetary_values_are_exact_decimals(httpx_mock: HTTPXMock) -> None:
    """Balances are parsed as exact Decimals with no binary float drift."""
    mock_token(httpx_mock)
    httpx_mock.add_response(
        method="GET",
        url=f"{BASE_URL}/za/pb/v1/accounts/123/balance",
        json={
            "data": {
                "accountId": "123",
                "currentBalance": 0.1,
                "availableBalance": 0.2,
                "currency": "ZAR",
            }
        },
    )
    with make_client() as client:
        balance = client.get_account_balance("123")

    assert isinstance(balance.current_balance, Decimal)
    # The classic float trap (0.1 + 0.2 != 0.3) does not bite with Decimal.
    assert balance.current_balance + balance.available_balance == Decimal("0.3")


def test_get_account_transactions_with_filters(httpx_mock: HTTPXMock) -> None:
    """get_account_transactions forwards filters and maps Transactions."""
    mock_token(httpx_mock)
    httpx_mock.add_response(
        method="GET",
        url=f"{BASE_URL}/za/pb/v1/accounts/123/transactions",
        match_params={
            "fromDate": "2026-01-01",
            "toDate": "2026-01-31",
            "transactionType": "CardPurchases",
        },
        json={
            "data": {
                "transactions": [
                    {
                        "accountId": "123",
                        "type": "DEBIT",
                        "transactionType": "CardPurchases",
                        "status": "POSTED",
                        "description": "Coffee Shop",
                        "amount": 42.5,
                        "postedOrder": 1,
                    }
                ]
            }
        },
    )
    with make_client() as client:
        transactions = client.get_account_transactions(
            "123",
            from_date="2026-01-01",
            to_date="2026-01-31",
            transaction_type="CardPurchases",
        )

    assert len(transactions) == 1
    txn = transactions[0]
    assert isinstance(txn, Transaction)
    assert txn.amount == Decimal("42.5")
    assert txn.description == "Coffee Shop"
    assert txn.posted_order == 1
    assert txn.movement_type == "DEBIT"


def test_transfer_multiple_posts_transfer_list(httpx_mock: HTTPXMock) -> None:
    """transfer_multiple posts a transferList and returns the envelope."""
    mock_token(httpx_mock)
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/za/pb/v1/accounts/123/transfermultiple",
        json={"data": {"TransferResponses": [{"Status": "Success"}]}},
    )
    transfers = [
        {
            "beneficiaryAccountId": "456",
            "amount": "100.00",
            "myReference": "Savings",
            "theirReference": "From John",
        }
    ]
    with make_client() as client:
        result = client.transfer_multiple("123", transfers)

    assert result["TransferResponses"][0]["Status"] == "Success"
    request = httpx_mock.get_requests()[-1]
    assert b"transferList" in request.content


def test_pay_multiple_posts_payment_list(httpx_mock: HTTPXMock) -> None:
    """pay_multiple posts a paymentList and returns the envelope."""
    mock_token(httpx_mock)
    httpx_mock.add_response(
        method="POST",
        url=f"{BASE_URL}/za/pb/v1/accounts/123/paymultiple",
        json={"data": {"TransferResponses": [{"Status": "Success"}]}},
    )
    payments = [
        {
            "beneficiaryId": "789",
            "amount": "250.00",
            "myReference": "Rent",
            "theirReference": "John rent",
        }
    ]
    with make_client() as client:
        result = client.pay_multiple("123", payments)

    assert result["TransferResponses"][0]["Status"] == "Success"
    request = httpx_mock.get_requests()[-1]
    assert b"paymentList" in request.content


def test_api_error_includes_status_and_body(httpx_mock: HTTPXMock) -> None:
    """A non-success response raises InvestecAPIError with status and body."""
    mock_token(httpx_mock)
    httpx_mock.add_response(
        method="GET",
        url=f"{BASE_URL}/za/pb/v1/accounts",
        status_code=500,
        text="server boom",
    )
    with make_client() as client:
        with pytest.raises(InvestecAPIError) as excinfo:
            client.get_accounts()

    assert excinfo.value.status_code == 500
    assert excinfo.value.response_body == "server boom"


def test_invalid_json_response_is_wrapped(httpx_mock: HTTPXMock) -> None:
    """A 2xx response with a non-JSON body raises InvestecAPIError."""
    mock_token(httpx_mock)
    httpx_mock.add_response(
        method="GET",
        url=f"{BASE_URL}/za/pb/v1/accounts",
        text="<html>not json</html>",
    )
    with make_client() as client:
        with pytest.raises(InvestecAPIError) as excinfo:
            client.get_accounts()

    assert excinfo.value.status_code == 200
    assert "not json" in (excinfo.value.response_body or "")


def test_retry_network_error_is_wrapped(httpx_mock: HTTPXMock) -> None:
    """A transport error on the post-401 retry surfaces as InvestecAPIError."""
    mock_token(httpx_mock)
    httpx_mock.add_response(
        method="GET",
        url=f"{BASE_URL}/za/pb/v1/accounts",
        status_code=401,
        text="expired",
    )
    mock_token(httpx_mock)
    httpx_mock.add_exception(
        httpx.ConnectError("boom"),
        method="GET",
        url=f"{BASE_URL}/za/pb/v1/accounts",
    )
    with make_client() as client:
        with pytest.raises(InvestecAPIError):
            client.get_accounts()


def test_unauthorized_triggers_token_refresh(httpx_mock: HTTPXMock) -> None:
    """A 401 forces a token refresh and the request is retried once."""
    mock_token(httpx_mock)
    httpx_mock.add_response(
        method="GET",
        url=f"{BASE_URL}/za/pb/v1/accounts",
        status_code=401,
        text="expired",
    )
    mock_token(httpx_mock)
    httpx_mock.add_response(
        method="GET",
        url=f"{BASE_URL}/za/pb/v1/accounts",
        json={"data": {"accounts": []}},
    )
    with make_client() as client:
        accounts = client.get_accounts()

    assert accounts == []
    # Two token requests: initial + forced refresh after the 401.
    token_requests = [
        r for r in httpx_mock.get_requests() if r.url.path.endswith("/oauth2/token")
    ]
    assert len(token_requests) == 2
