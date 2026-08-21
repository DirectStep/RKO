const tg = window.Telegram?.WebApp
tg?.ready(); tg?.expand()

const state = { session: null, dashboard: {}, leads: [], partners: [], channels: [], banks: [], staff: [], leadApplication: null, leadBanks: [], leadScope: 'all' }
const leadLabels = { new:'Новая',manager_assigned:'Менеджер назначен',awaiting_first_contact:'Ждёт звонка',contacted:'Связались',awaiting_data:'Ждём данные',data_received:'Данные получены',selecting_banks:'Подбираем банки',preparing_applications:'Готовим заявки',applications_sent:'Заявки отправлены',opening_accounts:'Открытие счетов',partially_opened:'Часть счетов открыта',all_planned_opened:'Счета открыты',paused:'На паузе',no_response:'Нет ответа',lead_refused:'Отказ клиента',not_eligible:'Не подходит',completed:'Завершена',in_progress:'В работе',partially_completed:'Частично завершена',closed_without_result:'Закрыта без результата' }
const internalLeadStatuses = ['new','manager_assigned','awaiting_first_contact','contacted','awaiting_data','data_received','selecting_banks','preparing_applications','applications_sent','opening_accounts','partially_opened','all_planned_opened','paused','no_response','lead_refused','not_eligible','completed']
const questionLabels = { adult:'Совершеннолетие',has_ip:'ИП',city:'Город',has_bankruptcy_or_arrests:'Банкротства или аресты',is_civil_servant:'Госслужащий',has_social_benefits:'Социальные выплаты',no_bankruptcy:'Нет банкротств или арестов',not_civil_servant:'Не госслужащий',no_social_benefits:'Нет социальных выплат' }
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
function dateTime(value){ return value ? new Intl.DateTimeFormat('ru-RU',{dateStyle:'medium',timeStyle:'short'}).format(new Date(value)) : '—' }
function localISODate(){ const now=new Date(),pad=value=>String(value).padStart(2,'0');return `${now.getFullYear()}-${pad(now.getMonth()+1)}-${pad(now.getDate())}` }
function money(value){ return value===null||value===undefined||value==='' ? '—' : `${new Intl.NumberFormat('ru-RU').format(Number(value))} ₽` }
function answer(value){ if(value===true||value==='yes'||value==='Да')return 'Да';if(value===false||value==='no'||value==='Нет')return 'Нет';return value||'—' }
function toast(message){ const el=document.querySelector('#toast'); el.textContent=message; el.hidden=false; clearTimeout(toast.timer); toast.timer=setTimeout(()=>el.hidden=true,2400) }
function openSheet(title, eyebrow, html){ document.querySelector('#sheet-title').textContent=title; document.querySelector('#sheet-eyebrow').textContent=eyebrow; document.querySelector('#sheet-content').innerHTML=html; document.querySelector('#sheet-backdrop').hidden=false; document.querySelector('#bottom-sheet').hidden=false }
function closeSheet(){ document.querySelector('#sheet-backdrop').hidden=true; document.querySelector('#bottom-sheet').hidden=true }
async function copyText(value){
  if(navigator.clipboard?.writeText) await navigator.clipboard.writeText(value)
  else { const input=document.createElement('textarea');input.value=value;input.style.position='fixed';input.style.opacity='0';document.body.append(input);input.select();document.execCommand('copy');input.remove() }
  toast('Ссылка скопирована')
}

function leadRow(lead){
  const detail=state.session.role==='partner'?lead.username:lead.phone
  return `<button class="list-row" type="button" data-lead="${lead.id}"><span class="row-icon">${initials(lead.name)||'Р'}</span><span class="row-content"><span class="row-title"><strong>${esc(lead.name)}</strong><time>${date(lead.date).slice(0,5)}</time></span><span class="row-subtitle">${esc(lead.short_id)} · ${esc(leadLabels[lead.status]||lead.status)}${detail?` · ${esc(detail)}`:''}</span></span></button>`
}
function renderLeads(items,target){ target.innerHTML=items.length?items.map(leadRow).join(''):'<p class="empty">Заявок пока нет</p>' }
function updateLeadCount(count){ document.querySelector('#lead-count').textContent=`Показано: ${count}` }
function render(){
  const admin=state.session.role==='admin', partnerRole=state.session.role==='partner', employee=admin||state.session.role==='manager'
  document.querySelector('#loading-state').hidden=true
  document.querySelector('.tabbar').hidden=false
  document.querySelectorAll('#client-application-tab, #client-banks-tab').forEach(item=>item.hidden=true)
  document.querySelector('#greeting').textContent=state.session.name
  document.querySelector('#avatar').textContent=initials(state.session.name)||'Р'
  for(const key of ['total','new','active','unresolved']) document.querySelector(`#${key}-count`).textContent=state.dashboard[key]
  renderLeads(state.leads.slice(0,5),document.querySelector('#recent-leads')); renderLeads(state.leads,document.querySelector('#all-leads')); updateLeadCount(state.leads.length)
  document.querySelector('#partners-tab').hidden=!(admin||partnerRole); document.querySelector('#banks-tab').hidden=!employee; document.querySelector('#team-tab').hidden=!employee
  document.querySelector('#scope-filter').hidden=state.session.role!=='manager'
  document.querySelector('#add-bank-button').hidden=!admin; document.querySelector('#add-staff-button').hidden=!admin; document.querySelector('#add-channel-button').hidden=!partnerRole
  document.querySelector('#open-google-sheet').hidden=!admin||!state.session.google_sheet_url
  document.querySelector('.tabbar').style.setProperty('--tab-count',admin?5:employee?4:3)
  document.querySelector('#partners-tab-label').textContent=partnerRole?'Каналы':'Партнёры'; document.querySelector('#partners-title').textContent=partnerRole?'Каналы':'Партнёры'; document.querySelector('#partners-eyebrow').textContent=partnerRole?'Источники твоего трафика':'Источники заявок'
  document.querySelector('#partners-list').innerHTML=partnerRole?(state.channels.length?state.channels.map(channel=>`<button class="list-row" type="button" data-copy-channel="${esc(channel.link)}"><span class="row-icon partner">${initials(channel.name)||'К'}</span><span class="row-content"><span class="row-title"><strong>${esc(channel.name)}</strong></span><span class="row-subtitle">${esc(channel.link)}</span></span><b>Скопировать</b></button>`).join(''):'<p class="empty">Добавь первый канал и получи ссылку для лидов</p>'):(state.partners.length?state.partners.map(p=>`<button class="list-row" type="button" data-partner="${p.id}"><span class="row-icon partner">${initials(p.name)||'П'}</span><span class="row-content"><span class="row-title"><strong>${esc(p.name)}</strong></span><span class="row-subtitle">${esc(p.commission)}% · каналов: ${p.channels}</span></span><i class="status-dot ${p.active?'':'off'}"></i></button>`).join(''):'<p class="empty">Партнёров пока нет</p>')
  document.querySelector('#banks-list').innerHTML=state.banks.length?state.banks.map(b=>`<button class="list-row" type="button" data-bank="${b.id}"><span class="row-icon">Б</span><span class="row-content"><span class="row-title"><strong>${esc(b.name)}</strong></span><span class="row-subtitle">${b.active?'Можно добавлять в заявки':'Отключён'}</span></span><i class="status-dot ${b.active?'':'off'}"></i></button>`).join(''):'<p class="empty">Добавьте первый банк</p>'
  document.querySelector('#staff-list').innerHTML=state.staff.length?state.staff.map(p=>`<button class="list-row" type="button" data-staff="${p.id}"><span class="row-icon partner">${p.role==='admin'?'А':'М'}</span><span class="row-content"><span class="row-title"><strong>${esc(p.username||p.telegram_id)}</strong></span><span class="row-subtitle">${p.role==='admin'?'Администратор':'Менеджер'} · ${p.status==='pending'?'ожидает первого входа':p.status==='active'?'доступ включён':'доступ отключён'}</span></span><i class="status-dot ${p.status==='active'?'':'off'}"></i></button>`).join(''):'<p class="empty">Сотрудников пока нет</p>'
  if(!document.querySelector('.screen.is-active'))showScreen('summary')
}
function renderLeadCabinet(){
  const application=state.leadApplication
  document.querySelector('#loading-state').hidden=true
  document.querySelector('.tabbar').hidden=false
  document.querySelector('#greeting').textContent='Кабинет клиента'
  document.querySelector('#avatar').textContent=initials(state.session.name)||'К'
  document.querySelectorAll('.tabbar button').forEach(item=>item.hidden=true)
  document.querySelector('#client-application-tab').hidden=false
  document.querySelector('#client-banks-tab').hidden=false
  document.querySelector('.tabbar').style.setProperty('--tab-count',2)
  document.querySelector('#client-application-id').textContent=application.short_id
  const manager=application.manager_url
    ? `<a class="contact-row" href="${esc(application.manager_url)}" target="_blank" rel="noopener"><span><small>Менеджер</small><strong>${esc(application.manager)}</strong></span><b>Написать</b></a>`
    : `<div class="value-row"><span>Менеджер</span><strong>${esc(application.manager||'Ещё не назначен')}</strong></div>`
  document.querySelector('#client-application-card').innerHTML=`<section class="client-hero"><span>Текущий статус</span><strong>${esc(leadLabels[application.status]||application.status)}</strong><small>Обновлено ${dateTime(application.updated)}</small></section><section class="detail-section"><h3>Данные заявки</h3><div class="value-row"><span>Номер</span><strong>${esc(application.short_id)}</strong></div><div class="value-row"><span>Создана</span><strong>${date(application.date)}</strong></div>${manager}</section><p class="client-note">Здесь отображается актуальный статус. Если появятся вопросы, напиши своему менеджеру.</p>`
  document.querySelector('#client-banks-list').innerHTML=state.leadBanks.length?state.leadBanks.map(item=>`<article class="client-bank-card"><header><span class="client-bank-icon">Б</span><div><h3>${esc(item.bank)}</h3><p>${esc(bankLabels[item.status]||item.status)}</p></div></header><section class="activation-action"><span>Что нужно сделать</span><p>${esc(item.action_text||'Уточняем целевое действие — менеджер сообщит его отдельно.')}</p></section><small>Обновлено ${dateTime(item.updated)}</small></article>`).join(''):'<section class="empty-card"><span class="client-bank-icon">Б</span><h3>Банки ещё не назначены</h3><p>Когда менеджер подберёт банки, они появятся здесь вместе с условиями активации.</p></section>'
  showScreen('client-application')
}
async function load(){
  document.querySelectorAll('.screen').forEach(x=>x.classList.remove('is-active'))
  document.querySelector('#loading-state').hidden=false
  document.querySelector('.tabbar').hidden=true
  document.querySelector('#error-state').hidden=true
  try{
    state.session=await api('/api/session')
    if(state.session.role==='lead'){
      const [leadApplication,leadBanks]=await Promise.all([api('/api/lead/application'),api('/api/lead/banks')])
      Object.assign(state,{leadApplication,leadBanks});renderLeadCabinet();return
    }
    const employee=['admin','manager'].includes(state.session.role)
    const jobs=[api('/api/dashboard'),api(`/api/leads${state.leadScope==='mine'?'?mine=true':''}`),state.session.role==='admin'?api('/api/partners'):[],['admin','partner'].includes(state.session.role)?api('/api/channels'):[],employee?api('/api/banks'):[],employee?api('/api/staff'):[]]
    const [dashboard,leads,partners,channels,banks,staff]=await Promise.all(jobs); Object.assign(state,{dashboard,leads,partners,channels,banks,staff}); render()
  }catch(error){ document.querySelector('#loading-state').hidden=true; document.querySelector('.tabbar').hidden=true; document.querySelectorAll('.screen').forEach(x=>x.classList.remove('is-active')); document.querySelector('#error-message').textContent=error.message; document.querySelector('#error-state').hidden=false }
}

function sourceCard(lead){
  if(lead.assignment_status==='confirmed') return `<section class="form-card"><h3>Источник подтверждён</h3><div class="value-row"><span>Канал</span><strong>${esc(lead.channel)}</strong></div></section>`
  if(lead.assignment_status==='direct') return `<section class="form-card"><h3>Источник заявки</h3><div class="value-row"><span>Источник</span><strong>Прямая заявка</strong></div></section>`
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
    const statusButtons=internalLeadStatuses.map(value=>`<button type="button" class="status-option ${lead.status===value?'is-selected':''}" data-lead-status="${value}" aria-pressed="${lead.status===value}">${esc(leadLabels[value])}</button>`).join('')
    const username=String(lead.username||'').replace(/^@/,'')
    const telegramLink=/^[A-Za-z0-9_]{5,}$/.test(username)?`https://t.me/${username}`:''
    const phoneLink=String(lead.phone||'').replace(/[^+\d]/g,'')
    const contacts=partner?'':`<section class="detail-section"><h3>Контакты</h3><a class="contact-row" href="tel:${esc(phoneLink)}"><span><small>Телефон</small><strong>${esc(lead.phone||'Не указан')}</strong></span><b aria-hidden="true">Позвонить</b></a>${telegramLink?`<a class="contact-row" href="${esc(telegramLink)}" target="_blank" rel="noopener"><span><small>Telegram</small><strong>@${esc(username)}</strong></span><b aria-hidden="true">Открыть</b></a>`:`<div class="value-row"><span>Telegram</span><strong>${esc(lead.username||lead.telegram_id||'Не указан')}</strong></div>`}</section>`
    const answers=partner?'':Object.entries(lead.answers||{}).map(([key,value])=>`<div class="value-row"><span>${esc(questionLabels[key]||key)}</span><strong>${esc(answer(value))}</strong></div>`).join('')
    const statusEditor=employee?`<section class="detail-section status-section"><h3>Статус заявки</h3><details><summary><span><small>Текущий статус</small><strong>${esc(leadLabels[lead.status]||lead.status)}</strong></span><b>Изменить</b></summary><div class="status-grid">${statusButtons}</div></details></section>`:''
    const edit=employee?`<section class="detail-section"><h3>Работа с заявкой</h3>${admin?`<label class="field"><span>Менеджер</span><select id="lead-manager"><option value="">Не назначен</option>${managers}</select></label>`:''}<label class="field"><span>Внутренний комментарий</span><textarea id="lead-comment" placeholder="Заметка для команды">${esc(lead.comment||'')}</textarea></label><button class="primary-button inset-button" id="save-lead">Сохранить изменения</button></section>`:''
    const banks=lead.banks.map(x=>bankCard(x,employee,admin)).join('')
    const application=`<section class="detail-section"><h3>Заявка</h3><div class="value-row"><span>Создана</span><strong>${dateTime(lead.date)}</strong></div><div class="value-row"><span>Обновлена</span><strong>${dateTime(lead.updated)}</strong></div><div class="value-row"><span>Источник</span><strong>${esc(lead.channel)}</strong></div><div class="value-row"><span>Менеджер</span><strong>${esc(lead.manager)}</strong></div>${partner?'':`<div class="value-row"><span>Согласие на данные</span><strong>${lead.consent?'Получено':'Нет'}${lead.consent_at?` · ${date(lead.consent_at)}`:''}</strong></div>`}</section>`
    const questionnaire=partner||!answers?'':`<section class="detail-section"><h3>Анкета</h3>${answers}</section>`
    openSheet(lead.name,`${lead.short_id} · ${leadLabels[lead.status]||lead.status}`,`${contacts}${application}${statusEditor}${questionnaire}${edit}${admin?sourceCard(lead):''}<div class="list-heading"><h3>Банки</h3>${employee?'<button id="add-lead-bank">Добавить</button>':''}</div>${banks||'<p class="empty">Банки не добавлены</p>'}`)
    bindLeadActions(lead,admin)
  }catch(error){ toast(error.message) }
}
function bindLeadActions(lead,admin){
  document.querySelectorAll('[data-lead-status]').forEach(button=>button.addEventListener('click',async()=>{ if(button.dataset.leadStatus===lead.status)return; document.querySelectorAll('[data-lead-status]').forEach(item=>item.disabled=true); await api(`/api/leads/${lead.id}`,{method:'PATCH',body:JSON.stringify({internal_status:button.dataset.leadStatus})}); toast('Статус изменён'); await openLead(lead.id); await load() }))
  document.querySelector('#save-lead')?.addEventListener('click',async()=>{ await api(`/api/leads/${lead.id}`,{method:'PATCH',body:JSON.stringify({manager_id:admin?(document.querySelector('#lead-manager').value||null):null,update_manager:admin,internal_comment:document.querySelector('#lead-comment').value,update_comment:true})}); toast('Изменения сохранены'); await openLead(lead.id); await load() })
  document.querySelector('#save-source')?.addEventListener('click',async()=>{ const s=document.querySelector('#source-channel'),o=s.selectedOptions[0]; if(!s.value)return toast('Выберите канал'); await api(`/api/leads/${lead.id}/source`,{method:'PUT',body:JSON.stringify({channel_id:s.value,partner_id:o.dataset.partner})}); toast('Источник сохранён'); await openLead(lead.id) })
  document.querySelector('#confirm-source')?.addEventListener('click',async()=>{ await api(`/api/leads/${lead.id}/source/confirm`,{method:'POST'}); toast('Источник подтверждён'); await openLead(lead.id) })
  document.querySelector('#direct-source')?.addEventListener('click',async()=>{ await api(`/api/leads/${lead.id}/source/direct`,{method:'POST'}); toast('Прямая заявка'); await openLead(lead.id) })
  document.querySelector('#add-lead-bank')?.addEventListener('click',()=>addLeadBank(lead))
  document.querySelectorAll('[data-save-bank]').forEach(btn=>btn.addEventListener('click',async()=>{ const c=btn.closest('[data-bank-card]'); await api(`/api/lead-banks/${btn.dataset.saveBank}`,{method:'PATCH',body:JSON.stringify({status:c.querySelector('[data-bank-status]').value,close_reason:c.querySelector('[data-reason]').value||null,income_estimate:c.querySelector('[data-estimate]').value||null,income_fact:c.querySelector('[data-fact]').value||null})}); toast('Банк сохранён'); await openLead(lead.id) }))
  document.querySelectorAll('[data-confirm-pay]').forEach(btn=>btn.addEventListener('click',async()=>{ await api(`/api/lead-banks/${btn.dataset.confirmPay}/payment/confirm`,{method:'POST',body:'{}'}); toast('Выплата подтверждена'); await openLead(lead.id) }))
  document.querySelectorAll('[data-next-pay]').forEach(btn=>btn.addEventListener('click',async()=>{ const status=btn.dataset.current==='confirmed'?'in_registry':'paid'; const payload={status}; if(status==='paid')payload.paid_at=localISODate(); await api(`/api/payments/${btn.dataset.nextPay}`,{method:'PATCH',body:JSON.stringify(payload)}); toast(status==='paid'?'Выплата отмечена':'Добавлено в реестр'); await openLead(lead.id) }))
}
function addLeadBank(lead){
  const used=new Set(lead.banks.map(x=>x.bank_id)), options=state.banks.filter(x=>x.active&&!used.has(x.id)).map(x=>`<option value="${x.id}">${esc(x.name)}</option>`).join('')
  openSheet('Добавить банк',lead.short_id,`<section class="form-card"><label class="field"><span>Банк</span><select id="new-lead-bank">${options}</select></label></section><button class="primary-button" id="confirm-add-bank">Добавить</button>`)
  document.querySelector('#confirm-add-bank').addEventListener('click',async()=>{ const id=document.querySelector('#new-lead-bank').value;if(!id)return toast('Нет доступных банков');await api(`/api/leads/${lead.id}/banks`,{method:'POST',body:JSON.stringify({bank_id:id})});toast('Банк добавлен');await openLead(lead.id) })
}
function openPartner(id){
  const p=state.partners.find(x=>x.id===id), channels=state.channels.filter(x=>x.partner_id===id)
  const links=channels.length?channels.map(channel=>`<a class="contact-row" href="${esc(channel.link)}" target="_blank" rel="noopener"><span><small>${esc(channel.name)}</small><strong>${esc(channel.link)}</strong></span><b>Открыть</b></a>`).join(''):'<p class="empty">Каналов пока нет</p>'
  const username=String(p.telegram_username||'').replace(/^@/,'')
  const telegram=username?`@${username}${p.telegram_id?` · ID ${p.telegram_id}`:''}`:p.telegram_id?`ID ${p.telegram_id}`:'Не привязан'
  openSheet(p.name,'Партнёр и каналы',`<section class="detail-section"><h3>Реферальные ссылки</h3>${links}</section><section class="form-card"><h3>Настройки партнёра</h3><label class="field"><span>Процент партнёра</span><input id="partner-commission" inputmode="decimal" value="${esc(p.commission)}"></label><button class="secondary-button inset-button" id="save-commission">Сохранить процент</button><div class="value-row"><span>Telegram</span><strong>${esc(telegram)}</strong></div><label class="field"><span>Telegram ID</span><input id="partner-id" inputmode="numeric" value="${esc(p.telegram_id||'')}" placeholder="Например, 123456789"></label><label class="field"><span>Username без @</span><input id="partner-user" value="${esc(username)}" placeholder="Например, gerasimov"></label><p class="field-note">Username привяжется при первом входе партнёра. Telegram ID можно указать сразу, если он известен.</p><button class="primary-button inset-button" id="save-partner">Сохранить доступ</button></section><section class="destructive-section"><button class="danger-button" id="show-remove-partner">Убрать партнёра</button><div id="remove-partner-confirm" hidden><p>Партнёр и его каналы будут удалены. Если уже есть заявки, удаление не выполнится.</p><div class="button-stack"><button class="danger-button" id="remove-partner">Да, удалить</button><button class="secondary-button" id="cancel-remove-partner">Отмена</button></div></div></section>`)
  document.querySelector('#save-commission').addEventListener('click',async()=>{await api(`/api/partners/${id}`,{method:'PATCH',body:JSON.stringify({commission_percent:document.querySelector('#partner-commission').value.replace(',','.')})});toast('Процент сохранён');await load();openPartner(id)})
  document.querySelector('#save-partner').addEventListener('click',async()=>{const telegramId=document.querySelector('#partner-id').value.trim(),telegramUsername=document.querySelector('#partner-user').value.trim();if(telegramId){await api(`/api/partners/${id}/access`,{method:'PUT',body:JSON.stringify({telegram_id:telegramId,telegram_username:telegramUsername||null})});toast('Доступ настроен')}else{if(!telegramUsername)return toast('Укажи username или Telegram ID');await api(`/api/partners/${id}`,{method:'PATCH',body:JSON.stringify({telegram_username:telegramUsername})});toast('Username сохранён')}await load();openPartner(id)})
  document.querySelector('#show-remove-partner').addEventListener('click',()=>{document.querySelector('#show-remove-partner').hidden=true;document.querySelector('#remove-partner-confirm').hidden=false})
  document.querySelector('#cancel-remove-partner').addEventListener('click',()=>{document.querySelector('#show-remove-partner').hidden=false;document.querySelector('#remove-partner-confirm').hidden=true})
  document.querySelector('#remove-partner').addEventListener('click',async()=>{try{await api(`/api/partners/${id}`,{method:'DELETE'});toast('Партнёр удалён');closeSheet();await load()}catch(error){toast(error.message)}})
}
function showScreen(name){ document.querySelectorAll('.screen').forEach(x=>x.classList.toggle('is-active',x.id===`${name}-screen`));document.querySelectorAll('[data-screen]').forEach(x=>x.classList.toggle('is-active',x.dataset.screen===name));window.scrollTo({top:0,behavior:'smooth'}) }

document.addEventListener('click',async event=>{ const lead=event.target.closest('[data-lead]'),partner=event.target.closest('[data-partner]'),channel=event.target.closest('[data-copy-channel]'),bank=event.target.closest('[data-bank]'),staff=event.target.closest('[data-staff]');try{if(lead)await openLead(lead.dataset.lead);if(partner)openPartner(partner.dataset.partner);if(channel)await copyText(channel.dataset.copyChannel);if(bank&&state.session.role==='admin'){await api(`/api/banks/${bank.dataset.bank}/toggle`,{method:'POST'});toast('Статус банка изменён');await load()}if(staff&&state.session.role==='admin'){await api(`/api/staff/${staff.dataset.staff}/toggle`,{method:'POST'});toast('Доступ изменён');await load()}}catch(error){toast(error.message)} })
document.querySelectorAll('[data-screen]').forEach(x=>x.addEventListener('click',()=>showScreen(x.dataset.screen)))
document.querySelectorAll('[data-go]').forEach(x=>x.addEventListener('click',()=>showScreen(x.dataset.go)))
document.querySelector('#close-sheet').addEventListener('click',closeSheet);document.querySelector('#sheet-backdrop').addEventListener('click',closeSheet);document.querySelector('#retry-button').addEventListener('click',load)
document.querySelector('#lead-search').addEventListener('input',event=>{const q=event.target.value.trim().toLowerCase(),items=state.leads.filter(x=>`${x.name} ${x.phone||''} ${x.username||''} ${x.short_id}`.toLowerCase().includes(q));renderLeads(items,document.querySelector('#all-leads'));updateLeadCount(items.length)})
document.querySelector('#lead-scope').addEventListener('change',async event=>{state.leadScope=event.target.value;await load()})
document.querySelector('#download-report').addEventListener('click',async()=>{try{const response=await fetch('/api/reports/leads.csv',{headers:{'X-Telegram-Init-Data':tg?.initData||''}});if(!response.ok)throw new Error('Не удалось сформировать отчёт');const link=document.createElement('a');link.href=URL.createObjectURL(await response.blob());link.download='rko-leads.csv';link.click();setTimeout(()=>URL.revokeObjectURL(link.href),1000);toast('Отчёт сформирован')}catch(error){toast(error.message)}})
document.querySelector('#open-google-sheet').addEventListener('click',()=>{const url=state.session?.google_sheet_url;if(!url)return;tg?.openLink?tg.openLink(url):window.open(url,'_blank','noopener')})
document.querySelector('#add-bank-button').addEventListener('click',()=>{openSheet('Новый банк','Справочник','<section class="form-card"><label class="field"><span>Название</span><input id="new-bank"></label></section><button class="primary-button" id="create-bank">Добавить</button>');document.querySelector('#create-bank').addEventListener('click',async()=>{await api('/api/banks',{method:'POST',body:JSON.stringify({name:document.querySelector('#new-bank').value})});toast('Банк добавлен');closeSheet();await load()})})
document.querySelector('#add-staff-button').addEventListener('click',()=>{openSheet('Новый сотрудник','Доступ','<section class="form-card"><label class="field"><span>Username без @</span><input id="staff-user" placeholder="Например, anutka_rko"></label><p class="field-note">Сотрудник получит доступ после первого запуска бота через /start.</p><label class="field"><span>Роль</span><select id="staff-role"><option value="manager">Менеджер</option><option value="admin">Администратор</option></select></label></section><button class="primary-button" id="create-staff">Добавить</button>');document.querySelector('#create-staff').addEventListener('click',async()=>{await api('/api/staff',{method:'POST',body:JSON.stringify({telegram_username:document.querySelector('#staff-user').value,role:document.querySelector('#staff-role').value})});toast('Приглашение добавлено');closeSheet();await load()})})
document.querySelector('#add-channel-button').addEventListener('click',()=>{openSheet('Новый канал','Источник трафика','<section class="form-card"><label class="field"><span>Название канала</span><input id="new-channel" maxlength="160" placeholder="Например, Telegram-канал"></label><p class="field-note">Для каждого источника создавай отдельный канал — так будет видно, откуда пришёл лид.</p></section><button class="primary-button" id="create-channel">Создать ссылку</button>');document.querySelector('#create-channel').addEventListener('click',async()=>{try{const created=await api('/api/channels',{method:'POST',body:JSON.stringify({name:document.querySelector('#new-channel').value})});await load();openSheet(created.name,'Канал создан',`<section class="detail-section"><h3>Ссылка для лидов</h3><div class="value-row"><span>Источник</span><strong>${esc(created.name)}</strong></div><div class="value-row"><span>Ссылка</span><strong>${esc(created.link)}</strong></div></section><button class="primary-button" id="copy-created-channel">Скопировать ссылку</button>`);document.querySelector('#copy-created-channel').addEventListener('click',()=>copyText(created.link))}catch(error){toast(error.message)}})})
load()
