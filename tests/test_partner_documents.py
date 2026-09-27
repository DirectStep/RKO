from datetime import datetime
from types import SimpleNamespace

import pytest

from app.bot.handlers import accept_partner_document


class FakeSession:
    def __init__(self, partner):
        self.partner = partner

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    def begin(self):
        return self

    async def scalar(self, _query):
        return self.partner


@pytest.mark.asyncio
async def test_partner_confirms_offer_and_pdn_independently() -> None:
    partner = SimpleNamespace(
        offer_accepted_at=None,
        offer_accepted_version=None,
        pdn_consented_at=None,
        pdn_consent_version=None,
    )
    session = FakeSession(partner)
    database = SimpleNamespace(session=lambda: session)
    answers = []

    async def answer(text, **_kwargs):
        answers.append(text)

    callback = SimpleNamespace(
        from_user=SimpleNamespace(id=123),
        data="partner:accept_offer",
        message=None,
        answer=answer,
    )
    await accept_partner_document(callback, database)

    assert isinstance(partner.offer_accepted_at, datetime)
    assert partner.offer_accepted_version == "27.09.2026"
    assert partner.pdn_consented_at is None
    accepted_at = partner.offer_accepted_at

    await accept_partner_document(callback, database)
    assert partner.offer_accepted_at == accepted_at

    partner.offer_accepted_version = "01.01.2025"
    await accept_partner_document(callback, database)
    assert partner.offer_accepted_version == "27.09.2026"
    assert partner.offer_accepted_at >= accepted_at

    callback.data = "partner:consent_pdn"
    await accept_partner_document(callback, database)

    assert isinstance(partner.pdn_consented_at, datetime)
    assert partner.pdn_consent_version == "20.09.2026"
    assert answers == [
        "Принятие оферты сохранено",
        "Принятие оферты сохранено",
        "Принятие оферты сохранено",
        "Согласие на обработку ПДн сохранено",
    ]
