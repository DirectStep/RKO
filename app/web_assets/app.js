const telegram = window.Telegram?.WebApp
telegram?.ready()
telegram?.expand()

const state = { session: null, dashboard: null, leads: [], partners: [] }
const statusLabels = {
  new: 'Новая', manager_assigned: 'Менеджер назначен', awaiting_first_contact: 'Ждёт звонка',
  contacted: 'Связались', awaiting_data: 'Ждём данные', data_received: 'Данные получены',
  selecting_banks: 'Подбираем банки', preparing_applications: 'Готовим заявки',
  applications_sent: 'Заявки отправлены', opening_accounts: 'Открытие счетов',
  partially_opened: 'Часть счетов открыта', all_planned_opened: 'Счета открыты',
  paused: 'На паузе', no_response: 'Нет ответа', lead_refused: 'Отказ клиента',
  not_eligible: 'Не подходит', completed: 'Завершена'
}

async function api(path) {
  const response = await fetch(path, {
    headers: { 'X-Telegram-Init-Data': telegram?.initData || '' }
  })
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(body.detail || 'Не удалось загрузить данные')
  }
  return response.json()
}

function initials(name) {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map(part => part[0]).join('').toUpperCase()
}

function leadRow(lead) {
  const date = new Intl.DateTimeFormat('ru-RU', { day: '2-digit', month: '2-digit' }).format(new Date(lead.date))
  return `<article class="list-row">
    <div class="row-icon">${initials(lead.name) || 'Р'}</div>
    <div class="row-content">
      <div class="row-title"><strong>${escapeHtml(lead.name)}</strong><time>${date}</time></div>
      <p class="row-subtitle">${escapeHtml(lead.short_id)} · ${escapeHtml(statusLabels[lead.status] || lead.status)}</p>
    </div>
  </article>`
}

function renderLeads(items, target) {
  target.innerHTML = items.length ? items.map(leadRow).join('') : '<p class="empty">Заявок пока нет</p>'
}

function render() {
  document.querySelector('#greeting').textContent = state.session.name
  document.querySelector('#avatar').textContent = initials(state.session.name) || 'Р'
  document.querySelector('#total-count').textContent = state.dashboard.total
  document.querySelector('#new-count').textContent = state.dashboard.new
  document.querySelector('#active-count').textContent = state.dashboard.active
  document.querySelector('#unresolved-count').textContent = state.dashboard.unresolved
  renderLeads(state.leads.slice(0, 5), document.querySelector('#recent-leads'))
  renderLeads(state.leads, document.querySelector('#all-leads'))

  const partnersTab = document.querySelector('#partners-tab')
  partnersTab.hidden = state.session.role !== 'admin'
  const partnersList = document.querySelector('#partners-list')
  partnersList.innerHTML = state.partners.length
    ? state.partners.map(partner => `<article class="list-row">
        <div class="row-icon partner">${initials(partner.name) || 'П'}</div>
        <div class="row-content">
          <div class="row-title"><strong>${escapeHtml(partner.name)}</strong></div>
          <p class="row-subtitle">${partner.commission}% · каналов: ${partner.channels}</p>
        </div>
        <i class="status-dot ${partner.active ? '' : 'off'}" aria-label="${partner.active ? 'Активен' : 'Выключен'}"></i>
      </article>`).join('')
    : '<p class="empty">Партнёров пока нет</p>'
}

async function load() {
  document.querySelector('#error-state').hidden = true
  document.querySelector('.app-shell > main').classList.remove('has-error')
  try {
    state.session = await api('/api/session')
    const requests = [api('/api/dashboard'), api('/api/leads')]
    if (state.session.role === 'admin') requests.push(api('/api/partners'))
    const [dashboard, leads, partners = []] = await Promise.all(requests)
    Object.assign(state, { dashboard, leads, partners })
    render()
  } catch (error) {
    document.querySelectorAll('.screen').forEach(screen => screen.classList.remove('is-active'))
    document.querySelector('#error-message').textContent = error.message
    document.querySelector('#error-state').hidden = false
  }
}

function showScreen(name) {
  document.querySelectorAll('.screen').forEach(screen => screen.classList.toggle('is-active', screen.id === `${name}-screen`))
  document.querySelectorAll('[data-screen]').forEach(button => button.classList.toggle('is-active', button.dataset.screen === name))
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

function escapeHtml(value) {
  const node = document.createElement('span')
  node.textContent = value
  return node.innerHTML
}

document.querySelectorAll('[data-screen]').forEach(button => button.addEventListener('click', () => showScreen(button.dataset.screen)))
document.querySelectorAll('[data-go]').forEach(button => button.addEventListener('click', () => showScreen(button.dataset.go)))
document.querySelector('#lead-search').addEventListener('input', event => {
  const query = event.target.value.trim().toLowerCase()
  const filtered = state.leads.filter(lead => `${lead.name} ${lead.phone} ${lead.short_id}`.toLowerCase().includes(query))
  renderLeads(filtered, document.querySelector('#all-leads'))
})
document.querySelector('#retry-button').addEventListener('click', load)

load()
