"""Step 15 validation: merchant dashboard (login, review list, approve/deny)."""

from __future__ import annotations

from httpx import ASGITransport, AsyncClient

from paari.dashboard.session import create_session
from paari.main import app
from paari.review.service import ReviewService


def _service() -> ReviewService:
    """An isolated ReviewService backed by a fresh on-disk SQLite DB."""
    from pathlib import Path
    from uuid import uuid4

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    db_path = Path(__file__).resolve().parent / f"_test_dashboard_{uuid4().hex}.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False, future=True)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    return ReviewService(session_maker=maker, sla_hours=4)


async def test_login_page_renders_without_session() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/dashboard/login")
    assert response.status_code == 200
    assert "Paari" in response.text


async def test_dashboard_requires_session() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/dashboard", follow_redirects=False)
    assert response.status_code == 302
    assert "/dashboard/login" in response.headers["location"]


async def test_dashboard_with_session_lists_reviews() -> None:
    """A logged-in operator sees pending reviews."""
    import paari.api.reviews as reviews_api
    import paari.dashboard.routes as dashboard_routes

    svc = _service()
    original_review = reviews_api.REVIEW
    original_dashboard_review = dashboard_routes.REVIEW
    reviews_api.REVIEW = svc
    dashboard_routes.REVIEW = svc
    try:
        await svc.create(merchant_id="merchant-demo-001", transaction_id="tx-1", triggered_by="POLICY", reason="over limit")
        token = create_session("merchant@demo.local", "merchant-demo-001")

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/dashboard", cookies={"paari_session": token})
        assert response.status_code == 200
        assert "over limit" in response.text
    finally:
        reviews_api.REVIEW = original_review
        dashboard_routes.REVIEW = original_dashboard_review


async def test_login_rejects_bad_credentials() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/dashboard/login",
            data={"email": "no@one.local", "password": "wrong"},
            follow_redirects=False,
        )
    assert response.status_code == 302
    assert "error=invalid" in response.headers["location"]


async def test_login_accepts_valid_credentials() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/dashboard/login",
            data={"email": "merchant@demo.local", "password": "demo"},
            follow_redirects=False,
        )
    assert response.status_code == 302
    assert response.headers["location"] == "/dashboard"
    assert "paari_session" in response.cookies
