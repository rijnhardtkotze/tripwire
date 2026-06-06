"""Typed data models for Investec API resources.

These dataclasses provide convenient, typed access to the most common
fields returned by the Investec Programmable Banking Open API while
retaining the full raw payload on each instance for forward compatibility
with fields not yet modelled here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


def _to_decimal(value: Any) -> Decimal:
    """Convert an API numeric value to :class:`~decimal.Decimal`.

    Parsing through ``str`` keeps monetary values exact and avoids the
    binary rounding drift inherent to ``float`` (e.g. ``0.1 + 0.2``).
    """
    if value is None or value == "":
        return Decimal("0")
    return Decimal(str(value))


@dataclass
class Account:
    """A bank account belonging to the authenticated profile."""

    account_id: str
    account_number: str
    account_name: str
    reference_name: str
    product_name: str
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Account":
        """Build an :class:`Account` from a raw API account object."""
        return cls(
            account_id=data.get("accountId", ""),
            account_number=data.get("accountNumber", ""),
            account_name=data.get("accountName", ""),
            reference_name=data.get("referenceName", ""),
            product_name=data.get("productName", ""),
            raw=data,
        )


@dataclass
class AccountBalance:
    """The balance snapshot for a single account."""

    account_id: str
    current_balance: Decimal
    available_balance: Decimal
    currency: str
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AccountBalance":
        """Build an :class:`AccountBalance` from a raw API balance object."""
        return cls(
            account_id=data.get("accountId", ""),
            current_balance=_to_decimal(data.get("currentBalance")),
            available_balance=_to_decimal(data.get("availableBalance")),
            currency=data.get("currency", ""),
            raw=data,
        )


@dataclass
class Transaction:
    """A single account transaction."""

    account_id: str
    transaction_type: str
    status: str
    description: str
    card_number: str
    posted_order: int | None
    posting_date: str
    value_date: str
    action_date: str
    amount: Decimal
    # The Investec "type" field (e.g. DEBIT/CREDIT). Named ``movement_type``
    # to avoid shadowing the ``type`` built-in.
    movement_type: str
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Transaction":
        """Build a :class:`Transaction` from a raw API transaction object."""
        posted_order = data.get("postedOrder")
        return cls(
            account_id=data.get("accountId", ""),
            transaction_type=data.get("transactionType", ""),
            status=data.get("status", ""),
            description=data.get("description", ""),
            card_number=data.get("cardNumber", ""),
            posted_order=int(posted_order) if posted_order is not None else None,
            posting_date=data.get("postingDate", ""),
            value_date=data.get("valueDate", ""),
            action_date=data.get("actionDate", ""),
            amount=_to_decimal(data.get("amount")),
            movement_type=data.get("type", ""),
            raw=data,
        )
