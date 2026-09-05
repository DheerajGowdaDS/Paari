"""A2A Gateway - receive and route A2A messages from external agents.

Phase 2: This module provides the A2A message receive endpoint that
connects external Buyer Agents to Merchant Agents through Paari.
"""

from __future__ import annotations

import json
import logging
import uuid

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from paari.a2a.protocol import (
    create_error_response,
    create_success_response,
    deserialize_message,
    serialize_message,
    validate_message,
)
from paari.a2a.types import A2AAction, A2AMessage, A2AResponse, A2AStatus
from paari.agent.merchant_agent import get_merchant_agent
from paari.db.engine import get_session_maker

_log = logging.getLogger("paari.a2a.gateway")
router = APIRouter(prefix="/a2a", tags=["a2a"])


class A2AMessageRequest(BaseModel):
    """Wrapper for A2A message in HTTP POST body."""

    message: dict


class IdempotencyResponse(BaseModel):
    """Response when idempotency key matches a previous request."""

    cached: bool = True
    response: dict


async def _check_idempotency(
    idempotency_key: str,
    agent_id: str,
    action: str,
) -> dict | None:
    """Check if an idempotency key was already processed.

    Returns the cached response if found, None otherwise.
    """
    maker = get_session_maker()
    async with maker() as session:
        from sqlalchemy import text

        row = (
            await session.execute(
                text(
                    "SELECT response_json FROM idempotency_keys "
                    "WHERE key = :key AND agent_id = :agent_id AND action = :action"
                ),
                {"key": idempotency_key, "agent_id": agent_id, "action": action},
            )
        ).first()

        if row:
            return json.loads(row.response_json)
    return None


async def _store_idempotency_response(
    idempotency_key: str,
    agent_id: str,
    action: str,
    response: A2AResponse,
) -> None:
    """Store response for idempotency."""
    maker = get_session_maker()
    async with maker() as session:
        from sqlalchemy import text

        try:
            await session.execute(
                text(
                    "INSERT INTO idempotency_keys (key, agent_id, action, response_json) "
                    "VALUES (:key, :agent_id, :action, :response)"
                ),
                {
                    "key": idempotency_key,
                    "agent_id": agent_id,
                    "action": action,
                    "response": serialize_message(response),
                },
            )
            await session.commit()
        except Exception as e:
            _log.warning("Failed to store idempotency response: %s", e)


async def _notify_buyer_agent(message: A2AMessage, response: A2AResponse) -> None:
    """Blueprint Step 13: push the fulfillment result back to the buyer agent.

    Best-effort: failures are logged, never raised.
    """
    try:
        from sqlalchemy import text

        maker = get_session_maker()
        async with maker() as session:
            row = (
                await session.execute(
                    text(
                        "SELECT a2a_endpoint FROM agents "
                        "WHERE id = :id OR display_id = :id"
                    ),
                    {"id": message.sender_id},
                )
            ).first()

        endpoint = row.a2a_endpoint if row else None
        if not endpoint:
            _log.warning(
                "No a2a_endpoint for buyer agent %s; skipping fulfillment notification",
                message.sender_id,
            )
            return

        notification = A2AMessage(
            sender_id=message.receiver_id,
            receiver_id=message.sender_id,
            action=A2AAction.FULFILL_ORDER,
            payload=response.payload,
            reply_to=message.message_id,
        )

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                endpoint,
                content=serialize_message(notification),
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
        _log.info(
            "Notified buyer agent %s of fulfillment for %s",
            message.sender_id,
            message.message_id,
        )
    except Exception as exc:
        _log.warning("Failed to notify buyer agent of fulfillment: %s", exc)


async def _authenticate_agent(message: A2AMessage) -> tuple[bool, str | None]:
    """Authenticate an agent from the A2A message.

    In Phase 2, we do basic verification. Full JWT auth comes later.

    Returns:
        tuple of (is_authenticated, error_message)
    """
    # For Phase 2, we trust messages from registered agents
    maker = get_session_maker()
    async with maker() as session:
        from sqlalchemy import text

        row = (
            await session.execute(
                text(
                    "SELECT id, status FROM agents "
                    "WHERE id = :id OR display_id = :id"
                ),
                {"id": message.sender_id},
            )
        ).first()

        if not row:
            return False, f"Unknown agent: {message.sender_id}"

        if row.status != "ACTIVE":
            return False, f"Agent not active: {message.sender_id}"

    return True, None


async def _authorize_action(
    agent_id: str,
    action: str,
) -> tuple[bool, str | None]:
    """Check if agent has capability for the action.

    Returns:
        tuple of (is_authorized, error_message)
    """
    maker = get_session_maker()
    async with maker() as session:
        from sqlalchemy import text

        row = (
            await session.execute(
                text("SELECT capabilities_json FROM agents WHERE id = :id OR display_id = :id"),
                {"id": agent_id},
            )
        ).first()

        if not row:
            return False, "Agent not found"

        try:
            capabilities = json.loads(row.capabilities_json or "[]")
        except Exception:
            capabilities = []

        # Map actions to required capabilities
        action_capabilities = {
            "REQUEST_QUOTE": "quote.request",
            "ACCEPT_QUOTE": "quote.accept",
            "EXECUTE_PAYMENT": "payment.execute",
            "NEGOTIATE": "deal.negotiate",
            "DISCOVER": "catalog.read",
        }

        required = action_capabilities.get(action)
        if required and required not in capabilities:
            return False, f"Missing capability: {required}"

    return True, None


@router.post("/merchant")
async def receive_merchant_message(request: Request) -> A2AResponse:
    """Receive A2A message for merchant agent operations.

    POST /a2a/merchant

    This endpoint receives messages from Buyer Agents directed to
    Merchant Agents. It handles:
    - Authentication
    - Authorization
    - Idempotency
    - Message routing to Merchant Agent

    Request body should be the serialized A2AMessage.
    """
    try:
        body = await request.body()
        if not body:
            return A2AResponse(
                message_id="",
                sender_id="paari-gateway",
                receiver_id="",
                status=A2AStatus.ERROR,
                error="Empty request body",
            )

        message = deserialize_message(body)
    except Exception as e:
        _log.error("Failed to deserialize message: %s", e)
        return A2AResponse(
            message_id="",
            sender_id="paari-gateway",
            receiver_id="",
            status=A2AStatus.ERROR,
            error=f"Invalid message format: {e}",
        )

    # Validate message
    is_valid, error = validate_message(message)
    if not is_valid:
        return create_error_response(message, error or "Invalid message")

    # Check idempotency
    if message.idempotency_key:
        cached = await _check_idempotency(
            message.idempotency_key,
            message.sender_id,
            message.action.value,
        )
        if cached:
            _log.info("Returning cached response for idempotency key: %s", message.idempotency_key)
            return A2AResponse(**cached)

    # Authenticate sender
    is_auth, auth_error = await _authenticate_agent(message)
    if not is_auth:
        return create_error_response(message, auth_error or "Authentication failed")

    # Authorize action
    is_authz, authz_error = await _authorize_action(
        message.sender_id,
        message.action.value,
    )
    if not is_authz:
        return create_error_response(message, authz_error or "Authorization failed")

    # Route to merchant agent
    try:
        # Get target merchant agent
        merchant_agent = get_merchant_agent(message.receiver_id)
        if not merchant_agent:
            return create_error_response(message, f"Merchant agent not found: {message.receiver_id}")

        # Handle the message
        response = await merchant_agent.handle_message(message)

        # Blueprint Step 13: notify the buyer agent when an order is fulfilled
        # (fulfillment answers with ORDER_CONFIRMED; treat it as success)
        if message.action == A2AAction.FULFILL_ORDER and response.status in (
            A2AStatus.SUCCESS,
            A2AStatus.ORDER_CONFIRMED,
        ):
            await _notify_buyer_agent(message, response)

        # Store idempotency response
        if message.idempotency_key and response.status in (
            A2AStatus.SUCCESS,
            A2AStatus.ORDER_CONFIRMED,
        ):
            await _store_idempotency_response(
                message.idempotency_key,
                message.sender_id,
                message.action.value,
                response,
            )

        return response

    except Exception as e:
        _log.exception("Error processing message: %s", e)
        return create_error_response(message, f"Internal error: {e}")


@router.post("/buyer")
async def receive_buyer_message(request: Request) -> A2AResponse:
    """Receive A2A message for buyer agent operations.

    POST /a2a/buyer

    This endpoint allows the Paari gateway to push messages to the Buyer Agent,
    enabling bidirectional A2A communication.
    """
    try:
        body = await request.body()
        if not body:
            return A2AResponse(
                message_id="",
                sender_id="paari-gateway",
                receiver_id="",
                status=A2AStatus.ERROR,
                error="Empty request body",
            )
        message = deserialize_message(body)
    except Exception as e:
        _log.error("Failed to deserialize message: %s", e)
        return A2AResponse(
            message_id="",
            sender_id="paari-gateway",
            receiver_id="",
            status=A2AStatus.ERROR,
            error=f"Invalid message format: {e}",
        )

    # Validate
    is_valid, error = validate_message(message)
    if not is_valid:
        return create_error_response(message, error or "Invalid message")

    # Route based on action
    if message.action == A2AAction.PAYMENT_RESULT:
        # Payment result notification - return success
        return create_success_response(message, {"received": True})
    elif message.action == A2AAction.FULFILL_ORDER:
        # Order fulfillment notification
        return create_success_response(message, {"received": True})

    return create_error_response(message, f"Unsupported action for buyer: {message.action}")


@router.get("/health")
async def a2a_health() -> dict:
    """Health check for A2A gateway."""
    return {"status": "ok", "service": "a2a-gateway"}
