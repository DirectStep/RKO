import hashlib
import hmac
import json
import time
from pathlib import Path
from urllib.parse import urlencode

import pytest

from app.web import validate_telegram_init_data

ASSETS_DIR = Path(__file__).parents[1] / "app" / "web_assets"


def signed_init_data(bot_token: str, user_id: int, auth_date: int) -> str:
    values = {
        "auth_date": str(auth_date),
        "query_id": "AAEAAAE",
        "user": json.dumps({"id": user_id, "first_name": "Стёпа"}, separators=(",", ":")),
    }
    data_check_string = "\n".join(f"{key}={values[key]}" for key in sorted(values))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    values["hash"] = hmac.new(secret, data_check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode(values)


def test_valid_telegram_init_data() -> None:
    now = int(time.time())
    raw_data = signed_init_data("123456:test-token", 1781530480, now)

    user = validate_telegram_init_data(raw_data, "123456:test-token")

    assert user["id"] == 1781530480


def test_modified_telegram_init_data_is_rejected() -> None:
    raw_data = signed_init_data("123456:test-token", 1781530480, int(time.time()))

    with pytest.raises(ValueError, match="Telegram"):
        validate_telegram_init_data(
            raw_data.replace("1781530480", "1781530481"), "123456:test-token"
        )


def test_expired_telegram_init_data_is_rejected() -> None:
    raw_data = signed_init_data("123456:test-token", 1781530480, 1)

    with pytest.raises(ValueError, match="устарела"):
        validate_telegram_init_data(raw_data, "123456:test-token")


def test_hidden_navigation_tabs_stay_hidden() -> None:
    styles = (ASSETS_DIR / "styles.css").read_text(encoding="utf-8")

    assert ".tabbar button[hidden] { display: none; }" in styles


def test_partner_channel_controls_are_present() -> None:
    markup = (ASSETS_DIR / "index.html").read_text(encoding="utf-8")
    script = (ASSETS_DIR / "app.js").read_text(encoding="utf-8")

    assert 'id="add-channel-button"' in markup
    assert "state.session.role==='partner'?api('/api/channels')" not in script
    assert "['admin','partner'].includes(state.session.role)?api('/api/channels')" in script
    assert "method:'POST'" in script and "api('/api/channels'" in script
