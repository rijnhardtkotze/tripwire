"""Tests for the Investec API wrapper.

These exercise the client against a mocked HTTP transport so no real
network calls or credentials are required.
"""

from __future__ import annotations

import base64

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
    return InvestecClient(
        client_id="id",
        client_secret="secret",
        api_key="key",
        base_url=BASE_URL,
    )


def mock_token(httpx_mock: HTTPXMock, *, expires_in: int = 1800) -> None:
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
    with pytest.raises(InvestecConfigError):
        InvestecClient(client_id="", client_secret="s", api_key="k")


def test_from_env_missing_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("INVESTEC_CLIENT_ID", "INVESTEC_CLIENT_SECRET", "INVESTEC_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(InvestecConfigError):
        InvestecClient.from_env()


def test_from_env_reads_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INVESTEC_CLIENT_ID", "cid")
    monkeypatch.setenv("INVESTEC_CLIENT_SECRET", "csecret")
    monkeypatch.setenv("INVESTEC_API_KEY", "apikey")
    monkeypatch.setenv("INVESTEC_BASE_URL", BASE_URL)
    client = InvestecClient.from_env()
    assert client._base_url == BASE_URL


def test_from_env_strips_whitespace(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INVESTEC_CLIENT_ID", "  cid\n")
    monkeypatch.setenv("INVESTEC_CLIENT_SECRET", "csecret ")
    monkeypatch.setenv("INVESTEC_API_KEY", "\tapikey")
    monkeypatch.delenv("INVESTEC_BASE_URL", raising=False)
    client = InvestecClient.from_env(base_url=BASE_URL)
    assert client._client_id == "cid"
    assert client._client_secret == "csecret"
    assert client._api_key == "apikey"


def test_authenticate_sends_basic_auth_and_api_key(httpx_mock: HTTPXMock) -> None:
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


def test_authenticate_caches_token(httpx_mock: HTTPXMock) -> None:
    mock_token(httpx_mock)
    with make_client() as client:
        first = client.authenticate()
        second = client.authenticate()

    assert first == second
    # Only one token request should have been made thanks to caching.
    assert len(httpx_mock.get_requests()) == 1


def test_authenticate_failure_raises(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(method="POST", url=TOKEN_URL, status_code=401, text="nope")
    with make_client() as client:
        with pytest.raises(InvestecAuthError):
            client.authenticate()


def test_get_accounts(httpx_mock: HTTPXMock) -> None:
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


def test_get_account_balance(httpx_mock: HTTPXMock) -> None:
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
    assert balance.current_balance == 28857.76
    assert balance.available_balance == 98857.76
    assert balance.currency == "ZAR"


def test_get_account_transactions_with_filters(httpx_mock: HTTPXMock) -> None:
    mock_token(httpx_mock)
    httpx_mock.add_response(
        method="GET",
        url=(
            f"{BASE_URL}/za/pb/v1/accounts/123/transactions"
            "?fromDate=2026-01-01&toDate=2026-01-31&transactionType=CardPurchases"
        ),
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
                        "type": "DEBIT",
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
    assert txn.amount == 42.5
    assert txn.description == "Coffee Shop"
    assert txn.posted_order == 1
    assert txn.movement_type == "DEBIT"


def test_transfer_multiple_posts_transfer_list(httpx_mock: HTTPXMock) -> None:
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


def test_unauthorized_triggers_token_refresh(httpx_mock: HTTPXMock) -> None:
    # First token, then a 401 on the resource, then a forced re-auth, then success.
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
