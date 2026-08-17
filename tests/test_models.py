from app.models import User


def test_user_defaults() -> None:
    user = User(telegram_id="123456789")

    assert user.telegram_id == "123456789"
    assert User.__tablename__ == "users"
    assert User.__table__.c.role.default.arg == "lead"
    assert User.__table__.c.access_status.default.arg == "active"
