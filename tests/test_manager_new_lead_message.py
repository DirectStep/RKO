from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from httpx import ASGITransport, AsyncClient

from app.bot.texts import manager_new_lead_message
from app.config import Settings
from app.domain.enums import AccessStatus, LeadWorkflowStage, UserRole
from app.web import MiniAppUser, create_web_app


def test_manager_message_escapes_client_data_and_uses_requested_emoji() -> None:
    text = manager_new_lead_message('RKO-0042', '<Иван> & сын', '@client', '+79990000000', '@admin')
    assert '<code>RKO-0042</code>' in text
    assert '<blockquote>&lt;Иван&gt; &amp; сын</blockquote>' in text
    assert '<blockquote>@client</blockquote>' in text
    assert '<blockquote>@admin</blockquote>' in text
    assert text.count('<blockquote>') == text.count('</blockquote>') == 5
    assert text.count('<tg-emoji ') == text.count('</tg-emoji>') == 6
    for emoji_id in ('5244927342190541585', '5244634919342192985', '5226831738734400762',
                     '5188234920639632382', '5206357006864113601', '5188463524568926712'):
        assert f'emoji-id="{emoji_id}"' in text
    assert 'группу с лидом и ркошником' in text
    assert '<b>(улица и номер дома и ИНН)</b>' in text
    assert '<blockquote>Не указан</blockquote>' in manager_new_lead_message('RKO-1', 'Иван', None, '123', 'Не назначен')


async def test_bank_submission_sends_html_message_with_primary_admin(monkeypatch) -> None:
    lead_id, manager_id, admin_id = uuid4(), uuid4(), uuid4()
    lead = SimpleNamespace(
        id=lead_id, manager_id=manager_id, primary_admin_id=admin_id,
        short_id='RKO-0042', display_name='Иван <Тест>', telegram_username='client',
        phone='+79990000000', workflow_stage=LeadWorkflowStage.AWAITING_MANAGER,
    )
    manager = SimpleNamespace(id=manager_id, telegram_id='200', telegram_username='manager', access_status=AccessStatus.ACTIVE)
    admin = SimpleNamespace(telegram_username='primary_admin', telegram_id='300')
    async def get_user(model, user_id):
        return {manager_id: manager, admin_id: admin}[user_id]
    session = SimpleNamespace(
        get=AsyncMock(side_effect=get_user),
        scalar=AsyncMock(side_effect=[LeadWorkflowStage.AWAITING_CLIENT_SELECTION, '100']),
    )
    @asynccontextmanager
    async def database_session():
        yield session
    monkeypatch.setattr('app.web.LeadWorkflowService.submit_bank_selection', AsyncMock(return_value=lead))
    bot = SimpleNamespace(id=1, send_message=AsyncMock())
    app = create_web_app(database=SimpleNamespace(session=database_session), settings=Settings(), bot=bot)
    route = next(r for r in app.routes if getattr(r, 'path', '') == '/api/lead/banks/selection')
    app.dependency_overrides[route.dependant.dependencies[0].call] = lambda: MiniAppUser(
        id='100', database_id=None, name='Иван', role=UserRole.LEAD, lead_id=lead_id,
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        response = await client.post('/api/lead/banks/selection', json={'bank_ids': [str(uuid4())]})
    assert response.status_code == 200
    call = bot.send_message.await_args_list[0].kwargs
    assert call['chat_id'] == 200
    assert call['parse_mode'] == 'HTML'
    assert call['text'] == manager_new_lead_message('RKO-0042', 'Иван <Тест>', 'client', '+79990000000', '@primary_admin')
    assert call['reply_markup'].inline_keyboard[0][0].callback_data.endswith(str(lead_id))
