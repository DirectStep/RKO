import hashlib
import hmac
import json
import time
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlencode

import pytest

from app.domain.enums import (
    BankExternalStatus,
    BankInternalStatus,
    LeadInternalStatus,
    PaymentStatus,
    UserRole,
)
from app.web import (
    CLIENT_STATUS_LABELS,
    build_mini_app_html,
    lead_bank_sort_key,
    lead_cabinet_metrics,
    public_referral_links,
    serialize_lead_bank,
    telegram_contact_url,
    validate_telegram_init_data,
    validate_telegram_init_data_with_tokens,
)

ASSETS_DIR = Path(__file__).parents[1] / "app" / "web_assets"
DOCUMENTS_DIR = Path(__file__).parents[1] / "app" / "documents"


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


def test_secondary_bot_init_data_is_accepted() -> None:
    now = int(time.time())
    raw_data = signed_init_data("654321:secondary-token", 1781530480, now)

    user = validate_telegram_init_data_with_tokens(
        raw_data,
        ("123456:primary-token", "654321:secondary-token"),
    )

    assert user["id"] == 1781530480


def test_lead_expected_payout_decreases_only_after_payment() -> None:
    unpaid = None
    paid = SimpleNamespace(
        external_status=BankExternalStatus.OPENED,
        lead_reward_estimate=Decimal("3000"),
        lead_reward_fact=Decimal("2500"),
        lead_reward_paid_at=object(),
    )
    banks = [
        SimpleNamespace(
            external_status=BankExternalStatus.PLANNED,
            lead_reward_estimate=Decimal("1000"),
            lead_reward_fact=None,
            lead_reward_paid_at=unpaid,
        ),
        SimpleNamespace(
            external_status=BankExternalStatus.IN_PROGRESS,
            lead_reward_estimate=Decimal("2000"),
            lead_reward_fact=None,
            lead_reward_paid_at=unpaid,
        ),
        SimpleNamespace(
            external_status=BankExternalStatus.OPENED,
            lead_reward_estimate=Decimal("5000"),
            lead_reward_fact=None,
            lead_reward_paid_at=unpaid,
        ),
        paid,
    ]

    metrics = lead_cabinet_metrics(banks)

    assert metrics == {
        "planned_accounts": 2,
        "activated_accounts": 2,
        "expected_payout": Decimal("8000"),
        "paid_total": Decimal("2500"),
    }


def test_expired_telegram_init_data_is_rejected() -> None:
    raw_data = signed_init_data("123456:test-token", 1781530480, 1)

    with pytest.raises(ValueError, match="устарела"):
        validate_telegram_init_data(raw_data, "123456:test-token")


def test_hidden_navigation_tabs_stay_hidden() -> None:
    styles = (ASSETS_DIR / "styles.css").read_text(encoding="utf-8")

    assert ".tabbar button[hidden] { display: none; }" in styles


def test_list_row_subtitle_does_not_overlap_trailing_action() -> None:
    styles = (ASSETS_DIR / "styles.css").read_text(encoding="utf-8")

    assert "grid-template-columns: 2.75rem minmax(0, 1fr) auto;" in styles
    assert ".row-subtitle { display: block; overflow: hidden; max-width: 100%;" in styles
    assert "text-overflow: ellipsis; white-space: nowrap;" in styles


def test_partner_channel_controls_are_present() -> None:
    markup = (ASSETS_DIR / "index.html").read_text(encoding="utf-8")
    script = (ASSETS_DIR / "app.js").read_text(encoding="utf-8")

    assert 'id="add-channel-button"' in markup
    assert "state.session.role==='partner'?api('/api/channels')" not in script
    assert "['admin','partner'].includes(state.session.role)?'/api/channels':null" in script
    assert "method:'POST'" in script and "api('/api/channels'" in script
    assert 'class="contact-row channel-link-row" data-channel=' in script
    assert "bindReferralLinkCopies(channel)" in script
    assert 'id="remove-channel"' in script


def test_admin_partner_activation_and_lead_filters_are_present() -> None:
    markup = (ASSETS_DIR / "index.html").read_text(encoding="utf-8")
    script = (ASSETS_DIR / "app.js").read_text(encoding="utf-8")

    for control_id in (
        "admin-filters",
        "admin-partner",
        "admin-channel",
        "admin-period",
        "admin-date-from",
        "admin-date-to",
        "admin-lead-status",
        "admin-payment-status",
    ):
        assert f'id="{control_id}"' in markup
    assert "function renderAdminFilters" in script
    assert "function filteredLeads" in script
    assert "/activation-link" in script
    assert "referralLinkRows(result)" in script
    assert "bindReferralLinkCopies(result)" in script


def test_channels_show_only_the_new_bot_referral_link() -> None:
    script = (ASSETS_DIR / "app.js").read_text(encoding="utf-8")

    assert "function referralLinks(item)" in script
    assert "function referralLinkRows(item)" in script
    assert "data-copy-referral-link" in script

    links = public_referral_links(("RKOrko_bot", "RKollega_bot"), "channel-code")
    assert links == [
        {
            "bot": "@RKollega_bot",
            "url": "https://t.me/RKollega_bot?start=channel-code",
        }
    ]


def test_admin_can_delete_one_application_from_mini_app() -> None:
    script = (ASSETS_DIR / "app.js").read_text(encoding="utf-8")

    assert 'id="show-delete-lead"' in script
    assert 'id="delete-lead-confirm"' in script
    assert "method:'DELETE'" in script
    assert "Telegram-аккаунт клиента и другие его заявки останутся" in script


def test_online_badge_content_is_centered() -> None:
    styles = (ASSETS_DIR / "styles.css").read_text(encoding="utf-8")

    assert ".online-badge { display: flex; align-items: center;" in styles
    assert "line-height: 1; white-space: nowrap;" in styles
    assert (
        '.online-badge button, .online-badge [role="button"] { display: grid; flex: none;'
    ) in styles


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


def test_partner_summary_uses_clear_application_and_payment_metrics() -> None:
    markup = (ASSETS_DIR / "index.html").read_text(encoding="utf-8")
    script = (ASSETS_DIR / "app.js").read_text(encoding="utf-8")

    for label in (
        "Ожидаемая выплата",
        "Последняя выплата",
        "Выплачено всего",
        "Завершённые заявки",
        "Отменённые заявки",
    ):
        assert label in markup
    for label in (
        "Всего заявок",
        "Новые заявки",
        "Заявки в работе",
        "Счета в процессе открытия",
        "Активированные счета",
    ):
        assert label in script
    assert "metrics.last_payout" in script
    assert "metrics.cancelled" in script
    assert "Подтверждено к выплате" not in markup
    assert "Конверсия" not in markup


def test_lead_cabinet_has_separate_read_only_sections() -> None:
    markup = (ASSETS_DIR / "index.html").read_text(encoding="utf-8")
    script = (ASSETS_DIR / "app.js").read_text(encoding="utf-8")

    assert 'id="client-application-screen"' in markup
    assert 'id="client-banks-screen"' in markup
    assert "state.session.role==='lead'" in script
    assert "api('/api/lead/application')" in script
    assert "api('/api/lead/banks')" in script
    assert "renderLeadCabinet();return" in script
    assert "leadPayout(item)" in script
    assert "lead_payout_paid_separately" in script
    assert "`до ${value}`" in script
    assert "item.online_available" in script
    assert "const infoIcon=" in script
    assert "${infoIcon}</button>" in script
    assert "Добавить ещё" in markup
    assert "is-unselected" in script
    assert "Планируется счетов" in script
    assert "Активированных счетов" in script
    assert "data-confirm-lead-payment" in script
    assert (
        "<span>Номер</span>"
        not in script.split("function renderLeadCabinet", 1)[1].split(
            "function confirmLeadBankSelection", 1
        )[0]
    )
    activation_info = markup.index('id="activation-info"')
    add_more = markup.index('id="add-more-banks"')
    bank_list = markup.index('id="client-banks-list"')
    assert activation_info < add_more < bank_list


def test_manager_dashboard_and_queue_are_simplified() -> None:
    markup = (ASSETS_DIR / "index.html").read_text(encoding="utf-8")
    script = (ASSETS_DIR / "app.js").read_text(encoding="utf-8")

    scope = markup.split('id="lead-scope"', 1)[1].split("</select>", 1)[0]
    assert ">Новые</option>" in scope
    assert ">В работе</option>" in scope
    assert "Только мои" not in scope
    assert "Все заявки" not in scope
    assert "state.session.role==='manager'&&index>1" in script
    assert "document.querySelector('#banks-tab').hidden=!admin" in script
    assert "style.setProperty('--tab-count',admin?5:3)" in script


def test_team_has_direct_telegram_chat_action() -> None:
    script = (ASSETS_DIR / "app.js").read_text(encoding="utf-8")

    assert 'class="staff-chat"' in script
    assert 'data-telegram-chat="https://t.me/${esc(username)}"' in script
    assert "tg?.openTelegramLink" in script
    assert 'class="staff-toggle"' in script


def test_admin_can_assign_active_or_pending_support_manager() -> None:
    script = (ASSETS_DIR / "app.js").read_text(encoding="utf-8")

    assert "item.role==='manager'" in script
    assert "['active','pending'].includes(item.status)" in script
    assert 'id="lead-manager"' in script
    assert 'id="save-lead-manager"' in script
    assert "manager_id:managerId,update_manager:true" in script


def test_new_leads_use_anutka_as_default_support_manager() -> None:
    intake = (ASSETS_DIR.parent / "services" / "lead_intake.py").read_text(encoding="utf-8")

    assert 'DEFAULT_SUPPORT_MANAGER_USERNAME = "anutka_rko"' in intake
    assert "default_manager_id = await self._default_support_manager_id(session)" in intake
    assert "manager_id=default_manager_id" in intake
    assert "len(managers) != 1" in intake
    assert "manager.role is not UserRole.MANAGER" in intake
    assert "manager.access_status is not AccessStatus.ACTIVE" in intake


def test_direct_leads_use_xirass_as_primary_admin() -> None:
    intake = (ASSETS_DIR.parent / "services" / "lead_intake.py").read_text(encoding="utf-8")

    assert 'DEFAULT_DIRECT_ADMIN_USERNAME = "xirass"' in intake
    assert "primary_admin_id = await self._default_direct_admin_id(session)" in intake
    assert "admin.role is not UserRole.ADMIN" in intake
    assert "admin.access_status is not AccessStatus.ACTIVE" in intake


def test_ineligible_leads_are_notified_and_highlighted_for_staff() -> None:
    handlers = (ASSETS_DIR.parent / "bot" / "handlers.py").read_text(encoding="utf-8")
    script = (ASSETS_DIR / "app.js").read_text(encoding="utf-8")
    styles = (ASSETS_DIR / "styles.css").read_text(encoding="utf-8")

    assert "if result.lead_id is not None:" in handlers
    assert "🔴 НЕ ПОДХОДИТ ПО УСЛОВИЯМ АНКЕТЫ" in handlers
    assert "lead.workflow_stage==='not_eligible'" in script
    assert "is-not-eligible" in script
    assert "button.list-row.is-not-eligible" in styles


def test_lead_sees_admin_before_manager_and_manager_only_after_bank_selection() -> None:
    backend = (ASSETS_DIR.parent / "web.py").read_text(encoding="utf-8")
    script = (ASSETS_DIR / "app.js").read_text(encoding="utf-8")

    assert "lead.bank_selection_submitted_at is not None" in backend
    assert '"admin_url"' in backend
    assert '"manager_url"' in backend
    assert "<small>Администратор</small>" in script
    assert "<small>Персональный менеджер</small>" in script
    assert "${admin}${manager}" in script

    assert telegram_contact_url(SimpleNamespace(telegram_username="xirasS", telegram_id="1")) == (
        "https://t.me/xirasS"
    )
    assert telegram_contact_url(SimpleNamespace(telegram_username=None, telegram_id="123")) == (
        "tg://user?id=123"
    )


def test_partner_paid_total_is_the_first_full_width_metric() -> None:
    markup = (ASSETS_DIR / "index.html").read_text(encoding="utf-8")

    paid = markup.index('class="metric-wide"><span>Выплачено всего')
    expected = markup.index("Ожидаемая выплата")
    last = markup.index("Последняя выплата")
    assert paid < expected < last


def test_financial_fields_are_split_by_role_in_mini_app() -> None:
    markup = (ASSETS_DIR / "index.html").read_text(encoding="utf-8")
    script = (ASSETS_DIR / "app.js").read_text(encoding="utf-8")

    assert 'data-sheet-link="bank_conditions_sheet_url"' in markup
    assert 'data-sheet-link="bank_rates_sheet_url"' in markup
    assert "Выплата клиенту" in script
    assert "Выплата партнёру" in script
    assert "Командная прибыль" in script
    assert "const economics=admin?" in script


def test_activation_condition_is_read_only_in_bank_editor() -> None:
    script = (ASSETS_DIR / "app.js").read_text(encoding="utf-8")

    assert 'id="catalog-condition"' not in script
    assert "activation_condition:" not in script
    assert "Условие активации берётся из Google Sheets" in script


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
        lead_reward_paid_at=None,
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
    assert partner["lead_reward_estimate"] == "300"
    assert "team_profit_estimate" not in partner
    assert "lead_reward_estimate" not in manager
    assert "reward_estimate" not in manager
    assert "income_estimate" not in manager
    assert "team_profit_estimate" not in manager
    assert admin["team_profit_estimate"] == "600"


def test_bank_selection_is_one_step_and_supports_multiple_banks() -> None:
    script = (ASSETS_DIR / "app.js").read_text(encoding="utf-8")
    backend = (ASSETS_DIR.parent / "web.py").read_text(encoding="utf-8")

    assert "/claim-admin" not in script
    assert "/banks/publish" not in script
    assert '"/api/leads/{lead_id}/claim-admin"' not in backend
    assert '"/api/leads/{lead_id}/banks/publish"' not in backend
    assert "api('/api/lead/banks/selection'" in script
    assert "/claim-manager" in script
    assert "Отправить менеджеру" in script
    assert "bank_ids" in script
    assert "Добавить и показать клиенту" in script


def test_manager_queue_moves_to_work_only_when_application_is_opened() -> None:
    script = (ASSETS_DIR / "app.js").read_text(encoding="utf-8")
    backend = (ASSETS_DIR.parent / "web.py").read_text(encoding="utf-8")
    workflow = (ASSETS_DIR.parent / "services" / "lead_workflow.py").read_text(encoding="utf-8")

    assert "lead.workflow_stage = LeadWorkflowStage.AWAITING_MANAGER" in workflow
    assert "lead.manager_id is not None and lead.manager_id != actor_id" in workflow
    assert "Lead.manager_started_at.is_(None)" in backend
    assert "Lead.manager_started_at.is_not(None)" in backend
    assert "await notify_manager_new_lead(lead, manager)" in backend
    assert "lead.manager_started?'В работе':'Новая'" in script
    assert "managerRole&&!lead.manager_started&&lead.is_assigned_manager" in script
    assert "await api(`/api/leads/${lead.id}/claim-manager`" in script
    assert "state.leadScope='mine'" in script
    assert "document.querySelector('#lead-scope').value='mine'" in script


def test_admin_cannot_change_source_and_can_review_duplicates() -> None:
    markup = (ASSETS_DIR / "index.html").read_text(encoding="utf-8")
    script = (ASSETS_DIR / "app.js").read_text(encoding="utf-8")

    assert 'id="open-duplicate-reviews"' in markup
    assert "state.session.role==='admin'?'/api/duplicate-reviews':null" in script
    assert "/resolve" in script
    assert "confirmSourceChange" not in script
    assert "change-source" not in script
    assert "/source/direct" not in script
    assert "Источник требует проверки" in markup


def test_partner_does_not_see_lead_telegram_username() -> None:
    script = (ASSETS_DIR / "app.js").read_text(encoding="utf-8")

    assert "Telegram клиента" not in script
    assert "Имя или номер заявки" in script


def test_admin_contact_actions_copy_phone_and_email() -> None:
    script = (ASSETS_DIR / "app.js").read_text(encoding="utf-8")

    assert "data-copy-contact=\"${encodeURIComponent(String(lead.phone||''))}\"" in script
    assert 'data-copy-contact="${encodeURIComponent(String(lead.email))}"' in script
    assert (
        "await copyText(decodeURIComponent(copyContact.dataset.copyContact),'Скопировано')"
        in script
    )
    assert "<b>Позвонить</b>" not in script
    assert 'data-contact-link="tel:' not in script
    assert 'data-contact-link="mailto:' not in script


def test_partner_bank_progress_summary_is_present() -> None:
    script = (ASSETS_DIR / "app.js").read_text(encoding="utf-8")

    assert "Запланировано / в работе / открыто" in script


def test_partner_creates_one_referral_link() -> None:
    script = (ASSETS_DIR / "app.js").read_text(encoding="utf-8")

    assert 'id="create-channel">Создать ссылку</button>' in script
    assert 'id="create-channel">Создать ссылки</button>' not in script


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

    assert "request.timeout=10000" in script
    assert "new XMLHttpRequest()" in script
    assert "const attempts=(options.method||'GET').toUpperCase()==='GET'?2:1" in script
    assert "Сервер отвечает слишком долго" in script
    assert "const [dashboard,loadedLeads]=await Promise.all" in script
    assert "api('/api/dashboard')" in script
    assert "api(`/api/leads" in script
    assert "Object.assign(state,{dashboard,leads});render()" in script
    assert "await Promise.all(optional.map" in script
    assert "state.banksLoading=employee" in script


def test_online_help_text_is_aligned_to_the_bottom_everywhere() -> None:
    styles = (ASSETS_DIR / "styles.css").read_text(encoding="utf-8")
    script = (ASSETS_DIR / "app.js").read_text(encoding="utf-8")

    assert 'class="detail-section online-help-content"' in script
    assert ".online-help-content { display: flex; align-items: flex-end;" in styles
    assert ".online-help-content .info-copy { width: 100%; padding-top: 1rem; }" in styles


def test_every_internal_status_has_a_client_notification_label() -> None:
    assert set(CLIENT_STATUS_LABELS) == set(LeadInternalStatus)
    assert CLIENT_STATUS_LABELS[LeadInternalStatus.SELECTING_BANKS] == "Выберите банки"
    assert CLIENT_STATUS_LABELS[LeadInternalStatus.COMPLETED] == "Заявка завершена"

    source = (ASSETS_DIR.parent / "web.py").read_text(encoding="utf-8")
    assert "previous_internal_status != lead.internal_status" in source
    assert "Статус вашей заявки изменён" in source
    assert "await notify_client_status(lead.id, lead.internal_status)" in source
    assert "previous_internal_status != current_internal_status" in source
    assert "await notify_client_status(lead_id, current_internal_status)" in source


def test_telegram_sdk_does_not_block_application_startup() -> None:
    markup = (ASSETS_DIR / "index.html").read_text(encoding="utf-8")
    script = (ASSETS_DIR / "app.js").read_text(encoding="utf-8")

    assert 'telegram-web-app.js?59" async' in markup
    assert 'app.js?v=20260829-01" data-inline="app"></script>' in markup
    assert markup.index('window.addEventListener("error"') < markup.index('data-inline="app"')
    assert "await waitForTelegramContext()" in script
    assert "Загружаем справочник банков" in script
    assert "await Promise.all(optional.map" in script
    assert "get('tgWebAppData')" in script
    assert "'X-Telegram-Init-Data':telegramInitData()" in script


def test_mini_app_is_delivered_without_separate_local_assets() -> None:
    markup = build_mini_app_html()

    assert '<script src="/assets/app.js' not in markup
    assert '<link rel="stylesheet" href="/assets/styles.css' not in markup
    assert "new XMLHttpRequest()" in markup
    assert ".app-shell" in markup


def test_public_consent_documents_are_packaged_as_pdf() -> None:
    consent = DOCUMENTS_DIR / "soglasie-pdn.pdf"
    policy = DOCUMENTS_DIR / "politika-pdn.pdf"

    assert consent.read_bytes().startswith(b"%PDF-")
    assert policy.read_bytes().startswith(b"%PDF-")


def test_public_documents_use_short_cache_lifetime() -> None:
    source = (Path(__file__).parents[1] / "app" / "web.py").read_text(encoding="utf-8")

    assert 'request.url.path.startswith("/documents/")' in source
    assert 'response.headers["Cache-Control"] = "public, max-age=300"' in source


def test_client_faq_does_not_include_legality_question() -> None:
    markup = (ASSETS_DIR / "index.html").read_text(encoding="utf-8")

    assert "Легально ли это?" not in markup


def test_unfinished_lead_draft_gets_questionnaire_hint() -> None:
    source = (Path(__file__).parents[1] / "app" / "web.py").read_text(encoding="utf-8")

    assert "select(LeadDraft).where(LeadDraft.telegram_id == telegram_id)" in source
    assert "Сначала ответьте на вопросы в боте." in source
    assert "кабинет станет доступен." in source


def test_lead_banks_are_sorted_by_activation_then_payout() -> None:
    banks = [
        {
            "bank": "Оборот большой",
            "action_text": "Сделать оборот",
            "lead_payout": "5000",
            "order": 1,
        },
        {
            "bank": "Тариф дешевле",
            "action_text": "Оплатить тариф",
            "lead_payout": "1000",
            "order": 2,
        },
        {
            "bank": "Открытие меньше",
            "action_text": "Открыть счёт",
            "lead_payout": "700",
            "order": 3,
        },
        {
            "bank": "Холд",
            "action_text": "Удерживать сумму 4 дня",
            "lead_payout": "1500",
            "order": 4,
        },
        {
            "bank": "Открытие больше",
            "action_text": "Открытие счёта",
            "lead_payout": "1700",
            "order": 5,
        },
        {"bank": "Без условия", "action_text": "", "lead_payout": "9000", "order": 6},
    ]

    ordered = sorted(banks, key=lead_bank_sort_key)

    assert [bank["bank"] for bank in ordered] == [
        "Открытие больше",
        "Открытие меньше",
        "Тариф дешевле",
        "Холд",
        "Оборот большой",
        "Без условия",
    ]
