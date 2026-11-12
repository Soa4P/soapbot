"""Delivery of approval events to the operator.

The ledger decides; these channels only report. Nothing here can approve, deny,
pay, or change a request — a dead webhook or an offline phone loses a notification,
never a decision.
"""

from __future__ import annotations

from soapbot.notifications.dispatcher import ApprovalNotifier

__all__ = ["ApprovalNotifier"]
