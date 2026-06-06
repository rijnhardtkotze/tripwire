"""Investec Programmable Banking Open API wrapper.

This subpackage provides :class:`InvestecClient`, a typed client for the
Investec Programmable Banking Open API, together with the data models and
exceptions it uses.
"""

from .client import (
    PRODUCTION_BASE_URL,
    SANDBOX_BASE_URL,
    InvestecClient,
)
from .exceptions import (
    InvestecAPIError,
    InvestecAuthError,
    InvestecConfigError,
    InvestecError,
)
from .models import Account, AccountBalance, Transaction

__all__ = [
    "InvestecClient",
    "PRODUCTION_BASE_URL",
    "SANDBOX_BASE_URL",
    "Account",
    "AccountBalance",
    "Transaction",
    "InvestecError",
    "InvestecConfigError",
    "InvestecAuthError",
    "InvestecAPIError",
]
