"""Account and membership service for the web/app archive clients.

Kept out of ``api/`` so the password rules, invite rules and isolation checks are
testable without an HTTP client, and out of ``memory/`` so the storage layer stays
about messages rather than about who may read them.
"""

from __future__ import annotations

from soapbot.accounts.service import (
    Account,
    AccountError,
    authenticate,
    bind_qq_user,
    count_accounts,
    create_invite,
    create_owner,
    grant_membership,
    has_access,
    list_accounts,
    list_memberships,
    redeem_invite,
    set_account_status,
    unbind_qq_user,
)

__all__ = [
    "Account",
    "AccountError",
    "authenticate",
    "bind_qq_user",
    "count_accounts",
    "create_invite",
    "create_owner",
    "grant_membership",
    "has_access",
    "list_accounts",
    "list_memberships",
    "redeem_invite",
    "set_account_status",
    "unbind_qq_user",
]
