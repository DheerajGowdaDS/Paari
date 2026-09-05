"""Checkout API router.

Endpoints:
- GET /checkout/{transaction_id} — Render Razorpay checkout page
- POST /checkout/{transaction_id}/order — Create Razorpay order for checkout
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field

from paari.config import settings
from paari.payment.service import get_payment_service

_log = logging.getLogger("paari.checkout")
router = APIRouter(prefix="/checkout", tags=["checkout"])


class CreateOrderRequest(BaseModel):
    """Request to create a Razorpay order for checkout."""
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(..., description="Payment session ID")


class CreateOrderResponse(BaseModel):
    """Response with Razorpay checkout order details."""
    model_config = ConfigDict(extra="forbid")

    order_id: str
    amount_paise: int
    currency: str
    key_id: str
    checkout_url: str | None = None


@router.get("/{transaction_id}", response_class=HTMLResponse)
async def get_checkout_page(transaction_id: str) -> HTMLResponse:
    """Render the Razorpay checkout page.

    The page includes the Razorpay checkout.js modal and automatically
    creates an order when loaded.
    """
    from sqlalchemy import text
    from paari.db.engine import get_session_maker

    maker = get_session_maker()
    async with maker() as session:
        row = (
            await session.execute(
                text(
                    "SELECT t.id, t.display_id, t.amount_paise, t.currency, t.state, t.razorpay_order_id, "
                    "ps.id AS session_id, ps.status AS session_status "
                    "FROM transactions t "
                    "LEFT JOIN payment_sessions ps ON ps.transaction_id = t.id AND ps.status = 'ACTIVE' "
                    "WHERE t.id = :x OR t.display_id = :x"
                ),
                {"x": transaction_id},
            )
        ).first()

        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"transaction not found: {transaction_id}",
            )

        if row.state not in ("PAYMENT_PENDING", "AUTHORIZED"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"transaction not ready for checkout: {row.state}",
            )

        if row.session_status != "ACTIVE":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="payment session not active",
            )

        amount_paise = int(row.amount_paise)
        currency = row.currency or "INR"
        order_id = row.razorpay_order_id
        session_id = row.session_id

        if not order_id:
            service = get_payment_service()
            result = await service.create_razorpay_order(transaction_id, session_id)
            if not result.success:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"order creation failed: {result.reason}",
                )
            order_id = result.order_id

        razorpay_key = settings.razorpay_key_id or "rzp_test_demo"

        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Paari Checkout</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <script src="https://checkout.razorpay.com/v1/checkout.js"></script>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            margin: 0;
            background: #f5f5f5;
        }}
        .checkout-container {{
            background: white;
            padding: 40px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            text-align: center;
            max-width: 400px;
            width: 100%;
        }}
        h1 {{ color: #333; margin-bottom: 10px; }}
        .amount {{ font-size: 32px; font-weight: bold; color: #2d9a4e; margin: 20px 0; }}
        .description {{ color: #666; margin-bottom: 30px; }}
        .btn-pay {{
            background: #2d9a4e;
            color: white;
            border: none;
            padding: 15px 40px;
            font-size: 16px;
            border-radius: 4px;
            cursor: pointer;
            width: 100%;
        }}
        .btn-pay:hover {{ background: #248a3d; }}
        .transaction-id {{ font-size: 12px; color: #999; margin-top: 20px; }}
    </style>
</head>
<body>
    <div class="checkout-container">
        <h1>Paari Checkout</h1>
        <div class="amount">{currency} {amount_paise / 100:.2f}</div>
        <div class="description">Complete your payment securely via Razorpay</div>
        <button class="btn-pay" id="rzp-button">Pay Now</button>
        <div class="transaction-id">Transaction: {row.display_id or row.id}</div>
    </div>

    <script>
        var options = {{
            "key": "{razorpay_key}",
            "amount": {amount_paise},
            "currency": "{currency}",
            "name": "Paari Demo Store",
            "description": "Order payment for transaction {row.display_id or row.id}",
            "order_id": "{order_id}",
            "handler": async function (response) {{
                try {{
                    const verifyRes = await fetch('/payments/verify', {{
                        method: 'POST',
                        headers: {{ 'Content-Type': 'application/json' }},
                        body: JSON.stringify({{
                            transaction_id: '{row.display_id or row.id}',
                            razorpay_payment_id: response.razorpay_payment_id,
                            razorpay_order_id: response.razorpay_order_id,
                            razorpay_signature: response.razorpay_signature
                        }})
                    }});
                    const data = await verifyRes.json();
                    if (data.success) {{
                        document.body.innerHTML = '<div class="checkout-container"><h1>Payment Successful!</h1><p>Your payment has been verified.</p><p>Order ID: ' + response.razorpay_order_id + '</p></div>';
                    }} else {{
                        alert('Payment verification failed: ' + (data.reason || 'unknown error'));
                    }}
                }} catch (err) {{
                    alert('Payment verification error: ' + err.message);
                }}
            }},
            "modal": {{
                "ondismiss": function() {{
                    console.log('Checkout closed');
                }}
            }}
        }};

        var rzp = new Razorpay(options);
        document.getElementById('rzp-button').onclick = function(e) {{
            rzp.open();
            e.preventDefault();
        }};
    </script>
</body>
</html>
        """

        return HTMLResponse(content=html_content.strip())


@router.post("/{transaction_id}/order", response_model=CreateOrderResponse)
async def create_checkout_order(
    transaction_id: str,
    req: CreateOrderRequest,
) -> CreateOrderResponse:
    """Create a Razorpay order for the checkout page.

    This endpoint is called by the checkout page to create an order
    if one doesn't exist yet.
    """
    service = get_payment_service()

    try:
        result = await service.create_razorpay_order(transaction_id, req.session_id)

        if not result.success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.reason,
            )

        from sqlalchemy import text
        from paari.db.engine import get_session_maker

        maker = get_session_maker()
        async with maker() as session:
            row = (
                await session.execute(
                    text("SELECT amount_paise, currency FROM transactions WHERE id = :x OR display_id = :x"),
                    {"x": transaction_id},
                )
            ).first()
            amount_paise = int(row.amount_paise) if row else 0
            currency = row.currency if row else "INR"

        return CreateOrderResponse(
            order_id=result.order_id,
            amount_paise=amount_paise,
            currency=currency,
            key_id=settings.razorpay_key_id or "rzp_test_demo",
        )

    except HTTPException:
        raise
    except Exception as exc:
        _log.error("Order creation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"order_creation_failed: {exc}",
        )
