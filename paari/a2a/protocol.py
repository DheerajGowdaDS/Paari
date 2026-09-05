"""A2A protocol helpers for serialization, validation, and error responses."""

from __future__ import annotations

import json
import logging
from typing import Any

from paari.a2a.types import A2AAction, A2AMessage, A2AResponse, A2AStatus

_log = logging.getLogger("paari.a2a.protocol")


def serialize_message(message: A2AMessage) -> str:
    """Serialize an A2A message to JSON string."""
    return message.model_dump_json()


def deserialize_message(data: str | bytes | dict) -> A2AMessage:
    """Deserialize an A2A message from JSON string, raw bytes, or dict."""
    if isinstance(data, (str, bytes)):
        data = json.loads(data)
    return A2AMessage(**data)


def validate_message(message: A2AMessage) -> tuple[bool, str | None]:
    """Validate an A2A message.

    Returns:
        tuple of (is_valid, error_message)
    """
    if not message.sender_id:
        return False, "sender_id is required"
    if not message.receiver_id:
        return False, "receiver_id is required"
    if not message.action:
        return False, "action is required"
    if message.sender_id == message.receiver_id:
        return False, "sender_id and receiver_id cannot be the same"
    return True, None


def create_error_response(
    request_message: A2AMessage,
    error_message: str,
    status: A2AStatus = A2AStatus.ERROR,
) -> A2AResponse:
    """Create an error A2A response."""
    return A2AResponse(
        message_id=request_message.message_id,
        sender_id=request_message.receiver_id,
        receiver_id=request_message.sender_id,
        status=status,
        payload={},
        error=error_message,
    )


def create_success_response(
    request_message: A2AMessage,
    payload: dict[str, Any],
) -> A2AResponse:
    """Create a success A2A response."""
    return A2AResponse(
        message_id=request_message.message_id,
        sender_id=request_message.receiver_id,
        receiver_id=request_message.sender_id,
        status=A2AStatus.SUCCESS,
        payload=payload,
        error=None,
    )


def create_review_response(
    request_message: A2AMessage,
    payload: dict[str, Any],
    reason: str,
) -> A2AResponse:
    """Create a review-required A2A response."""
    payload_with_reason = {**payload, "review_reason": reason}
    return A2AResponse(
        message_id=request_message.message_id,
        sender_id=request_message.receiver_id,
        receiver_id=request_message.sender_id,
        status=A2AStatus.REVIEW_REQUIRED,
        payload=payload_with_reason,
        error=None,
    )


def create_deny_response(
    request_message: A2AMessage,
    reason: str,
) -> A2AResponse:
    """Create a deny A2A response."""
    return A2AResponse(
        message_id=request_message.message_id,
        sender_id=request_message.receiver_id,
        receiver_id=request_message.sender_id,
        status=A2AStatus.DENIED,
        payload={"deny_reason": reason},
        error=reason,
    )


ACTION_HANDLERS: dict[A2AAction, str] = {
    A2AAction.DISCOVER: "handle_discover",
    A2AAction.REQUEST_QUOTE: "handle_request_quote",
    A2AAction.ACCEPT_QUOTE: "handle_accept_quote",
    A2AAction.EXECUTE_PAYMENT: "handle_execute_payment",
    A2AAction.PAYMENT_RESULT: "handle_payment_result",
    A2AAction.FULFILL_ORDER: "handle_fulfill_order",
    A2AAction.CANCEL: "handle_cancel",
    A2AAction.NEGOTIATE: "handle_negotiate",
    A2AAction.COUNTER_OFFER: "handle_counter_offer",
}


def get_action_handler(action: A2AAction) -> str | None:
    """Get the handler method name for an action."""
    return ACTION_HANDLERS.get(action)


def is_valid_action(action: str) -> bool:
    """Check if an action string is a valid A2AAction."""
    try:
        A2AAction(action)
        return True
    except ValueError:
        return False
