const tg = window.Telegram?.WebApp
tg?.ready(); tg?.expand()

const state = { session: null, dashboard: {}, leads: [], partners: [], channels: [], banks: [], staff: [], leadScope: 'all' }
const leadLabels = { new:'Новая',manager_assigned:'Менеджер назначен',awaiting_first_contact:'Ждёт звонка',contacted:'Связались',awaiting_data:'Ждём данные',data_received:'Данные получены',selecting_banks:'Подбираем банки',preparing_applications:'Готовим заявки',applications_sent:'Заявки отправлены',opening_accounts:'Открытие счетов',partially_opened:'Часть счетов открыта',all_planned_opened:'Счета открыты',paused:'На паузе',no_response:'Нет ответа',lead_refused:'Отказ клиента',not_eligible:'Не подходит',completed:'Завершена',in_progress:'В работе',partially_completed:'Частично завершена',closed_without_result:'Закрыта без результата' }
const bankLabels = { planned:'Запланирован',awaiting_data:'Ждём данные',preparing_application:'Готовим заявку',application_sent:'Заявка отправлена',under_review:'На рассмотрении',revision_required:'Нужна доработка',account_opened:'Счёт открыт',bank_rejected:'Отказ банка',client_refused:'Отказ клиента',excluded:'Исключён',in_progress:'В работе',opened:'Открыт',not_opened:'Не открыт',will_not_open:'Не будет открыт' }
const payLabels = { not_calculated:'Не рассчитана',calculated:'Рассчитана',awaiting_confirmation:'Ждёт подтверждения',confirmed:'Подтверждена',in_registry:'В реестре',paid:'Выплачена',cancelled:'Отменена' }

async function api(path, options={}) {
  const response = await fetch(path, { ...options, headers:{ 'Content-Type':'application/json','X-Telegram-Init-Data':tg?.initData||'',...(options.headers||{}) } })
  if (!response.ok) { const body=await response.json().catch(()=>({})); throw new Error(body.detail||'Не удалось выполнить действие') }
  return response.status===204 ? null : response.json()
}
function esc(value){ const n=document.createElement('span'); n.textContent=value??''; return n.innerHTML }
function initials(name){ return String(name||'').split(/\s+/).filter(Boolean).slice(0,2).map(x=>x[0]).join('').toUpperCase() }
function date(value){ return value ? new Intl.DateTimeFormat('ru-RU').format(new Date(value)) : '—' }
function money(value){ return value===null||value===undefined||value==='' ? '—' : `${new Intl.NumberFormat('ru-RU').format(Number(value))} ₽` }
function toast(message){ const el=document.querySelector('#toast'); el.textContent=message; el.hidden=false; clearTimeout(toast.timer); toast.timer=setTimeout(()=>el.hidden=true,2400) }
function openSheet(title, eyebrow, html){ document.querySelector('#sheet-title').textContent=title; document.querySelector('#sheet-eyebrow').textContent=eyebrow; document.querySelector('#sheet-content').innerHTML=html; document.querySelector('#sheet-backdrop').hidden=false; document.querySelector('#bottom-sheet').hidden=false }
function closeSheet(){ document.querySelector('#sheet-backdrop').hidden=true; document.querySelector('#bottom-sheet').hidden=true }

function leadRow(lead){
  const detail=state.session.role==='partner'?lead.username:lead.phone
  return `<button class="list-row" type="button" data-lead="${lead.id}"><span class="row-icon">${initials(lead.name)||'Р'}</span><span class="row-content"><span class="row-title"><strong>${esc(lead.name)}</strong><time>${date(lead.date).slice(0,5)}</time></span><span class="row-subtitle">${esc(lead.short_id)} · ${esc(leadLabels[lead.status]||lead.status)}${detail?` · ${esc(detail)}`:''}</span></span></button>`
}
function renderLeads(items,target){ target.innerHTML=items.length?items.map(leadRow).join(''):'<p class="empty">Заявок пока нет</p>' }
function render(){
  const admin=state.session.role==='admin', employee=admin||state.session.role==='manager'
  document.querySelector('#greeting').textContent=state.session.name
  document.querySelector('#avatar').textContent=initials(state.session.name)||'Р'
  for(const key of ['total','new','active','unresolved']) document.querySelector(`#${key}-count`).textContent=state.dashboard[key]
  renderLeads(state.leads.slice(0,5),document.querySelector('#recent-leads')); renderLeads(state.leads,document.querySelector('#all-leads'))
  document.querySelector('#partners-tab').hidden=!admin; document.querySelector('#banks-tab').hidden=!employee; document.querySelector('#team-tab').hidden=!employee
  document.querySelector('#scope-filter').hidden=state.session.role!=='manager'
  document.querySelector('#add-bank-button').hidden=!admin; document.querySelector('#add-staff-button').hidden=!admin
  document.querySelector('.tabbar').style.setProperty('--tab-count',admin?5:employee?4:2)
  document.querySelector('#partners-list').innerHTML=state.partners.length?state.partners.map(p=>`<button class="list-row" type="button" data-partner="${p.id}"><span class="row-icon partner">${initials(p.name)||'П'}</span><span class="row-content"><span class="row-title"><strong>${esc(p.name)}</strong></span><span class="row-subtitle">${esc(p.commission)}% · каналов: ${p.channels}</span></span><i class="status-dot ${p.active?'':'off'}"></i></button>`).join(''):'<p class="empty">Партнёров пока нет</p>'
  document.querySelector('#banks-list').innerHTML=state.banks.length?state.banks.map(b=>`<button class="list-row" type="button" data-bank="${b.id}"><span class="row-icon">Б</span><span class="row-content"><span class="row-title"><strong>${esc(b.name)}</strong></span><span class="row-subtitle">${b.active?'Можно добавлять в заявки':'Отключён'}</span></span><i class="status-dot ${b.active?'':'off'}"></i></button>`).join(''):'<p class="empty">Добавьте первый банк</p>'
  document.querySelector('#staff-list').innerHTML=state.staff.length?state.staff.map(p=>`<button class="list-row" type="button" data-staff="${p.id}"><span class="row-icon partner">${p.role==='admin'?'А':'М'}</span><span class="row-content"><span class="row-title"><strong>${esc(p.username||p.telegram_id)}</strong></span><span class="row-subtitle">${p.role==='admin'?'Администратор':'Менеджер'} · ${p.status==='active'?'доступ включён':'доступ отключён'}</span></span><i class="status-dot ${p.status==='active'?'':'off'}"></i></button>`).join(''):'<p class="empty">Сотрудников пока нет</p>'
}
async function load(){
  document.querySelector('#error-state').hidden=true
  try{
    state.session=await api('/api/session'); const employee=['admin','manager'].includes(state.session.role)
    const jobs=[api('/api/dashboard'),api(`/api/leads${state.leadScope==='mine'?'?mine=true':''}`),state.session.role==='admin'?api('/api/partners'):[],state.session.role==='admin'?api('/api/channels'):[],employee?api('/api/banks'):[],employee?api('/api/staff'):[]]
    const [dashboard,leads,partners,channels,banks,staff]=await Promise.all(jobs); Object.assign(state,{dashboard,leads,partners,channels,banks,staff}); render()
  }catch(error){ document.querySelectorAll('.screen').forEach(x=>x.classList.remove('is-active')); document.querySelector('#error-message').textContent=error.message; document.querySelector('#error-state').hidden=false }
}

function sourceCard(lead){
  if(lead.assignment_status==='confirmed') return `<section class="form-card"><h3>Источник подтверждён</h3><div class="value-row"><span>Канал</span><strong>${esc(lead.channel)}</strong></div></section>`
  const options=state.channels.filter(c=>c.active).map(c=>`<option value="${c.id}" data-partner="${c.partner_id}">${esc(c.partner)} — ${esc(c.name)}</option>`).join('')
  return `<section class="form-card"><h3>Источник заявки</h3><label class="field"><span>Партнёрский канал</span><select id="source-channel"><option value="">Выберите канал</option>${options}</select></label><div class="button-stack"><button class="primary-button" id="save-source">Сохранить источник</button>${lead.assignment_status==='pending'?'<button class="secondary-button" id="confirm-source">Подтвердить источник</button>':''}<button class="secondary-button" id="direct-source">Это прямая заявка</button></div></section>`
}
function bankCard(item,employee,admin){
  const options=Object.entries(bankLabels).slice(0,10).map(([v,l])=>`<option value="${v}" ${item.status===v?'selected':''}>${l}</option>`).join('')
  const edit=employee?`<label class="field"><span>Статус</span><select data-bank-status>${options}</select></label><div class="field-row"><label class="field"><span>Доход, прогноз</span><input type="number" data-estimate value="${item.income_estimate||''}"></label><label class="field"><span>Доход, факт</span><input type="number" data-fact value="${item.income_fact||''}"></label></div><label class="field"><span>Причина закрытия</span><input data-reason value="${esc(item.close_reason||'')}"></label><button class="secondary-button" data-save-bank="${item.id}">Сохранить банк</button>`:`<div class="value-row"><span>Статус</span><strong>${esc(bankLabels[item.status]||item.status)}</strong></div>`
  const confirm=admin&&item.payment_status==='awaiting_confirmation'?`<button class="primary-button" data-confirm-pay="${item.id}">Подтвердить выплату</button>`:''
  const next=admin&&item.payment_id&&['confirmed','in_registry'].includes(item.payment_status)?`<button class="primary-button" data-next-pay="${item.payment_id}" data-current="${item.payment_status}">${item.payment_status==='confirmed'?'Добавить в реестр':'Отметить выплаченной'}</button>`:''
  return `<article class="bank-card" data-bank-card="${item.id}"><header><h4>${esc(item.bank)}</h4><span>${esc(payLabels[item.payment_status]||item.payment_status)}</span></header>${edit}<div class="value-row"><span>Вознаграждение</span><strong class="money">${money(item.reward_fact||item.reward_estimate)}</strong></div><div class="button-stack">${confirm}${next}</div></article>`
}
async function openLead(id){
  try{
    const lead=await api(`/api/leads/${id}`), partner=state.session.role==='partner', employee=!partner, admin=state.session.role==='admin'
    const managers=state.staff.filter(x=>x.role==='manager'&&x.status==='active').map(x=>`<option value="${x.id}" ${lead.manager_id===x.id?'selected':''}>${esc(x.username||x.telegram_id)}</option>`).join('')
    const statuses=Object.entries(leadLabels).slice(0,18).map(([v,l])=>`<option value="${v}" ${lead.status===v?'selected':''}>${l}</option>`).join('')
    const details=partner?'':`<div class="value-row"><span>Телефон</span><strong>${esc(lead.phone)}</strong></div><div class="value-row"><span>Telegram</span><strong>${esc(lead.username||lead.telegram_id)}</strong></div>`
    const edit=employee?`<section class="form-card"><h3>Работа с заявкой</h3><label class="field"><span>Статус</span><select id="lead-status">${statuses}</select></label>${admin?`<label class="field"><span>Менеджер</span><select id="lead-manager"><option value="">Не назначен</option>${managers}</select></label>`:''}<label class="field"><span>Внутренний комментарий</span><textarea id="lead-comment">${esc(lead.comment||'')}</textarea></label><button class="primary-button" id="save-lead">Сохранить заявку</button></section>`:''
    const banks=lead.banks.map(x=>bankCard(x,employee,admin)).join('')
    openSheet(lead.name,`${lead.short_id} · ${leadLabels[lead.status]||lead.status}`,`<section class="form-card"><h3>Карточка</h3><div class="value-row"><span>Дата заявки</span><strong>${date(lead.date)}</strong></div><div class="value-row"><span>Источник</span><strong>${esc(lead.channel)}</strong></div><div class="value-row"><span>Менеджер</span><strong>${esc(lead.manager)}</strong></div>${details}</section>${edit}${admin?sourceCard(lead):''}<div class="list-heading"><h3>Банки</h3>${employee?'<button id="add-lead-bank">Добавить</button>':''}</div>${banks||'<p class="empty">Банки не добавлены</p>'}`)
    bindLeadActions(lead,admin)
  }catch(error){ toast(error.message) }
}
function bindLeadActions(lead,admin){
  document.querySelector('#save-lead')?.addEventListener('click',async()=>{ await api(`/api/leads/${lead.id}`,{method:'PATCH',body:JSON.stringify({internal_status:document.querySelector('#lead-status').value,manager_id:admin?(document.querySelector('#lead-manager').value||null):null,update_manager:admin,internal_comment:document.querySelector('#lead-comment').value,update_comment:true})}); toast('Заявка сохранена'); closeSheet(); await load() })
  document.querySelector('#save-source')?.addEventListener('click',async()=>{ const s=document.querySelector('#source-channel'),o=s.selectedOptions[0]; if(!s.value)return toast('Выберите канал'); await api(`/api/leads/${lead.id}/source`,{method:'PUT',body:JSON.stringify({channel_id:s.value,partner_id:o.dataset.partner})}); toast('Источник сохранён'); await openLead(lead.id) })
  document.querySelector('#confirm-source')?.addEventListener('click',async()=>{ await api(`/api/leads/${lead.id}/source/confirm`,{method:'POST'}); toast('Источник подтверждён'); await openLead(lead.id) })
  document.querySelector('#direct-source')?.addEventListener('click',async()=>{ await api(`/api/leads/${lead.id}/source/direct`,{method:'POST'}); toast('Прямая заявка'); await openLead(lead.id) })
  document.querySelector('#add-lead-bank')?.addEventListener('click',()=>addLeadBank(lead))
  document.querySelectorAll('[data-save-bank]').forEach(btn=>btn.addEventListener('click',async()=>{ const c=btn.closest('[data-bank-card]'); await api(`/api/lead-banks/${btn.dataset.saveBank}`,{method:'PATCH',body:JSON.stringify({status:c.querySelector('[data-bank-status]').value,close_reason:c.querySelector('[data-reason]').value||null,income_estimate:c.querySelector('[data-estimate]').value||null,income_fact:c.querySelector('[data-fact]').value||null})}); toast('Банк сохранён'); await openLead(lead.id) }))
  document.querySelectorAll('[data-confirm-pay]').forEach(btn=>btn.addEventListener('click',async()=>{ await api(`/api/lead-banks/${btn.dataset.confirmPay}/payment/confirm`,{method:'POST',body:'{}'}); toast('Выплата подтверждена'); await openLead(lead.id) }))
  document.querySelectorAll('[data-next-pay]').forEach(btn=>btn.addEventListener('click',async()=>{ const status=btn.dataset.current==='confirmed'?'in_registry':'paid'; await api(`/api/payments/${btn.dataset.nextPay}`,{method:'PATCH',body:JSON.stringify({status})}); toast(status==='paid'?'Выплата отмечена':'Добавлено в реестр'); await openLead(lead.id) }))
}
function addLeadBank(lead){
  const used=new Set(lead.banks.map(x=>x.bank_id)), options=state.banks.filter(x=>x.active&&!used.has(x.id)).map(x=>`<option value="${x.id}">${esc(x.name)}</option>`).join('')
  openSheet('Добавить банк',lead.short_id,`<section class="form-card"><label class="field"><span>Банк</span><select id="new-lead-bank">${options}</select></label></section><button class="primary-button" id="confirm-add-bank">Добавить</button>`)
  document.querySelector('#confirm-add-bank').addEventListener('click',async()=>{ const id=document.querySelector('#new-lead-bank').value;if(!id)return toast('Нет доступных банков');await api(`/api/leads/${lead.id}/banks`,{method:'POST',body:JSON.stringify({bank_id:id})});toast('Банк добавлен');await openLead(lead.id) })
}
function openPartner(id){ const p=state.partners.find(x=>x.id===id);openSheet(p.name,'Доступ партнёра',`<section class="form-card"><div class="value-row"><span>Комиссия</span><strong>${esc(p.commission)}%</strong></div><label class="field"><span>Telegram ID</span><input id="partner-id" inputmode="numeric"></label><label class="field"><span>Username без @</span><input id="partner-user"></label></section><button class="primary-button" id="save-partner">Привязать кабинет</button>`);document.querySelector('#save-partner').addEventListener('click',async()=>{await api(`/api/partners/${id}/access`,{method:'PUT',body:JSON.stringify({telegram_id:document.querySelector('#partner-id').value,telegram_username:document.querySelector('#partner-user').value||null})});toast('Доступ настроен');closeSheet()}) }
function showScreen(name){ document.querySelectorAll('.screen').forEach(x=>x.classList.toggle('is-active',x.id===`${name}-screen`));document.querySelectorAll('[data-screen]').forEach(x=>x.classList.toggle('is-active',x.dataset.screen===name));window.scrollTo({top:0,behavior:'smooth'}) }

document.addEventListener('click',async event=>{ const lead=event.target.closest('[data-lead]'),partner=event.target.closest('[data-partner]'),bank=event.target.closest('[data-bank]'),staff=event.target.closest('[data-staff]');try{if(lead)await openLead(lead.dataset.lead);if(partner)openPartner(partner.dataset.partner);if(bank&&state.session.role==='admin'){await api(`/api/banks/${bank.dataset.bank}/toggle`,{method:'POST'});toast('Статус банка изменён');await load()}if(staff&&state.session.role==='admin'){await api(`/api/staff/${staff.dataset.staff}/toggle`,{method:'POST'});toast('Доступ изменён');await load()}}catch(error){toast(error.message)} })
document.querySelectorAll('[data-screen]').forEach(x=>x.addEventListener('click',()=>showScreen(x.dataset.screen)))
document.querySelectorAll('[data-go]').forEach(x=>x.addEventListener('click',()=>showScreen(x.dataset.go)))
document.querySelector('#close-sheet').addEventListener('click',closeSheet);document.querySelector('#sheet-backdrop').addEventListener('click',closeSheet);document.querySelector('#retry-button').addEventListener('click',load)
document.querySelector('#lead-search').addEventListener('input',event=>{const q=event.target.value.trim().toLowerCase();renderLeads(state.leads.filter(x=>`${x.name} ${x.phone||''} ${x.short_id}`.toLowerCase().includes(q)),document.querySelector('#all-leads'))})
document.querySelector('#lead-scope').addEventListener('change',async event=>{state.leadScope=event.target.value;await load()})
document.querySelector('#download-report').addEventListener('click',async()=>{try{const response=await fetch('/api/reports/leads.csv',{headers:{'X-Telegram-Init-Data':tg?.initData||''}});if(!response.ok)throw new Error('Не удалось сформировать отчёт');const link=document.createElement('a');link.href=URL.createObjectURL(await response.blob());link.download='rko-leads.csv';link.click();setTimeout(()=>URL.revokeObjectURL(link.href),1000);toast('Отчёт сформирован')}catch(error){toast(error.message)}})
document.querySelector('#add-bank-button').addEventListener('click',()=>{openSheet('Новый банк','Справочник','<section class="form-card"><label class="field"><span>Название</span><input id="new-bank"></label></section><button class="primary-button" id="create-bank">Добавить</button>');document.querySelector('#create-bank').addEventListener('click',async()=>{await api('/api/banks',{method:'POST',body:JSON.stringify({name:document.querySelector('#new-bank').value})});toast('Банк добавлен');closeSheet();await load()})})
document.querySelector('#add-staff-button').addEventListener('click',()=>{openSheet('Новый сотрудник','Доступ','<section class="form-card"><label class="field"><span>Telegram ID</span><input id="staff-id" inputmode="numeric"></label><label class="field"><span>Username без @</span><input id="staff-user"></label><label class="field"><span>Роль</span><select id="staff-role"><option value="manager">Менеджер</option><option value="admin">Администратор</option></select></label></section><button class="primary-button" id="create-staff">Добавить</button>');document.querySelector('#create-staff').addEventListener('click',async()=>{await api('/api/staff',{method:'POST',body:JSON.stringify({telegram_id:document.querySelector('#staff-id').value,telegram_username:document.querySelector('#staff-user').value||null,role:document.querySelector('#staff-role').value})});toast('Сотрудник добавлен');closeSheet();await load()})})
load()
