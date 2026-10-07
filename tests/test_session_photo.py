import hashlib
import hmac
import json
import time
from unittest.mock import AsyncMock
from urllib.parse import urlencode
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.domain.enums import UserRole
from app.web import MiniAppUser, create_web_app


@pytest.mark.parametrize("photo", ["https://t.me/i/userpic/test.jpg", "", "javascript:alert(1)"])
async def test_session_returns_only_https_photo_from_signed_telegram_user(monkeypatch, photo):
    token = "123456:test-token"
    values = {
        "auth_date": str(int(time.time())),
        "user": json.dumps({"id": 100, "first_name": "Test", "photo_url": photo}),
    }
    data = "\n".join(f"{key}={value}" for key, value in sorted(values.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    values["hash"] = hmac.new(secret, data.encode(), hashlib.sha256).hexdigest()
    monkeypatch.setattr("app.web.observe_telegram_profile", AsyncMock())
    app = create_web_app(database=None, settings=Settings(bot_token=token))
    route = next(route for route in app.routes if getattr(route, "path", "") == "/api/session")
    app.dependency_overrides[route.dependant.dependencies[0].call] = lambda: MiniAppUser(
        id="100",
        database_id=uuid4(),
        name="Test",
        role=UserRole.ADMIN,
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/session", headers={"X-Telegram-Init-Data": urlencode(values)}
        )
    assert response.status_code == 200
    assert response.json()["photo_url"] == (photo if photo.startswith("https://") else "")
