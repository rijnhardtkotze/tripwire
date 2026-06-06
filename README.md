# tripwire
Behavioural tripwires for programmable banking

## Investec API wrapper

Tripwire ships a thin, typed client for the
[Investec Programmable Banking Open API](https://developer.investec.com/programmable-banking/).
It handles OAuth2 `client_credentials` authentication (with transparent
token caching and refresh) and exposes the core Account Information,
transfer, and payment endpoints.

### Usage

```python
from tripwire.investec import InvestecClient, SANDBOX_BASE_URL

# Credentials can be passed directly...
client = InvestecClient(
    client_id="...",
    client_secret="...",
    api_key="...",
    base_url=SANDBOX_BASE_URL,  # omit for production
)

# ...or read from INVESTEC_CLIENT_ID / INVESTEC_CLIENT_SECRET / INVESTEC_API_KEY
with InvestecClient.from_env(base_url=SANDBOX_BASE_URL) as client:
    for account in client.get_accounts():
        balance = client.get_account_balance(account.account_id)
        print(account.account_name, balance.current_balance, balance.currency)

        transactions = client.get_account_transactions(
            account.account_id,
            from_date="2026-01-01",
            to_date="2026-01-31",
        )
        for txn in transactions:
            print(txn.posting_date, txn.description, txn.amount)
```

### Available methods

| Method | Description |
| ------ | ----------- |
| `authenticate()` | Obtain/cache an OAuth2 access token |
| `get_accounts()` | List accessible accounts |
| `get_account_balance(account_id)` | Current and available balance |
| `get_account_transactions(account_id, ...)` | Transactions, with optional date/type filters |
| `transfer_multiple(account_id, transfers)` | Transfer between own accounts |
| `pay_multiple(account_id, payments)` | Pay beneficiaries |

Errors surface as `InvestecConfigError`, `InvestecAuthError`, or
`InvestecAPIError` (all subclasses of `InvestecError`).
