function telegramWebApp(){return window.Telegram?.WebApp}
function telegramInitData(){return telegramWebApp()?.initData||new URLSearchParams(window.location.hash.slice(1)).get('tgWebAppData')||''}
telegramWebApp()?.ready(); telegramWebApp()?.expand()

let telegramContextWaited=false
async function waitForTelegramContext(){
  if(telegramInitData()||telegramContextWaited)return
  telegramContextWaited=true
  for(let attempt=0;attempt<20&&!telegramInitData();attempt+=1){
    await new Promise(resolve=>setTimeout(resolve,100))
  }
  telegramWebApp()?.ready();telegramWebApp()?.expand()
}

const state = { session: null, dashboard: {}, leads: [], partners: [], channels: [], banks: [], staff: [], duplicates: [], leadApplication: null, leadBanks: [], leadScope: 'queue', partnerData: null, currentScreen: 'summary' }
const leadLabels = { new:'Новая',manager_assigned:'Менеджер назначен',awaiting_first_contact:'Ждёт звонка',contacted:'Связались',awaiting_data:'Ждём данные',data_received:'Данные получены',selecting_banks:'Подбираем банки',preparing_applications:'Готовим заявки',applications_sent:'Заявки отправлены',opening_accounts:'Открытие счетов',partially_opened:'Часть счетов открыта',all_planned_opened:'Счета открыты',paused:'На паузе',no_response:'Нет ответа',lead_refused:'Отказ клиента',not_eligible:'Не подходит',completed:'Завершена',in_progress:'В работе',partially_completed:'Частично завершена',closed_without_result:'Закрыта без результата' }
const internalLeadStatuses = ['new','manager_assigned','awaiting_first_contact','contacted','awaiting_data','data_received','selecting_banks','preparing_applications','applications_sent','opening_accounts','partially_opened','all_planned_opened','paused','no_response','lead_refused','not_eligible','completed']
const questionLabels = { adult:'Совершеннолетие',has_ip:'ИП',city:'Город',full_name:'ФИО',email:'E-mail',has_bankruptcy_or_arrests:'Банкротства или аресты',is_civil_servant:'Госслужащий',has_social_benefits:'Социальные выплаты',no_bankruptcy:'Нет банкротств или арестов',not_civil_servant:'Не госслужащий',no_social_benefits:'Нет социальных выплат' }
const bankLabels = { planned:'Запланирован',awaiting_data:'Ждём данные',preparing_application:'Готовим заявку',application_sent:'Заявка отправлена',under_review:'На рассмотрении',revision_required:'Нужна доработка',account_opened:'Счёт открыт',bank_rejected:'Отказ банка',client_refused:'Отказ клиента',excluded:'Исключён',in_progress:'В работе',opened:'Открыт',not_opened:'Не открыт',will_not_open:'Не будет открыт' }
const payLabels = { not_calculated:'Не рассчитана',calculated:'Рассчитана',awaiting_confirmation:'Ждёт подтверждения',confirmed:'Подтверждена',in_registry:'В реестре',paid:'Выплачена',cancelled:'Отменена' }
const workflowLabels = { awaiting_admin:'Ожидает администратора',admin_processing:'Первичная обработка',awaiting_client_selection:'Клиент выбирает банки',awaiting_manager:'Ожидает менеджера',manager_processing:'В работе у менеджера',not_eligible:'Не подходит' }

async function api(path, options={}) {
  const attempts=(options.method||'GET').toUpperCase()==='GET'?3:1
  for(let attempt=1;attempt<=attempts;attempt+=1){
    const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),12000)
    try{
      const response = await fetch(path, { ...options, cache:'no-store', signal:controller.signal, headers:{ 'Content-Type':'application/json','X-Telegram-Init-Data':telegramInitData(),...(options.headers||{}) } })
      if (!response.ok) { const body=await response.json().catch(()=>({})); throw new Error(body.detail||'Не удалось выполнить действие') }
      return response.status===204 ? null : response.json()
    }catch(error){
      if(attempt===attempts){
        if(error.name==='AbortError')throw new Error('Сервер отвечает слишком долго. Нажми «Повторить».')
        throw error
      }
      await new Promise(resolve=>setTimeout(resolve,400*attempt))
    }finally{clearTimeout(timeout)}
  }
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
  const status=state.session.role==='partner'?(leadLabels[lead.status]||lead.status):(workflowLabels[lead.workflow_stage]||leadLabels[lead.status]||lead.status)
  return `<button class="list-row" type="button" data-lead="${lead.id}"><span class="row-icon">${initials(lead.name)||'Р'}</span><span class="row-content"><span class="row-title"><strong>${esc(lead.name)}</strong><time>${date(lead.date).slice(0,5)}</time></span><span class="row-subtitle">${esc(lead.short_id)} · ${lead.is_repeat?'Повторная · ':''}${esc(status)}${detail?` · ${esc(detail)}`:''}</span></span></button>`
}
function renderLeads(items,target){ target.innerHTML=items.length?items.map(leadRow).join(''):'<p class="empty">Заявок пока нет</p>' }
function updateLeadCount(count){ document.querySelector('#lead-count').textContent=`Показано: ${count}` }
function monthStart(){ const now=new Date();return `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-01` }
function partnerQuery(){
  const params=new URLSearchParams()
  const period=document.querySelector('#partner-period').value
  if(period==='month')params.set('date_from',monthStart())
  if(period==='custom'){
    const from=document.querySelector('#partner-date-from').value,to=document.querySelector('#partner-date-to').value
    if(from)params.set('date_from',from);if(to)params.set('date_to',to)
  }
  for(const [id,key] of [['partner-channel','channel_id'],['partner-lead-status','lead_status'],['partner-payment-status','payment_status']]){const value=document.querySelector(`#${id}`).value;if(value)params.set(key,value)}
  return params.toString()
}
function renderPartnerSummary(){
  const metrics=state.partnerData.metrics
  document.querySelector('#partner-summary').hidden=false
  document.querySelector('#partner-filters').hidden=false
  document.querySelector('#partner-active').textContent=metrics.active
  document.querySelector('#partner-opened').textContent=metrics.opened_banks
  document.querySelector('#partner-estimated').textContent=money(metrics.estimated_payout)
  document.querySelector('#partner-confirmed').textContent=money(metrics.confirmed_payout)
  document.querySelector('#partner-paid').textContent=money(metrics.paid)
  document.querySelector('#partner-closed').textContent=metrics.closed
  document.querySelector('#lead-search').placeholder='Имя, username или номер'
  const channelSelect=document.querySelector('#partner-channel'), selected=channelSelect.value
  channelSelect.innerHTML='<option value="">Все каналы</option>'+state.channels.map(channel=>`<option value="${channel.id}">${esc(channel.name)}</option>`).join('')
  channelSelect.value=selected
  const custom=document.querySelector('#partner-period').value==='custom'
  document.querySelector('#partner-date-from').hidden=!custom
  document.querySelector('#partner-date-to').hidden=!custom
  document.querySelector('.primary-stat span').textContent='Подтверждённые лиды'
  const labels=document.querySelectorAll('.stat-grid span')
  ;['Приняты в работу','Активные','Банки в плане','Завершённые'].forEach((label,index)=>labels[index].textContent=label)
}
function render(){
  const admin=state.session.role==='admin', partnerRole=state.session.role==='partner', employee=admin||state.session.role==='manager'
  document.querySelector('#loading-state').hidden=true
  document.querySelector('.tabbar').hidden=false
  document.querySelectorAll('#client-application-tab, #client-banks-tab').forEach(item=>item.hidden=true)
  document.querySelector('#greeting').textContent=state.session.name
  document.querySelector('#avatar').textContent=initials(state.session.name)||'Р'
  for(const key of ['total','new','active','unresolved','repeats']) document.querySelector(`#${key}-count`).textContent=state.dashboard[key]
  document.querySelector('#duplicate-count').textContent=state.dashboard.duplicates||0
  document.querySelector('#open-duplicate-reviews').hidden=!admin
  renderLeads(state.leads.slice(0,5),document.querySelector('#recent-leads')); renderLeads(state.leads,document.querySelector('#all-leads')); updateLeadCount(state.leads.length)
  document.querySelector('#partners-tab').hidden=!(admin||partnerRole); document.querySelector('#banks-tab').hidden=!employee; document.querySelector('#team-tab').hidden=!employee
  document.querySelector('#scope-filter').hidden=state.session.role!=='manager'
  document.querySelector('#add-bank-button').hidden=true; document.querySelector('#add-staff-button').hidden=!admin; document.querySelector('#add-channel-button').hidden=!partnerRole
  document.querySelector('#bank-sheet-links').hidden=!admin
  document.querySelector('#open-google-sheet').hidden=!admin||!state.session.google_sheet_url
  document.querySelector('.tabbar').style.setProperty('--tab-count',admin?5:employee?4:3)
  document.querySelector('#partners-tab-label').textContent=partnerRole?'Каналы':'Партнёры'; document.querySelector('#partners-title').textContent=partnerRole?'Каналы':'Партнёры'; document.querySelector('#partners-eyebrow').textContent=partnerRole?'Источники твоего трафика':'Источники заявок'
  document.querySelector('#partners-list').innerHTML=partnerRole?(state.channels.length?state.channels.map(channel=>`<button class="list-row" type="button" data-copy-channel="${esc(channel.link)}"><span class="row-icon partner">${initials(channel.name)||'К'}</span><span class="row-content"><span class="row-title"><strong>${esc(channel.name)}</strong></span><span class="row-subtitle">${esc(channel.link)}</span></span><b>Скопировать</b></button>`).join(''):'<p class="empty">Добавь первый канал и получи ссылку для лидов</p>'):(state.partners.length?state.partners.map(p=>`<button class="list-row" type="button" data-partner="${p.id}"><span class="row-icon partner">${initials(p.name)||'П'}</span><span class="row-content"><span class="row-title"><strong>${esc(p.name)}</strong></span><span class="row-subtitle">${esc(p.commission)}% · каналов: ${p.channels}</span></span><i class="status-dot ${p.active?'':'off'}"></i></button>`).join(''):'<p class="empty">Партнёров пока нет</p>')
  document.querySelector('#banks-list').innerHTML=state.banks.length?state.banks.map(b=>`<div class="list-row"><span class="row-icon">Б</span><span class="row-content"><span class="row-title"><strong>${esc(b.name)}</strong></span><span class="row-subtitle">${esc(b.online_text||'Уточняется')} · ${b.active?'доступен':'отключён'}${admin&&b.lead_payout!==null?` · лиду ${money(b.lead_payout)}`:''}</span></span><i class="status-dot ${b.active?'':'off'}"></i></div>`).join(''):'<p class="empty">Справочник пока не синхронизирован</p>'
  document.querySelector('#staff-list').innerHTML=state.staff.length?state.staff.map(p=>`<button class="list-row" type="button" data-staff="${p.id}"><span class="row-icon partner">${p.role==='admin'?'А':'М'}</span><span class="row-content"><span class="row-title"><strong>${esc(p.username||p.telegram_id)}</strong></span><span class="row-subtitle">${p.role==='admin'?'Администратор':'Менеджер'} · ${p.status==='pending'?'ожидает первого входа':p.status==='active'?'доступ включён':'доступ отключён'}</span></span><i class="status-dot ${p.status==='active'?'':'off'}"></i></button>`).join(''):'<p class="empty">Сотрудников пока нет</p>'
  if(partnerRole)renderPartnerSummary();else{document.querySelector('#partner-summary').hidden=true;document.querySelector('#partner-filters').hidden=true}
  if(!document.querySelector('.screen.is-active'))showScreen(state.currentScreen)
}
function renderLeadCabinet(){
  const application=state.leadApplication
  const canSelect=application.workflow_stage==='awaiting_client_selection'
  document.querySelector('#loading-state').hidden=true
  document.querySelector('.tabbar').hidden=false
  document.querySelector('#greeting').textContent='Кабинет клиента'
  document.querySelector('#avatar').textContent=initials(state.session.name)||'К'
  document.querySelectorAll('.tabbar button').forEach(item=>item.hidden=true)
  document.querySelector('#client-application-tab').hidden=false
  document.querySelector('#client-banks-tab').hidden=false
  document.querySelector('.tabbar').style.setProperty('--tab-count',2)
  document.querySelector('#client-application-id').textContent=`${application.short_id}${application.is_repeat?' · Повторная':''}`
  const manager=application.manager_url
    ? `<a class="contact-row" href="${esc(application.manager_url)}" target="_blank" rel="noopener"><span><small>Менеджер</small><strong>${esc(application.manager)}</strong></span><b>Написать</b></a>`
    : `<div class="value-row"><span>Менеджер</span><strong>${esc(application.manager||'Ещё не назначен')}</strong></div>`
  document.querySelector('#client-application-card').innerHTML=`<section class="client-hero"><span>Этап заявки</span><strong>${esc(workflowLabels[application.workflow_stage]||leadLabels[application.status]||application.status)}</strong><small>Обновлено ${dateTime(application.updated)}</small></section><section class="detail-section"><h3>Данные заявки</h3><div class="value-row"><span>Номер</span><strong>${esc(application.short_id)}</strong></div><div class="value-row"><span>Создана</span><strong>${date(application.date)}</strong></div>${manager}</section><p class="client-note">Здесь отображается актуальный этап работы с заявкой.</p>`
  const cards=state.leadBanks.map(item=>`<label class="client-bank-card ${canSelect?'is-selectable':''}">${canSelect?`<input class="bank-choice" type="checkbox" value="${esc(item.bank_id)}">`:''}<header><span class="client-bank-icon">${esc(initials(item.bank).slice(0,1)||'Б')}</span><div><h3>${esc(item.bank)}</h3><p>${canSelect?'Доступен для открытия':esc(bankLabels[item.status]||item.status)} · ${esc(item.online_text||'Онлайн уточняется')}</p></div><strong class="bank-payout">${money(item.lead_payout)}</strong>${canSelect?'<span class="choice-mark">✓</span>':''}</header><section class="activation-action"><span>Условие активации</span><p>${esc(item.action_text||'Условие уточняется')}</p></section><small>Обновлено ${dateTime(item.updated)}</small></label>`).join('')
  const emptyText=application.workflow_stage==='not_eligible'?'По текущим условиям подбор банков недоступен.':'Когда специалист сформирует доступные варианты, они появятся здесь.'
  document.querySelector('#client-banks-list').innerHTML=state.leadBanks.length?`${canSelect?'<p class="selection-intro">Отметь все банки, которые хочешь открыть.</p>':''}${cards}${canSelect?'<button class="primary-button selection-submit" id="submit-bank-selection">Продолжить</button>':''}`:`<section class="empty-card"><span class="client-bank-icon">Б</span><h3>Банки пока недоступны</h3><p>${emptyText}</p></section>`
  document.querySelector('#submit-bank-selection')?.addEventListener('click',confirmLeadBankSelection)
  showScreen('client-application')
}
function confirmLeadBankSelection(){
  const selected=[...document.querySelectorAll('.bank-choice:checked')].map(input=>input.value)
  if(!selected.length)return toast('Выбери хотя бы один банк')
  const names=state.leadBanks.filter(item=>selected.includes(item.bank_id)).map(item=>item.bank)
  openSheet('Проверь выбор','Перед отправкой',`<section class="detail-section"><h3>Выбранные банки</h3>${names.map(name=>`<div class="value-row"><span>Банк</span><strong>${esc(name)}</strong></div>`).join('')}</section><p class="confirmation-note">После отправки изменить список самостоятельно нельзя. Если передумаешь — сообщи менеджеру.</p><button class="primary-button" id="confirm-bank-selection">Отправить менеджеру</button>`)
  document.querySelector('#confirm-bank-selection').addEventListener('click',async()=>{try{await api('/api/lead/banks/selection',{method:'POST',body:JSON.stringify({bank_ids:selected})});closeSheet();toast('Выбор отправлен менеджеру');await load()}catch(error){toast(error.message)}})
}
async function load(){
  await waitForTelegramContext()
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
    if(state.session.role==='partner'){
      state.channels=await api('/api/channels')
      state.partnerData=await api(`/api/partner/cabinet?${partnerQuery()}`)
      const metrics=state.partnerData.metrics
      Object.assign(state,{leads:state.partnerData.leads,dashboard:{total:metrics.total,new:metrics.accepted,active:metrics.active,unresolved:metrics.planned_banks,repeats:metrics.completed,duplicates:0}})
      render();return
    }
    const employee=['admin','manager'].includes(state.session.role)
    const dashboard=await api('/api/dashboard')
    const loadedLeads=await api(`/api/leads${state.leadScope==='mine'?'?mine=true':''}`)
    const leads=state.session.role==='manager'&&state.leadScope==='queue'?loadedLeads.filter(lead=>lead.workflow_stage==='awaiting_manager'):loadedLeads
    Object.assign(state,{dashboard,leads});render()
    const optional=[
      ['partners',state.session.role==='admin'?'/api/partners':null],
      ['channels',['admin','partner'].includes(state.session.role)?'/api/channels':null],
      ['banks',employee?'/api/banks':null],
      ['staff',employee?'/api/staff':null],
      ['duplicates',state.session.role==='admin'?'/api/duplicate-reviews':null],
    ]
    for(const [key,path] of optional){
      if(!path)continue
      try{state[key]=await api(path);render()}catch(error){console.warn(`Не удалось загрузить ${key}`,error)}
    }
  }catch(error){ document.querySelector('#loading-state').hidden=true; document.querySelector('.tabbar').hidden=true; document.querySelectorAll('.screen').forEach(x=>x.classList.remove('is-active')); document.querySelector('#error-message').textContent=error.message; document.querySelector('#error-state').hidden=false }
}

function sourceLabel(lead){
  if(lead.assignment_status==='confirmed')return `${lead.source_partner} · ${lead.source_channel}`
  if(lead.assignment_status==='direct')return 'Прямая заявка'
  return 'Источник требует проверки'
}
function sourceCard(lead){
  const audit=lead.source_updated_at?`<div class="value-row"><span>Последнее изменение</span><strong>${esc(lead.source_updated_by)} · ${dateTime(lead.source_updated_at)}</strong></div>`:''
  return `<section class="form-card"><h3>Источник заявки</h3><div class="value-row"><span>Текущий источник</span><strong>${esc(sourceLabel(lead))}</strong></div>${audit}<button class="secondary-button inset-button" id="change-source">Изменить источник</button></section>`
}
function openSourceEditor(lead){
  const options=state.channels.filter(channel=>channel.active).map(channel=>`<option value="${channel.id}" data-partner="${channel.partner_id}">${esc(channel.partner)} — ${esc(channel.name)}</option>`).join('')
  openSheet('Изменить источник',lead.short_id,`<section class="form-card"><div class="value-row"><span>Сейчас</span><strong>${esc(sourceLabel(lead))}</strong></div><label class="field"><span>Партнёрский канал</span><select id="source-channel"><option value="">Выберите канал</option>${options}</select></label></section><div class="button-stack"><button class="primary-button" id="prepare-source">Привязать канал</button><button class="secondary-button" id="prepare-direct">Отметить как прямую</button></div>`)
  document.querySelector('#prepare-source').addEventListener('click',()=>{const select=document.querySelector('#source-channel'),option=select.selectedOptions[0];if(!select.value)return toast('Выберите канал');confirmSourceChange(lead,{channel_id:select.value,partner_id:option.dataset.partner},option.textContent)})
  document.querySelector('#prepare-direct').addEventListener('click',()=>confirmSourceChange(lead,null,'Прямая заявка'))
}
function confirmSourceChange(lead,payload,label){
  openSheet('Подтвердить источник',lead.short_id,`<section class="detail-section"><h3>Проверь изменение</h3><div class="value-row"><span>Заявка</span><strong>${esc(lead.short_id)}</strong></div><div class="value-row"><span>Новый источник</span><strong>${esc(label)}</strong></div></section><p class="confirmation-note">Источник будет сразу сохранён как подтверждённый.</p><div class="button-stack"><button class="primary-button" id="confirm-source-change">Подтвердить</button><button class="secondary-button" id="cancel-source-change">Отмена</button></div>`)
  document.querySelector('#confirm-source-change').addEventListener('click',async()=>{const path=payload?`/api/leads/${lead.id}/source`:`/api/leads/${lead.id}/source/direct`;await api(path,{method:payload?'PUT':'POST',body:payload?JSON.stringify(payload):undefined});toast('Источник обновлён');await load();await openLead(lead.id)})
  document.querySelector('#cancel-source-change').addEventListener('click',()=>openSourceEditor(lead))
}
function bankCard(item,employee,admin){
  const options=Object.entries(bankLabels).slice(0,10).map(([v,l])=>`<option value="${v}" ${item.status===v?'selected':''}>${l}</option>`).join('')
  const edit=employee?`<label class="field"><span>Статус</span><select data-bank-status>${options}</select></label><div class="field-row"><label class="field"><span>Доход, прогноз</span><input type="number" data-estimate value="${item.income_estimate||''}"></label><label class="field"><span>Доход, факт</span><input type="number" data-fact value="${item.income_fact||''}"></label></div><label class="field"><span>Причина закрытия</span><input data-reason value="${esc(item.close_reason||'')}"></label><button class="secondary-button" data-save-bank="${item.id}">Сохранить банк</button>`:`<div class="value-row"><span>Статус</span><strong>${esc(bankLabels[item.status]||item.status)}</strong></div>`
  const confirm=admin&&item.payment_status==='awaiting_confirmation'?`<button class="primary-button" data-confirm-pay="${item.id}">Подтвердить выплату</button>`:''
  const next=admin&&item.payment_id&&['confirmed','in_registry'].includes(item.payment_status)?`<button class="primary-button" data-next-pay="${item.payment_id}" data-current="${item.payment_status}">${item.payment_status==='confirmed'?'Добавить в реестр':'Отметить выплаченной'}</button>`:''
  const clientView=employee?`<div class="value-row"><span>Клиенту доступен</span><strong>${item.offered_to_lead?'Да':'Нет'}</strong></div><div class="value-row"><span>Выбор клиента</span><strong>${item.selected_by_lead===true?'Выбран':item.selected_by_lead===false?'Не выбран':'Не подтверждён'}</strong></div><div class="value-row"><span>Условие активации</span><strong>${esc(item.action_text||'Не заполнено')}</strong></div>`:''
  const economics=employee?`<div class="value-row"><span>Выплата лиду</span><strong>${money(item.lead_reward_fact||item.lead_reward_estimate)}</strong></div><div class="value-row"><span>Выплата партнёру</span><strong>${money(item.reward_fact||item.reward_estimate)}</strong></div>${admin?`<div class="value-row"><span>Командная прибыль</span><strong class="money">${money(item.team_profit_fact||item.team_profit_estimate)}</strong></div>`:''}`:''
  return `<article class="bank-card" data-bank-card="${item.id}"><header><h4>${esc(item.bank)}</h4><span>${esc(payLabels[item.payment_status]||item.payment_status)}</span></header>${clientView}${edit}${economics}<div class="button-stack">${confirm}${next}</div></article>`
}
async function openLead(id){
  if(state.session.role==='partner')return openPartnerLead(id)
  try{
    const lead=await api(`/api/leads/${id}`), partner=state.session.role==='partner', admin=state.session.role==='admin', editable=!partner&&!lead.archived
    const managerRole=state.session.role==='manager'
    const canManageBanks=editable&&((admin&&lead.is_primary_admin&&['admin_processing','awaiting_client_selection'].includes(lead.workflow_stage))||(managerRole&&lead.is_assigned_manager&&lead.workflow_stage==='manager_processing'))
    const statusButtons=internalLeadStatuses.map(value=>`<button type="button" class="status-option ${lead.status===value?'is-selected':''}" data-lead-status="${value}" aria-pressed="${lead.status===value}">${esc(leadLabels[value])}</button>`).join('')
    const username=String(lead.username||'').replace(/^@/,'')
    const telegramLink=/^[A-Za-z0-9_]{5,}$/.test(username)?`https://t.me/${username}`:''
    const phoneLink=String(lead.phone||'').replace(/[^+\d]/g,'')
    const contacts=partner?'':`<section class="detail-section"><h3>Контакты</h3><a class="contact-row" href="tel:${esc(phoneLink)}"><span><small>Телефон</small><strong>${esc(lead.phone||'Не указан')}</strong></span><b aria-hidden="true">Позвонить</b></a>${lead.email?`<a class="contact-row" href="mailto:${esc(lead.email)}"><span><small>E-mail</small><strong>${esc(lead.email)}</strong></span><b>Написать</b></a>`:''}${telegramLink?`<a class="contact-row" href="${esc(telegramLink)}" target="_blank" rel="noopener"><span><small>Telegram</small><strong>@${esc(username)}</strong></span><b aria-hidden="true">Открыть</b></a>`:`<div class="value-row"><span>Telegram</span><strong>${esc(lead.username||lead.telegram_id||'Не указан')}</strong></div>`}</section>`
    const answers=partner?'':Object.entries(lead.answers||{}).map(([key,value])=>`<div class="value-row"><span>${esc(questionLabels[key]||key)}</span><strong>${esc(answer(value))}</strong></div>`).join('')
    const statusEditor=editable?`<section class="detail-section status-section"><h3>Статус заявки</h3><details><summary><span><small>Текущий статус</small><strong>${esc(leadLabels[lead.status]||lead.status)}</strong></span><b>Изменить</b></summary><div class="status-grid">${statusButtons}</div></details></section>`:''
    const edit=editable?`<section class="detail-section"><h3>Работа с заявкой</h3><label class="field"><span>Внутренний комментарий</span><textarea id="lead-comment" placeholder="Заметка для команды">${esc(lead.comment||'')}</textarea></label><button class="primary-button inset-button" id="save-lead">Сохранить комментарий</button></section>`:''
    const workflowActions=!lead.archived&&(admin&&lead.workflow_stage==='awaiting_admin'?'<button class="primary-button inset-button" id="claim-admin">Взять в первичную работу</button>':managerRole&&lead.workflow_stage==='awaiting_manager'?'<button class="primary-button inset-button" id="claim-manager">Взять в сопровождение</button>':admin&&lead.is_primary_admin&&['admin_processing','awaiting_client_selection'].includes(lead.workflow_stage)?'<button class="primary-button inset-button" id="publish-banks">Открыть банки клиенту</button>':'')
    const workflow=`<section class="detail-section"><h3>Этап обработки</h3><div class="value-row"><span>Стадия</span><strong>${esc(workflowLabels[lead.workflow_stage]||lead.workflow_stage)}</strong></div><div class="value-row"><span>Первичный ответственный</span><strong>${esc(lead.primary_admin||'Не назначен')}</strong></div><div class="value-row"><span>Менеджер сопровождения</span><strong>${esc(lead.manager||'Не назначен')}</strong></div>${workflowActions}</section>`
    const banks=lead.banks.map(x=>bankCard(x,editable,admin&&!lead.archived)).join('')
    const application=`<section class="detail-section"><h3>${lead.archived?'Архивная заявка':'Заявка'}</h3><div class="value-row"><span>Создана</span><strong>${dateTime(lead.date)}</strong></div><div class="value-row"><span>Обновлена</span><strong>${dateTime(lead.updated)}</strong></div><div class="value-row"><span>Источник</span><strong>${esc(lead.channel)}</strong></div><div class="value-row"><span>Менеджер</span><strong>${esc(lead.manager)}</strong></div>${partner?'':`<div class="value-row"><span>Согласие на данные</span><strong>${lead.consent?'Получено':'Нет'}${lead.consent_at?` · ${date(lead.consent_at)}`:''}</strong></div>`}</section>`
    const questionnaire=partner||!answers?'':`<section class="detail-section"><h3>Анкета</h3>${answers}</section>`
    const history=partner||!lead.previous_applications?.length?'':`<section class="detail-section"><h3>Предыдущие заявки</h3>${lead.previous_applications.map(previous=>`<button class="list-row" type="button" data-lead="${previous.id}"><span class="row-icon">${previous.is_repeat?'П':'А'}</span><span class="row-content"><span class="row-title"><strong>${esc(previous.short_id)}</strong><time>${date(previous.date).slice(0,5)}</time></span><span class="row-subtitle">${previous.is_repeat?'Повторная · ':''}${esc(leadLabels[previous.status]||previous.status)}</span></span></button>`).join('')}</section>`
    openSheet(lead.name,`${lead.short_id} · ${lead.is_repeat?'Повторная · ':''}${lead.archived?'Архив · ':''}${workflowLabels[lead.workflow_stage]||leadLabels[lead.status]||lead.status}`,`${contacts}${workflow}${application}${statusEditor}${questionnaire}${history}${edit}${admin&&!lead.archived?sourceCard(lead):''}<div class="list-heading"><h3>Банки</h3>${canManageBanks?'<button id="add-lead-bank">Добавить</button>':''}</div>${banks||'<p class="empty">Банки не добавлены</p>'}`)
    bindLeadActions(lead,admin)
  }catch(error){ toast(error.message) }
}
function openPartnerLead(id){
  const lead=state.partnerData.leads.find(item=>item.id===id)
  if(!lead)return toast('Заявка не найдена')
  const username=String(lead.username||'').replace(/^@/,'')
  const telegram=/^[A-Za-z0-9_]{5,}$/.test(username)?`<a class="contact-row" href="https://t.me/${esc(username)}" target="_blank" rel="noopener"><span><small>Telegram клиента</small><strong>@${esc(username)}</strong></span><b>Открыть</b></a>`:'<div class="value-row"><span>Telegram клиента</span><strong>Не указан</strong></div>'
  const contact=state.partnerData.contact
  const admin=contact.url?`<a class="contact-row" href="${esc(contact.url)}" target="_blank" rel="noopener"><span><small>Ваш администратор</small><strong>${esc(contact.name)}</strong></span><b>Написать</b></a>`:`<div class="value-row"><span>Ваш администратор</span><strong>Ещё не назначен</strong></div>`
  const counts=lead.bank_counts||{}
  const banks=lead.banks.map(bank=>`<article class="bank-card"><header><h4>${esc(bank.bank)}</h4><span>${esc(payLabels[bank.payment_status]||bank.payment_status)}</span></header><div class="value-row"><span>Статус банка</span><strong>${esc(bankLabels[bank.status]||bank.status)}</strong></div><div class="value-row"><span>Расчётная выплата</span><strong>${money(bank.reward_estimate)}</strong></div><div class="value-row"><span>Подтверждённая выплата</span><strong>${money(bank.reward_fact)}</strong></div></article>`).join('')
  openSheet(lead.name,`${lead.short_id} · ${lead.is_repeat?'Повторная · ':''}${leadLabels[lead.status]||lead.status}`,`<section class="detail-section"><h3>Карточка лида</h3><div class="value-row"><span>Номер</span><strong>${esc(lead.short_id)}</strong></div><div class="value-row"><span>Дата заявки</span><strong>${dateTime(lead.date)}</strong></div><div class="value-row"><span>Последнее обновление</span><strong>${dateTime(lead.updated)}</strong></div><div class="value-row"><span>Канал</span><strong>${esc(lead.channel)}</strong></div><div class="value-row"><span>Статус</span><strong>${esc(leadLabels[lead.status]||lead.status)}</strong></div>${telegram}${admin}</section><section class="detail-section"><h3>Банки и выплаты</h3><div class="value-row"><span>Открыто / в работе / запланировано</span><strong>${counts.opened||0} / ${counts.in_progress||0} / ${counts.planned||0}</strong></div><div class="value-row"><span>Не будет открыто</span><strong>${counts.will_not_open||0}</strong></div><div class="value-row"><span>Расчётная выплата всего</span><strong>${money(lead.reward_estimate)}</strong></div><div class="value-row"><span>Подтверждено всего</span><strong>${money(lead.reward_fact)}</strong></div></section>${banks||'<p class="empty">Банки пока не добавлены</p>'}`)
}
function bindLeadActions(lead,admin){
  document.querySelector('#claim-admin')?.addEventListener('click',async()=>{await api(`/api/leads/${lead.id}/claim-admin`,{method:'POST',body:'{}'});toast('Заявка закреплена за тобой');await load();await openLead(lead.id)})
  document.querySelector('#publish-banks')?.addEventListener('click',async()=>{await api(`/api/leads/${lead.id}/banks/publish`,{method:'POST',body:'{}'});toast('Банки открыты клиенту');await load();await openLead(lead.id)})
  document.querySelector('#claim-manager')?.addEventListener('click',async()=>{await api(`/api/leads/${lead.id}/claim-manager`,{method:'POST',body:'{}'});toast('Лид взят в сопровождение');await load();await openLead(lead.id)})
  document.querySelectorAll('[data-lead-status]').forEach(button=>button.addEventListener('click',async()=>{ if(button.dataset.leadStatus===lead.status)return; document.querySelectorAll('[data-lead-status]').forEach(item=>item.disabled=true); await api(`/api/leads/${lead.id}`,{method:'PATCH',body:JSON.stringify({internal_status:button.dataset.leadStatus})}); toast('Статус изменён'); await openLead(lead.id); await load() }))
  document.querySelector('#save-lead')?.addEventListener('click',async()=>{ await api(`/api/leads/${lead.id}`,{method:'PATCH',body:JSON.stringify({update_manager:false,internal_comment:document.querySelector('#lead-comment').value,update_comment:true})}); toast('Комментарий сохранён'); await openLead(lead.id); await load() })
  document.querySelector('#change-source')?.addEventListener('click',()=>openSourceEditor(lead))
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
  const admins=state.staff.filter(item=>item.role==='admin'&&item.status==='active').map(item=>`<option value="${item.id}" ${p.assigned_admin_id===item.id?'selected':''}>${esc(item.username||item.telegram_id)}</option>`).join('')
  openSheet(p.name,'Партнёр и каналы',`<section class="detail-section"><h3>Реферальные ссылки</h3>${links}</section><section class="form-card"><h3>Настройки партнёра</h3><label class="field"><span>Ответственный администратор</span><select id="partner-admin"><option value="">Не назначен</option>${admins}</select></label><button class="secondary-button inset-button" id="save-partner-admin">Сохранить администратора</button><label class="field"><span>Процент партнёра</span><input id="partner-commission" inputmode="decimal" value="${esc(p.commission)}"></label><button class="secondary-button inset-button" id="save-commission">Сохранить процент</button><div class="value-row"><span>Telegram</span><strong>${esc(telegram)}</strong></div><label class="field"><span>Telegram ID</span><input id="partner-id" inputmode="numeric" value="${esc(p.telegram_id||'')}" placeholder="Например, 123456789"></label><label class="field"><span>Username без @</span><input id="partner-user" value="${esc(username)}" placeholder="Например, gerasimov"></label><p class="field-note">Username привяжется при первом входе партнёра. Telegram ID можно указать сразу, если он известен.</p><button class="primary-button inset-button" id="save-partner">Сохранить доступ</button></section><section class="destructive-section"><button class="danger-button" id="show-remove-partner">Убрать партнёра</button><div id="remove-partner-confirm" hidden><p>Партнёр и его каналы будут удалены. Если уже есть заявки, удаление не выполнится.</p><div class="button-stack"><button class="danger-button" id="remove-partner">Да, удалить</button><button class="secondary-button" id="cancel-remove-partner">Отмена</button></div></div></section>`)
  document.querySelector('#save-partner-admin').addEventListener('click',async()=>{const value=document.querySelector('#partner-admin').value;await api(`/api/partners/${id}`,{method:'PATCH',body:JSON.stringify({assigned_admin_id:value||null,update_assigned_admin:true})});toast('Администратор сохранён');await load();openPartner(id)})
  document.querySelector('#save-commission').addEventListener('click',async()=>{await api(`/api/partners/${id}`,{method:'PATCH',body:JSON.stringify({commission_percent:document.querySelector('#partner-commission').value.replace(',','.')})});toast('Процент сохранён');await load();openPartner(id)})
  document.querySelector('#save-partner').addEventListener('click',async()=>{const telegramId=document.querySelector('#partner-id').value.trim(),telegramUsername=document.querySelector('#partner-user').value.trim();if(telegramId){await api(`/api/partners/${id}/access`,{method:'PUT',body:JSON.stringify({telegram_id:telegramId,telegram_username:telegramUsername||null})});toast('Доступ настроен')}else{if(!telegramUsername)return toast('Укажи username или Telegram ID');await api(`/api/partners/${id}`,{method:'PATCH',body:JSON.stringify({telegram_username:telegramUsername})});toast('Username сохранён')}await load();openPartner(id)})
  document.querySelector('#show-remove-partner').addEventListener('click',()=>{document.querySelector('#show-remove-partner').hidden=true;document.querySelector('#remove-partner-confirm').hidden=false})
  document.querySelector('#cancel-remove-partner').addEventListener('click',()=>{document.querySelector('#show-remove-partner').hidden=false;document.querySelector('#remove-partner-confirm').hidden=true})
  document.querySelector('#remove-partner').addEventListener('click',async()=>{try{await api(`/api/partners/${id}`,{method:'DELETE'});toast('Партнёр удалён');closeSheet();await load()}catch(error){toast(error.message)}})
}
function openDuplicateQueue(){
  const rows=state.duplicates.map(item=>`<button class="list-row" type="button" data-duplicate="${item.id}"><span class="row-icon">Д</span><span class="row-content"><span class="row-title"><strong>${esc(item.name)}</strong><time>${date(item.date).slice(0,5)}</time></span><span class="row-subtitle">${esc(item.phone)} · исходная ${esc(item.original?.short_id||'не найдена')}</span></span><i class="status-dot off"></i></button>`).join('')
  openSheet('Дубли на проверке','Только для администраторов',`<div class="telegram-list">${rows||'<p class="empty">Непроверенных дублей нет</p>'}</div>`)
}
function openDuplicate(id){
  const item=state.duplicates.find(review=>review.id===id)
  if(!item)return openDuplicateQueue()
  const original=item.original?`<div class="value-row"><span>Заявка</span><strong>${esc(item.original.short_id)}</strong></div><div class="value-row"><span>ФИО</span><strong>${esc(item.original.name)}</strong></div><div class="value-row"><span>Telegram</span><strong>${esc(item.original.username||'Не указан')}</strong></div>`:'<p class="empty">Исходная заявка не найдена</p>'
  const answers=Object.entries(item.answers).map(([key,value])=>`<div class="value-row"><span>${esc(questionLabels[key]||key)}</span><strong>${esc(answer(value))}</strong></div>`).join('')
  openSheet(item.name,'Возможный дубль',`<section class="detail-section"><h3>Исходная заявка</h3>${original}</section><section class="detail-section"><h3>Новая попытка</h3><div class="value-row"><span>Telegram</span><strong>${esc(item.username||item.telegram_id)}</strong></div><div class="value-row"><span>Телефон</span><strong>${esc(item.phone)}</strong></div><div class="value-row"><span>Реферальная метка</span><strong>${esc(item.referral_code||'Прямой вход')}</strong></div>${answers}</section><div class="button-stack"><button class="primary-button" data-resolve-duplicate="duplicate">Это дубль</button><button class="secondary-button" data-resolve-duplicate="separate_lead">Это другой клиент</button><button class="secondary-button" data-resolve-duplicate="update_original">Обновить исходного лида</button></div>`)
  document.querySelectorAll('[data-resolve-duplicate]').forEach(button=>button.addEventListener('click',()=>confirmDuplicateResolution(item,button.dataset.resolveDuplicate)))
}
function confirmDuplicateResolution(item,resolution){
  const labels={duplicate:'Отклонить новую попытку как дубль',separate_lead:'Создать отдельную заявку',update_original:'Заменить данные исходной заявки'}
  openSheet('Подтвердить решение',item.name,`<section class="detail-section"><h3>Решение администратора</h3><div class="value-row"><span>Действие</span><strong>${esc(labels[resolution])}</strong></div></section><p class="confirmation-note">Операция сразу закроет проверку дубля.</p><div class="button-stack"><button class="primary-button" id="confirm-duplicate-resolution">Подтвердить</button><button class="secondary-button" id="cancel-duplicate-resolution">Отмена</button></div>`)
  document.querySelector('#confirm-duplicate-resolution').addEventListener('click',async()=>{await api(`/api/duplicate-reviews/${item.id}/resolve`,{method:'POST',body:JSON.stringify({resolution})});toast('Решение сохранено');await load();openDuplicateQueue()})
  document.querySelector('#cancel-duplicate-resolution').addEventListener('click',()=>openDuplicate(item.id))
}
function showScreen(name){ state.currentScreen=name;document.querySelectorAll('.screen').forEach(x=>x.classList.toggle('is-active',x.id===`${name}-screen`));document.querySelectorAll('[data-screen]').forEach(x=>x.classList.toggle('is-active',x.dataset.screen===name));window.scrollTo({top:0,behavior:'smooth'}) }

document.addEventListener('click',async event=>{ const lead=event.target.closest('[data-lead]'),partner=event.target.closest('[data-partner]'),channel=event.target.closest('[data-copy-channel]'),staff=event.target.closest('[data-staff]'),duplicate=event.target.closest('[data-duplicate]'),sheetLink=event.target.closest('[data-sheet-link]');try{if(lead)await openLead(lead.dataset.lead);if(partner)openPartner(partner.dataset.partner);if(channel)await copyText(channel.dataset.copyChannel);if(staff&&state.session.role==='admin'){await api(`/api/staff/${staff.dataset.staff}/toggle`,{method:'POST'});toast('Доступ изменён');await load()}if(duplicate)openDuplicate(duplicate.dataset.duplicate);if(sheetLink){const url=state.session?.[sheetLink.dataset.sheetLink];if(url){const tg=telegramWebApp();tg?.openLink?tg.openLink(url):window.open(url,'_blank','noopener')}}}catch(error){toast(error.message)} })
document.querySelectorAll('[data-screen]').forEach(x=>x.addEventListener('click',()=>showScreen(x.dataset.screen)))
document.querySelectorAll('[data-go]').forEach(x=>x.addEventListener('click',()=>showScreen(x.dataset.go)))
document.querySelector('#close-sheet').addEventListener('click',closeSheet);document.querySelector('#sheet-backdrop').addEventListener('click',closeSheet);document.querySelector('#retry-button').addEventListener('click',load)
document.querySelector('#lead-search').addEventListener('input',event=>{const q=event.target.value.trim().toLowerCase(),items=state.leads.filter(x=>`${x.name} ${x.phone||''} ${x.username||''} ${x.short_id}`.toLowerCase().includes(q));renderLeads(items,document.querySelector('#all-leads'));updateLeadCount(items.length)})
document.querySelector('#lead-scope').addEventListener('change',async event=>{state.leadScope=event.target.value;await load()})
async function downloadReport(){try{const partner=state.session?.role==='partner',path=partner?`/api/partner/report.xlsx?${partnerQuery()}`:'/api/reports/leads.csv',response=await fetch(path,{headers:{'X-Telegram-Init-Data':telegramInitData()}});if(!response.ok)throw new Error('Не удалось сформировать отчёт');const link=document.createElement('a');link.href=URL.createObjectURL(await response.blob());link.download=partner?'rko-partner-report.xlsx':'rko-leads.csv';link.click();setTimeout(()=>URL.revokeObjectURL(link.href),1000);toast('Отчёт сформирован')}catch(error){toast(error.message)}}
document.querySelector('#download-report').addEventListener('click',downloadReport)
document.querySelector('#partner-report').addEventListener('click',downloadReport)
document.querySelector('#partner-contact').addEventListener('click',()=>{const url=state.partnerData?.contact?.url;if(!url)return toast('Администратор ещё не назначен');const tg=telegramWebApp();tg?.openTelegramLink?tg.openTelegramLink(url):window.open(url,'_blank','noopener')})
document.querySelectorAll('#partner-filters select').forEach(select=>select.addEventListener('change',load))
document.querySelectorAll('#partner-date-from, #partner-date-to').forEach(input=>input.addEventListener('change',load))
document.querySelectorAll('[data-partner-list]').forEach(button=>button.addEventListener('click',()=>{const mode=button.dataset.partnerList;let items=state.leads;if(mode==='active')items=items.filter(lead=>['new','in_progress','opening_accounts','partially_completed','paused'].includes(lead.status));if(mode==='opened')items=items.filter(lead=>Number(lead.bank_counts?.opened||0)>0);renderLeads(items,document.querySelector('#all-leads'));updateLeadCount(items.length);showScreen('leads')}))
document.querySelector('#open-google-sheet').addEventListener('click',()=>{const url=state.session?.google_sheet_url;if(!url)return;const tg=telegramWebApp();tg?.openLink?tg.openLink(url):window.open(url,'_blank','noopener')})
document.querySelector('#open-duplicate-reviews').addEventListener('click',openDuplicateQueue)
document.querySelector('#add-staff-button').addEventListener('click',()=>{openSheet('Новый сотрудник','Доступ','<section class="form-card"><label class="field"><span>Username без @</span><input id="staff-user" placeholder="Например, anutka_rko"></label><p class="field-note">Сотрудник получит доступ после первого запуска бота через /start.</p><label class="field"><span>Роль</span><select id="staff-role"><option value="manager">Менеджер</option><option value="admin">Администратор</option></select></label></section><button class="primary-button" id="create-staff">Добавить</button>');document.querySelector('#create-staff').addEventListener('click',async()=>{await api('/api/staff',{method:'POST',body:JSON.stringify({telegram_username:document.querySelector('#staff-user').value,role:document.querySelector('#staff-role').value})});toast('Приглашение добавлено');closeSheet();await load()})})
document.querySelector('#add-channel-button').addEventListener('click',()=>{openSheet('Новый канал','Источник трафика','<section class="form-card"><label class="field"><span>Название канала</span><input id="new-channel" maxlength="160" placeholder="Например, Telegram-канал"></label><p class="field-note">Для каждого источника создавай отдельный канал — так будет видно, откуда пришёл лид.</p></section><button class="primary-button" id="create-channel">Создать ссылку</button>');document.querySelector('#create-channel').addEventListener('click',async()=>{try{const created=await api('/api/channels',{method:'POST',body:JSON.stringify({name:document.querySelector('#new-channel').value})});await load();openSheet(created.name,'Канал создан',`<section class="detail-section"><h3>Ссылка для лидов</h3><div class="value-row"><span>Источник</span><strong>${esc(created.name)}</strong></div><div class="value-row"><span>Ссылка</span><strong>${esc(created.link)}</strong></div></section><button class="primary-button" id="copy-created-channel">Скопировать ссылку</button>`);document.querySelector('#copy-created-channel').addEventListener('click',()=>copyText(created.link))}catch(error){toast(error.message)}})})
load()
