import hashlib
import hmac
import json
import time
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlencode

import pytest

from app.domain.enums import BankExternalStatus, BankInternalStatus, PaymentStatus, UserRole
from app.web import serialize_lead_bank, validate_telegram_init_data

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
    assert "['admin','partner'].includes(state.session.role)?'/api/channels':null" in script
    assert "method:'POST'" in script and "api('/api/channels'" in script


def test_partner_cabinet_has_section_seven_controls() -> None:
    markup = (ASSETS_DIR / "index.html").read_text(encoding="utf-8")
    script = (ASSETS_DIR / "app.js").read_text(encoding="utf-8")
    styles = (ASSETS_DIR / "styles.css").read_text(encoding="utf-8")

    for control_id in (
        "partner-summary",
        "partner-period",
        "partner-date-from",
        "partner-date-to",
        "partner-channel",
        "partner-lead-status",
        "partner-payment-status",
        "partner-report",
        "partner-contact",
    ):
        assert f'id="{control_id}"' in markup
    assert "api(`/api/partner/cabinet?${partnerQuery()}`)" in script
    assert "/api/partner/report.xlsx" in script
    assert "function openPartnerLead" in script
    assert ".scope-filter[hidden] { display: none; }" in styles


def test_lead_cabinet_has_separate_read_only_sections() -> None:
    markup = (ASSETS_DIR / "index.html").read_text(encoding="utf-8")
    script = (ASSETS_DIR / "app.js").read_text(encoding="utf-8")

    assert 'id="client-application-screen"' in markup
    assert 'id="client-banks-screen"' in markup
    assert "state.session.role==='lead'" in script
    assert "api('/api/lead/application')" in script
    assert "api('/api/lead/banks')" in script
    assert "renderLeadCabinet();return" in script
    assert "money(item.lead_payout)" in script
    assert "item.online_text" in script


def test_financial_fields_are_split_by_role_in_mini_app() -> None:
    markup = (ASSETS_DIR / "index.html").read_text(encoding="utf-8")
    script = (ASSETS_DIR / "app.js").read_text(encoding="utf-8")

    assert 'data-sheet-link="bank_conditions_sheet_url"' in markup
    assert 'data-sheet-link="bank_rates_sheet_url"' in markup
    assert "Выплата лиду" in script
    assert "Выплата партнёру" in script
    assert "Командная прибыль" in script
    assert 'admin?`<div class="value-row"><span>Командная прибыль' in script


def test_partner_api_does_not_receive_internal_financial_fields() -> None:
    lead_bank = SimpleNamespace(
        id="lead-bank",
        internal_status=BankInternalStatus.PLANNED,
        external_status=BankExternalStatus.PLANNED,
        opened_at=None,
        partner_reward_estimate=100,
        partner_reward_fact=None,
        bank_income_estimate=1000,
        bank_income_fact=None,
        partner_percent_snapshot=10,
        close_reason=None,
        offered_to_lead=True,
        selected_by_lead=True,
        lead_reward_estimate=300,
        lead_reward_fact=None,
        lead_reward_paid_separately=False,
        team_profit_estimate=600,
        team_profit_fact=None,
    )
    bank = SimpleNamespace(id="bank", name="Банк")
    rate = SimpleNamespace(online_text="Да")

    partner = serialize_lead_bank(lead_bank, bank, None, UserRole.PARTNER, rate)
    manager = serialize_lead_bank(lead_bank, bank, None, UserRole.MANAGER, rate)
    admin = serialize_lead_bank(lead_bank, bank, None, UserRole.ADMIN, rate)

    assert partner["payment_status"] == PaymentStatus.NOT_CALCULATED.value
    assert "income_estimate" not in partner
    assert "lead_reward_estimate" not in partner
    assert "team_profit_estimate" not in partner
    assert manager["lead_reward_estimate"] == "300"
    assert "team_profit_estimate" not in manager
    assert admin["team_profit_estimate"] == "600"


def test_two_stage_claim_and_client_bank_selection_controls_are_present() -> None:
    script = (ASSETS_DIR / "app.js").read_text(encoding="utf-8")

    assert "/claim-admin" in script
    assert "/banks/publish" in script
    assert "api('/api/lead/banks/selection'" in script
    assert "/claim-manager" in script
    assert "Отправить менеджеру" in script


def test_admin_can_confirm_sources_and_review_duplicates() -> None:
    markup = (ASSETS_DIR / "index.html").read_text(encoding="utf-8")
    script = (ASSETS_DIR / "app.js").read_text(encoding="utf-8")

    assert 'id="open-duplicate-reviews"' in markup
    assert "state.session.role==='admin'?'/api/duplicate-reviews':null" in script
    assert "/resolve" in script
    assert "confirmSourceChange" in script
    assert "Источник требует проверки" in markup


def test_mini_app_has_visible_loading_state() -> None:
    markup = (ASSETS_DIR / "index.html").read_text(encoding="utf-8")
    styles = (ASSETS_DIR / "styles.css").read_text(encoding="utf-8")

    assert 'id="loading-state"' in markup
    assert ".loading-spinner" in styles
    assert ".loading-state[hidden], .tabbar[hidden] { display: none; }" in styles


def test_repeat_applications_are_visible_in_summary_and_history() -> None:
    markup = (ASSETS_DIR / "index.html").read_text(encoding="utf-8")
    script = (ASSETS_DIR / "app.js").read_text(encoding="utf-8")

    assert 'id="repeats-count"' in markup
    assert "Повторная · " in script
    assert "Предыдущие заявки" in script
    assert "lead.previous_applications" in script


def test_mini_app_retries_and_loads_optional_sections_in_parallel() -> None:
    script = (ASSETS_DIR / "app.js").read_text(encoding="utf-8")

    assert "controller.abort(),10000" in script
    assert "const attempts=(options.method||'GET').toUpperCase()==='GET'?2:1" in script
    assert "Сервер отвечает слишком долго" in script
    assert "const [dashboard,loadedLeads]=await Promise.all" in script
    assert "api('/api/dashboard')" in script
    assert "api(`/api/leads" in script
    assert "Object.assign(state,{dashboard,leads});render()" in script
    assert "await Promise.all(optional.map" in script
    assert "state.banksLoading=employee" in script


def test_telegram_sdk_does_not_block_application_startup() -> None:
    markup = (ASSETS_DIR / "index.html").read_text(encoding="utf-8")
    script = (ASSETS_DIR / "app.js").read_text(encoding="utf-8")

    assert 'telegram-web-app.js?59" async' in markup
    assert 'app.js?v=20260823-07"></script>' in markup
    assert markup.index('window.addEventListener("error"') < markup.index("/assets/app.js")
    assert "await waitForTelegramContext()" in script
    assert "Загружаем справочник банков" in script
    assert "await Promise.all(optional.map" in script
    assert "get('tgWebAppData')" in script
    assert "'X-Telegram-Init-Data':telegramInitData()" in script
