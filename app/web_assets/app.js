function telegramWebApp(){return window.Telegram?.WebApp}
function telegramInitData(){
  const hashData=new URLSearchParams(window.location.hash.slice(1)).get('tgWebAppData')
  const queryData=new URLSearchParams(window.location.search).get('tgWebAppData')
  return telegramWebApp()?.initData||hashData||queryData||''
}
telegramWebApp()?.ready(); telegramWebApp()?.expand()

let telegramContextWaited=false
async function waitForTelegramContext(){
  if(telegramInitData()||telegramContextWaited)return
  telegramContextWaited=true
  for(let attempt=0;attempt<60&&!telegramInitData();attempt+=1){
    await new Promise(resolve=>setTimeout(resolve,100))
  }
  telegramWebApp()?.ready();telegramWebApp()?.expand()
}

const state = { session: null, dashboard: {}, leads: [], partners: [], channels: [], banks: [], banksLoading: false, banksError: false, staff: [], duplicates: [], leadApplication: null, leadBanks: [], leadAddingBanks: false, leadScope: 'queue', partnerData: null, currentScreen: 'summary' }
const leadLabels = { new:'Новая',manager_assigned:'Менеджер назначен',awaiting_first_contact:'Ждёт звонка',contacted:'Связались',awaiting_data:'Ждём данные',data_received:'Данные получены',selecting_banks:'Подбираем банки',preparing_applications:'Готовим заявки',applications_sent:'Заявки отправлены',opening_accounts:'Открытие счетов',partially_opened:'Часть счетов открыта',all_planned_opened:'Счета открыты',paused:'На паузе',no_response:'Нет ответа',lead_refused:'Отказ клиента',not_eligible:'Не подходит',completed:'Завершена',in_progress:'В работе',partially_completed:'Частично завершена',closed_without_result:'Закрыта без результата' }
const internalLeadStatuses = ['new','manager_assigned','awaiting_first_contact','contacted','awaiting_data','data_received','selecting_banks','preparing_applications','applications_sent','opening_accounts','partially_opened','all_planned_opened','paused','no_response','lead_refused','not_eligible','completed']
const questionLabels = { adult:'Совершеннолетие',has_ip:'ИП',city:'Город',full_name:'ФИО',email:'E-mail',has_bankruptcy_or_arrests:'Банкротства или аресты',is_civil_servant:'Госслужащий',has_social_benefits:'Социальные выплаты',no_bankruptcy:'Нет банкротств или арестов',not_civil_servant:'Не госслужащий',no_social_benefits:'Нет социальных выплат' }
const bankLabels = { planned:'Планируем открыть',awaiting_data:'Ждём данные от клиента',preparing_application:'Готовим заявку в банк',application_sent:'Заявка отправлена в банк',under_review:'Банк рассматривает заявку',revision_required:'Нужно дополнить данные',account_opened:'Счёт активирован',bank_rejected:'Банк отказал',client_refused:'Клиент отказался',excluded:'Банк исключён',in_progress:'Открытие в работе',opened:'Счёт активирован',not_opened:'Счёт не открыт',will_not_open:'Открывать не будем',lead_reward_paid:'Выплата сделана' }
const payLabels = { not_calculated:'Не рассчитана',calculated:'Рассчитана',awaiting_confirmation:'Ждёт подтверждения',confirmed:'Подтверждена',in_registry:'В реестре',paid:'Выплачена',cancelled:'Отменена' }
const workflowLabels = { awaiting_admin:'Ожидает администратора',admin_processing:'Первичная обработка',awaiting_client_selection:'Клиент выбирает банки',awaiting_manager:'Ожидает менеджера',manager_processing:'В работе у менеджера',not_eligible:'Не подходит' }
const clientWorkflowLabels = { awaiting_admin:'Заявка принята',admin_processing:'Подбираем подходящие банки',awaiting_client_selection:'Выберите банки',awaiting_manager:'Ожидаем менеджера',manager_processing:'Менеджер сопровождает заявку',not_eligible:'Пока не сможем помочь' }
const infoIcon='<svg class="info-icon" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9"></circle><path d="M12 10.5v6M12 7.5h.01"></path></svg>'

function jsonRequest(path, options={}){
  return new Promise((resolve,reject)=>{
    const request=new XMLHttpRequest()
    request.open((options.method||'GET').toUpperCase(),path,true)
    request.timeout=10000
    request.setRequestHeader('Content-Type','application/json')
    request.setRequestHeader('X-Telegram-Init-Data',telegramInitData())
    Object.entries(options.headers||{}).forEach(([name,value])=>request.setRequestHeader(name,value))
    request.onload=()=>{
      if(request.status>=200&&request.status<300){
        if(request.status===204)return resolve(null)
        try{return resolve(JSON.parse(request.responseText))}catch(error){return reject(new Error('Сервер вернул некорректные данные'))}
      }
      let message='Не удалось выполнить действие'
      try{message=JSON.parse(request.responseText).detail||message}catch(error){}
      reject(new Error(message))
    }
    request.ontimeout=()=>reject(new Error('Сервер отвечает слишком долго. Нажмите «Повторить».'))
    request.onerror=()=>reject(new Error('Нет связи с сервером. Проверьте интернет и нажмите «Повторить».'))
    request.send(options.body||null)
  })
}
async function api(path, options={}) {
  const attempts=(options.method||'GET').toUpperCase()==='GET'?2:1
  for(let attempt=1;attempt<=attempts;attempt+=1){
    try{
      return await jsonRequest(path,options)
    }catch(error){
      if(attempt===attempts){
        throw error
      }
      await new Promise(resolve=>setTimeout(resolve,400*attempt))
    }
  }
}
function esc(value){ const n=document.createElement('span'); n.textContent=value??''; return n.innerHTML }
function initials(name){ return String(name||'').split(/\s+/).filter(Boolean).slice(0,2).map(x=>x[0]).join('').toUpperCase() }
function date(value){ return value ? new Intl.DateTimeFormat('ru-RU').format(new Date(value)) : '—' }
function dateTime(value){ return value ? new Intl.DateTimeFormat('ru-RU',{dateStyle:'medium',timeStyle:'short'}).format(new Date(value)) : '—' }
function localISODate(){ const now=new Date(),pad=value=>String(value).padStart(2,'0');return `${now.getFullYear()}-${pad(now.getMonth()+1)}-${pad(now.getDate())}` }
function money(value){ return value===null||value===undefined||value==='' ? '—' : `${new Intl.NumberFormat('ru-RU').format(Number(value))} ₽` }
function leadPayout(item){ const value=money(item.lead_payout);return item.lead_payout_paid_separately?`до ${value}`:value }
function answer(value){ if(value===true||value==='yes'||value==='Да')return 'Да';if(value===false||value==='no'||value==='Нет')return 'Нет';return value||'—' }
function sentence(value,fallback){ const text=String(value||fallback).trim();return text?text[0].toUpperCase()+text.slice(1):fallback }
function toast(message){ const el=document.querySelector('#toast'); el.textContent=message; el.hidden=false; clearTimeout(toast.timer); toast.timer=setTimeout(()=>el.hidden=true,2400) }
function openSheet(title, eyebrow, html){ document.querySelector('#sheet-title').textContent=title; document.querySelector('#sheet-eyebrow').textContent=eyebrow; document.querySelector('#sheet-content').innerHTML=html; document.querySelector('#sheet-backdrop').hidden=false; document.querySelector('#bottom-sheet').hidden=false }
function closeSheet(){ document.querySelector('#sheet-backdrop').hidden=true; document.querySelector('#bottom-sheet').hidden=true }
function showOnlineHelp(text){openSheet('Открытие онлайн','Условия',`<section class="detail-section online-help-content"><p class="info-copy">${esc(text||'Условия онлайн-открытия уточняются')}</p></section><button class="primary-button" id="close-online-help">Понятно</button>`);document.querySelector('#close-online-help').addEventListener('click',closeSheet)}
async function copyText(value){
  if(navigator.clipboard?.writeText) await navigator.clipboard.writeText(value)
  else { const input=document.createElement('textarea');input.value=value;input.style.position='fixed';input.style.opacity='0';document.body.append(input);input.select();document.execCommand('copy');input.remove() }
  toast('Ссылка скопирована')
}
function referralLinks(item){
  if(Array.isArray(item?.links)&&item.links.length)return item.links
  return item?.link?[{bot:'Telegram',url:item.link}]:[]
}
function referralLinkRows(item){
  return referralLinks(item).map((link,index)=>`<section class="detail-section"><div class="value-row"><span>${esc(link.bot)}</span><strong>${esc(link.url)}</strong></div><button class="secondary-button inset-button" type="button" data-copy-referral-link="${index}">Скопировать ссылку</button></section>`).join('')
}
function bindReferralLinkCopies(item){
  const links=referralLinks(item)
  document.querySelectorAll('[data-copy-referral-link]').forEach(button=>button.addEventListener('click',()=>copyText(links[Number(button.dataset.copyReferralLink)].url)))
}

function leadRow(lead){
  const detail=state.session.role==='partner'?'':lead.phone
  const managerStatus=lead.workflow_stage==='awaiting_manager'?'Новая':lead.workflow_stage==='manager_processing'?'В работе':null
  const status=state.session.role==='partner'?(leadLabels[lead.status]||lead.status):state.session.role==='manager'&&managerStatus?managerStatus:(workflowLabels[lead.workflow_stage]||leadLabels[lead.status]||lead.status)
  const alert=state.session.role!=='partner'&&lead.workflow_stage==='not_eligible'
  return `<button class="list-row${alert?' is-not-eligible':''}" type="button" data-lead="${lead.id}"><span class="row-icon">${initials(lead.name)||'Р'}</span><span class="row-content"><span class="row-title"><strong>${esc(lead.name)}</strong><time>${date(lead.date).slice(0,5)}</time></span><span class="row-subtitle">${esc(lead.short_id)} · ${lead.is_repeat?'Повторная · ':''}${esc(status)}${detail?` · ${esc(detail)}`:''}</span></span></button>`
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
  document.querySelector('#partner-estimated').textContent=money(metrics.estimated_payout)
  document.querySelector('#partner-last-paid').textContent=money(metrics.last_payout)
  document.querySelector('#partner-paid').textContent=money(metrics.paid)
  document.querySelector('#partner-completed').textContent=metrics.completed
  document.querySelector('#partner-cancelled').textContent=metrics.cancelled
  document.querySelector('#lead-search').placeholder='Имя или номер заявки'
  const channelSelect=document.querySelector('#partner-channel'), selected=channelSelect.value
  channelSelect.innerHTML='<option value="">Все каналы</option>'+state.channels.map(channel=>`<option value="${channel.id}">${esc(channel.name)}</option>`).join('')
  channelSelect.value=selected
  const custom=document.querySelector('#partner-period').value==='custom'
  document.querySelector('#partner-date-range').hidden=!custom
  document.querySelector('.primary-stat span').textContent='Всего заявок'
  const labels=document.querySelectorAll('.stat-grid span')
  ;['Новые заявки','Заявки в работе','Счета в процессе открытия','Активированные счета'].forEach((label,index)=>labels[index].textContent=label)
}
function renderAdminFilters(){
  const panel=document.querySelector('#admin-filters'),partnerSelect=document.querySelector('#admin-partner'),channelSelect=document.querySelector('#admin-channel')
  panel.hidden=false
  const selectedPartner=partnerSelect.value
  partnerSelect.innerHTML='<option value="">Все источники</option>'+state.partners.map(partner=>`<option value="${partner.id}">${esc(partner.name)}</option>`).join('')
  if(state.partners.some(partner=>partner.id===selectedPartner))partnerSelect.value=selectedPartner
  const partnerId=partnerSelect.value, selectedChannel=channelSelect.value
  const channels=partnerId?state.channels.filter(channel=>channel.partner_id===partnerId):[]
  channelSelect.disabled=!partnerId
  channelSelect.innerHTML=partnerId?'<option value="">Все каналы партнёра</option>'+channels.map(channel=>`<option value="${channel.id}">${esc(channel.name)}</option>`).join(''):'<option value="">Сначала выберите партнёра</option>'
  if(channels.some(channel=>channel.id===selectedChannel))channelSelect.value=selectedChannel
  document.querySelector('#admin-date-range').hidden=document.querySelector('#admin-period').value!=='custom'
}
function filteredLeads(){
  const query=document.querySelector('#lead-search').value.trim().toLowerCase()
  let items=state.leads.filter(lead=>`${lead.name} ${lead.phone||''} ${lead.username||''} ${lead.short_id}`.toLowerCase().includes(query))
  if(state.session.role!=='admin')return items
  const partner=document.querySelector('#admin-partner').value,channel=document.querySelector('#admin-channel').value,status=document.querySelector('#admin-lead-status').value,payment=document.querySelector('#admin-payment-status').value,period=document.querySelector('#admin-period').value
  if(partner)items=items.filter(lead=>lead.source_partner_id===partner)
  if(channel)items=items.filter(lead=>lead.source_channel_id===channel)
  if(status)items=items.filter(lead=>lead.status===status)
  if(payment)items=items.filter(lead=>lead.payment_status===payment)
  let from='',to=''
  if(period==='month')from=monthStart()
  if(period==='custom'){from=document.querySelector('#admin-date-from').value;to=document.querySelector('#admin-date-to').value}
  if(from)items=items.filter(lead=>String(lead.date).slice(0,10)>=from)
  if(to)items=items.filter(lead=>String(lead.date).slice(0,10)<=to)
  return items
}
function renderVisibleLeads(){const items=filteredLeads();renderLeads(items,document.querySelector('#all-leads'));updateLeadCount(items.length)}
function render(){
  const admin=state.session.role==='admin', partnerRole=state.session.role==='partner', employee=admin||state.session.role==='manager'
  document.querySelector('#loading-state').hidden=true
  document.querySelector('.tabbar').hidden=false
  document.querySelectorAll('#client-application-tab, #client-banks-tab, #client-faq-tab').forEach(item=>item.hidden=true)
  document.querySelector('#greeting').textContent=state.session.name
  document.querySelector('#cabinet-label').textContent=admin?'Кабинет администратора':partnerRole?'Кабинет партнёра':'Кабинет менеджера'
  document.querySelector('#avatar').textContent=initials(state.session.name)||'Р'
  for(const key of ['total','new','active','unresolved','repeats']) document.querySelector(`#${key}-count`).textContent=state.dashboard[key]
  document.querySelector('#duplicate-count').textContent=state.dashboard.duplicates||0
  document.querySelector('#open-duplicate-reviews').hidden=!admin
  document.querySelectorAll('.stat-grid > div').forEach((item,index)=>{item.hidden=state.session.role==='manager'&&index>1})
  renderLeads(state.leads.slice(0,5),document.querySelector('#recent-leads'))
  document.querySelector('#partners-tab').hidden=!(admin||partnerRole); document.querySelector('#banks-tab').hidden=!admin; document.querySelector('#team-tab').hidden=!employee
  document.querySelector('#scope-filter').hidden=state.session.role!=='manager'
  document.querySelector('#add-bank-button').hidden=!admin; document.querySelector('#add-partner-button').hidden=!admin; document.querySelector('#add-staff-button').hidden=!admin; document.querySelector('#add-channel-button').hidden=!partnerRole
  document.querySelector('#bank-sheet-links').hidden=!admin
  document.querySelector('#open-google-sheet').hidden=!admin||!state.session.google_sheet_url
  document.querySelector('.tabbar').style.setProperty('--tab-count',admin?5:3)
  document.querySelector('#partners-tab-label').textContent=partnerRole?'Каналы':'Партнёры'; document.querySelector('#partners-title').textContent=partnerRole?'Каналы':'Партнёры'; document.querySelector('#partners-eyebrow').textContent=partnerRole?'Источники вашего трафика':'Источники заявок'
  document.querySelector('#partners-list').innerHTML=partnerRole?(state.channels.length?state.channels.map(channel=>`<button class="list-row" type="button" data-channel="${channel.id}"><span class="row-icon partner">${initials(channel.name)||'К'}</span><span class="row-content"><span class="row-title"><strong>${esc(channel.name)}</strong></span><span class="row-subtitle">${channel.active?'Работает':'Отключён'} · ${esc(channel.link)}</span></span><b>Открыть</b></button>`).join(''):'<p class="empty">Добавьте первый канал и получите ссылку для новых заявок</p>'):(state.partners.length?state.partners.map(p=>`<button class="list-row" type="button" data-partner="${p.id}"><span class="row-icon partner">${initials(p.name)||'П'}</span><span class="row-content"><span class="row-title"><strong>${esc(p.name)}</strong></span><span class="row-subtitle">${esc(p.commission)}% · каналов: ${p.channels}</span></span><i class="status-dot ${p.active?'':'off'}"></i></button>`).join(''):'<p class="empty">Партнёров пока нет</p>')
  document.querySelector('#banks-list').innerHTML=state.banksLoading?'<p class="empty">Загружаем справочник банков…</p>':state.banksError?'<p class="empty">Не удалось загрузить справочник. Откройте кабинет заново.</p>':state.banks.length?state.banks.map(b=>`<button class="list-row" type="button" ${admin?`data-catalog-bank="${b.id}"`:''}><span class="row-icon">Б</span><span class="row-content"><span class="row-title"><strong>${esc(b.name)}</strong></span><span class="row-subtitle">${b.online_available?'Можно онлайн':'Только очно'} · ${b.active?'доступен':'отключён'}${admin&&b.lead_payout!==null?` · клиенту ${money(b.lead_payout)}`:''}</span></span><i class="status-dot ${b.active?'':'off'}"></i></button>`).join(''):'<p class="empty">В справочнике пока нет банков</p>'
  document.querySelector('#staff-list').innerHTML=state.staff.length?state.staff.map(p=>{const username=String(p.username||'').replace(/^@/,'');const chat=/^[A-Za-z0-9_]{5,32}$/.test(username)?`<button class="staff-chat" type="button" data-telegram-chat="https://t.me/${esc(username)}">Написать</button>`:'';const toggle=admin?`<button class="staff-toggle" type="button" data-staff="${p.id}" aria-label="Изменить доступ"><i class="status-dot ${p.status==='active'?'':'off'}"></i></button>`:`<i class="status-dot ${p.status==='active'?'':'off'}"></i>`;return `<div class="list-row staff-row"><span class="row-icon partner">${p.role==='admin'?'А':'М'}</span><span class="row-content"><span class="row-title"><strong>${esc(p.username||p.telegram_id)}</strong></span><span class="row-subtitle">${p.role==='admin'?'Администратор':'Менеджер'} · ${p.status==='pending'?'ожидает первого входа':p.status==='active'?'доступ включён':'доступ отключён'}</span></span><span class="staff-actions">${chat}${toggle}</span></div>`}).join(''):'<p class="empty">Сотрудников пока нет</p>'
  document.querySelector('#admin-filters').hidden=!admin
  if(partnerRole)renderPartnerSummary();else{document.querySelector('#partner-summary').hidden=true;document.querySelector('#partner-filters').hidden=true}
  if(admin)renderAdminFilters()
  renderVisibleLeads()
  if(!document.querySelector('.screen.is-active'))showScreen(state.currentScreen)
}
function renderLeadCabinet(){
  const application=state.leadApplication
  const initialSelection=state.leadBanks.some(item=>item.selected===null)
  const addable=state.leadBanks.some(item=>item.selected===false)
  const canSelect=initialSelection||state.leadAddingBanks
  document.querySelector('#loading-state').hidden=true
  document.querySelector('.tabbar').hidden=false
  document.querySelector('#cabinet-label').textContent='Кабинет клиента'
  document.querySelector('#avatar').textContent=initials(state.session.name)||'К'
  document.querySelectorAll('.tabbar button').forEach(item=>item.hidden=true)
  document.querySelector('#client-application-tab').hidden=false
  document.querySelector('#client-banks-tab').hidden=false
  document.querySelector('#client-faq-tab').hidden=false
  document.querySelector('#add-more-banks').hidden=!addable||canSelect
  document.querySelector('.tabbar').style.setProperty('--tab-count',3)
  document.querySelector('#client-application-id').textContent=application.is_repeat?'Повторная заявка':'Заявка'
  const admin=application.admin_url
    ? `<a class="contact-row" href="${esc(application.admin_url)}" target="_blank" rel="noopener"><span><small>Администратор</small><strong>${esc(application.admin)}</strong></span><b>Написать</b></a>`
    : `<div class="value-row"><span>Администратор</span><strong>${esc(application.admin||'Ещё не назначен')}</strong></div>`
  const manager=application.manager_url
    ? `<a class="contact-row" href="${esc(application.manager_url)}" target="_blank" rel="noopener"><span><small>Персональный менеджер</small><strong>${esc(application.manager)}</strong></span><b>Написать</b></a>`
    : ''
  const metrics=application.metrics||{}
  document.querySelector('#client-application-card').innerHTML=`<section class="client-hero"><span>Что сейчас с заявкой</span><strong>${esc(clientWorkflowLabels[application.workflow_stage]||leadLabels[application.status]||application.status)}</strong><small>Обновлено ${dateTime(application.updated)}</small></section><section class="client-metric-grid"><div><span>Планируется счетов</span><strong>${metrics.planned_accounts||0}</strong></div><div><span>Активированных счетов</span><strong>${metrics.activated_accounts||0}</strong></div><div><span>Ожидаемая выплата</span><strong>${money(metrics.expected_payout)}</strong></div><div><span>Выплачено всего</span><strong>${money(metrics.paid_total)}</strong></div></section><section class="detail-section"><h3>Данные заявки</h3><div class="value-row"><span>Подана</span><strong>${date(application.date)}</strong></div>${admin}${manager}</section><p class="client-note">Здесь всегда виден текущий этап заявки.</p>`
  const cards=state.leadBanks.map(item=>{const selectable=item.selected===null||(state.leadAddingBanks&&item.selected===false);const dimmed=item.selected===false&&!state.leadAddingBanks;const status=selectable?'Доступен для открытия':item.selected===false?'Не выбран':item.lead_payment_status==='paid'?bankLabels.lead_reward_paid:(bankLabels[item.status]||item.status);return `<label class="client-bank-card ${selectable?'is-selectable':''} ${dimmed?'is-unselected':''}">${selectable?`<input class="bank-choice" type="checkbox" value="${esc(item.bank_id)}">`:''}${item.online_available?`<span class="online-badge">Можно онлайн <button type="button" data-online-help="${esc(item.online_help)}" aria-label="Условия открытия онлайн">${infoIcon}</button></span>`:''}<header><span class="client-bank-icon">${esc(initials(item.bank).slice(0,1)||'Б')}</span><div class="client-bank-copy"><h3>${esc(item.bank)}</h3><p>${esc(status)}</p></div>${selectable?'<span class="choice-mark">✓</span>':''}<strong class="bank-payout">${leadPayout(item)}</strong></header><section class="activation-action"><span>Условие активации</span><p>${esc(item.action_text||'Условие уточняется')}</p></section><small>Обновлено ${dateTime(item.updated)}</small></label>`}).join('')
  const emptyText=application.workflow_stage==='not_eligible'?'По текущим условиям подбор банков недоступен.':'Когда специалист сформирует доступные варианты, они появятся здесь.'
  const selectionActions=canSelect?`<button class="primary-button selection-submit" id="submit-bank-selection">${state.leadAddingBanks?'Добавить выбранные':'Продолжить'}</button>${state.leadAddingBanks?'<button class="secondary-button selection-submit" id="cancel-bank-selection">Отмена</button>':''}`:''
  document.querySelector('#client-banks-list').innerHTML=state.leadBanks.length?`${canSelect?'<p class="selection-intro">Отметьте банки, которые хотите открыть.</p>':''}${cards}${selectionActions}`:`<section class="empty-card"><span class="client-bank-icon">Б</span><h3>Банки пока недоступны</h3><p>${emptyText}</p></section>`
  document.querySelector('#submit-bank-selection')?.addEventListener('click',confirmLeadBankSelection)
  document.querySelector('#cancel-bank-selection')?.addEventListener('click',()=>{state.leadAddingBanks=false;renderLeadCabinet();showScreen('client-banks')})
  showScreen('client-application')
}
function confirmLeadBankSelection(){
  const selected=[...document.querySelectorAll('.bank-choice:checked')].map(input=>input.value)
  if(!selected.length)return toast('Выберите хотя бы один банк')
  const names=state.leadBanks.filter(item=>selected.includes(item.bank_id)).map(item=>item.bank)
  openSheet('Проверьте выбор','Перед отправкой',`<section class="detail-section"><h3>Выбранные банки</h3>${names.map(name=>`<div class="value-row"><span>Банк</span><strong>${esc(name)}</strong></div>`).join('')}</section><p class="confirmation-note">Выбранные банки останутся в заявке. Остальные можно будет добавить позже.</p><button class="primary-button" id="confirm-bank-selection">${state.leadAddingBanks?'Добавить банки':'Отправить менеджеру'}</button>`)
  document.querySelector('#confirm-bank-selection').addEventListener('click',async()=>{try{await api('/api/lead/banks/selection',{method:'POST',body:JSON.stringify({bank_ids:selected})});state.leadAddingBanks=false;closeSheet();toast('Выбор банков сохранён');await load();showScreen('client-banks')}catch(error){toast(error.message)}})
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
      const [channels,partnerData]=await Promise.all([
        api('/api/channels'),
        api(`/api/partner/cabinet?${partnerQuery()}`),
      ])
      Object.assign(state,{channels,partnerData})
      const metrics=state.partnerData.metrics
      Object.assign(state,{leads:state.partnerData.leads,dashboard:{total:metrics.total,new:metrics.new,active:metrics.active,unresolved:metrics.planned_banks,repeats:metrics.opened_banks,duplicates:0}})
      render();return
    }
    const employee=['admin','manager'].includes(state.session.role)
    const [dashboard,loadedLeads]=await Promise.all([
      api('/api/dashboard'),
      api(`/api/leads${state.leadScope==='mine'?'?mine=true':''}`),
    ])
    const leads=loadedLeads
    state.banksLoading=employee
    state.banksError=false
    Object.assign(state,{dashboard,leads});render()
    const optional=[
      ['partners',state.session.role==='admin'?'/api/partners':null],
      ['channels',['admin','partner'].includes(state.session.role)?'/api/channels':null],
      ['banks',employee?'/api/banks':null],
      ['staff',employee?'/api/staff':null],
      ['duplicates',state.session.role==='admin'?'/api/duplicate-reviews':null],
    ]
    await Promise.all(optional.map(async([key,path])=>{
      if(!path)return
      try{state[key]=await api(path)}catch(error){console.warn(`Не удалось загрузить ${key}`,error);if(key==='banks')state.banksError=true}
      finally{if(key==='banks')state.banksLoading=false;render()}
    }))
  }catch(error){ document.querySelector('#loading-state').hidden=true; document.querySelector('.tabbar').hidden=true; document.querySelectorAll('.screen').forEach(x=>x.classList.remove('is-active')); document.querySelector('#error-message').textContent=error.message; document.querySelector('#error-state').hidden=false }
}

function bankCard(item,employee,admin,quickActions){
  const options=Object.entries(bankLabels).slice(0,10).map(([v,l])=>`<option value="${v}" ${item.status===v?'selected':''}>${l}</option>`).join('')
  const financialEdit=admin?`<div class="field-row"><label class="field"><span>Общая ставка, прогноз</span><input type="number" data-estimate value="${item.income_estimate||''}"></label><label class="field"><span>Общая ставка, факт</span><input type="number" data-fact value="${item.income_fact||''}"></label></div>`:''
  const edit=employee?`<label class="field"><span>Статус</span><select data-bank-status>${options}</select></label>${financialEdit}<label class="field"><span>Причина закрытия</span><input data-reason value="${esc(item.close_reason||'')}"></label><button class="secondary-button" data-save-bank="${item.id}">Сохранить изменения</button>`:`<div class="value-row"><span>Статус</span><strong>${esc(bankLabels[item.status]||item.status)}</strong></div>`
  const quick=quickActions&&!['account_opened','bank_rejected','client_refused','excluded'].includes(item.status)?`<div class="bank-quick-actions"><button class="primary-button" data-bank-opened="${item.id}">Счёт активирован</button><button class="danger-button" data-bank-reject="${item.id}" data-bank-name="${esc(item.bank)}">Отказ</button></div>`:''
  const confirm=admin&&item.payment_status==='awaiting_confirmation'?`<button class="primary-button" data-confirm-pay="${item.id}">Подтвердить выплату</button>`:''
  const next=admin&&item.payment_id&&['confirmed','in_registry'].includes(item.payment_status)?`<button class="primary-button" data-next-pay="${item.payment_id}" data-current="${item.payment_status}">${item.payment_status==='confirmed'?'Добавить в реестр':'Отметить выплаченной'}</button>`:''
  const clientView=employee?`<div class="value-row"><span>Показан клиенту</span><strong>${item.offered_to_lead?'Да':'Нет'}</strong></div><div class="value-row"><span>Выбор клиента</span><strong>${item.selected_by_lead===true?'Клиент выбрал':item.selected_by_lead===false?'Клиент не выбрал':'Клиент ещё не подтвердил'}</strong></div><div class="value-row"><span>Условие выплаты</span><strong>${esc(item.action_text||'Условие пока не указано')}</strong></div>`:''
  const economics=admin?`<div class="value-row"><span>Общая ставка</span><strong>${money(item.income_fact||item.income_estimate)}</strong></div><div class="value-row"><span>Выплата клиенту</span><strong>${money(item.lead_reward_fact??item.lead_reward_estimate)}</strong></div><div class="value-row"><span>Выплата партнёру</span><strong>${money(item.reward_fact||item.reward_estimate)}</strong></div><div class="value-row"><span>Командная прибыль</span><strong class="money">${money(item.team_profit_fact||item.team_profit_estimate)}</strong></div>`:''
  const leadPayment=admin&&item.status==='account_opened'?(item.lead_reward_paid_at?`<div class="value-row"><span>Выплата лиду</span><strong>Сделана · ${money(item.lead_reward_fact)}</strong></div>`:`<section class="lead-payment-form"><label class="field"><span>Фактическая выплата лиду</span><input type="number" min="0" step="0.01" inputmode="decimal" data-lead-payment-amount value="${esc(item.lead_reward_estimate??'')}"></label><button class="primary-button" data-confirm-lead-payment="${item.id}">Подтвердить выплату лиду</button></section>`):''
  const online=item.online_available?`<span class="online-badge compact">Можно онлайн <button type="button" data-online-help="${esc(item.online_help)}" aria-label="Условия открытия онлайн">${infoIcon}</button></span>`:''
  const remove=admin?`<button class="danger-button" data-remove-lead-bank="${item.id}">Убрать банк из заявки</button>`:''
  return `<article class="bank-card" data-bank-card="${item.id}">${online}<header><h4>${esc(item.bank)}</h4><span>${admin?money(item.team_profit_fact||item.team_profit_estimate):esc(payLabels[item.payment_status]||item.payment_status)}</span></header>${clientView}${quick}${edit}${economics}${leadPayment}<div class="button-stack">${confirm}${next}${remove}</div></article>`
}
async function openLead(id){
  if(state.session.role==='partner')return openPartnerLead(id)
  try{
    let lead=await api(`/api/leads/${id}`)
    const partner=state.session.role==='partner',admin=state.session.role==='admin',managerRole=state.session.role==='manager'
    if(managerRole&&lead.workflow_stage==='awaiting_manager'&&lead.is_assigned_manager){
      await api(`/api/leads/${lead.id}/claim-manager`,{method:'POST',body:'{}'})
      lead=await api(`/api/leads/${id}`)
      state.leadScope='mine'
      document.querySelector('#lead-scope').value='mine'
      await load()
    }
    const editable=!partner&&!lead.archived
    const canManageBanks=editable&&((admin&&lead.is_primary_admin)||(managerRole&&lead.is_assigned_manager&&lead.workflow_stage==='manager_processing'))
    const statusButtons=internalLeadStatuses.map(value=>`<button type="button" class="status-option ${lead.status===value?'is-selected':''}" data-lead-status="${value}" aria-pressed="${lead.status===value}">${esc(leadLabels[value])}</button>`).join('')
    const username=String(lead.username||'').replace(/^@/,'')
    const telegramLink=/^[A-Za-z0-9_]{5,}$/.test(username)?`https://t.me/${username}`:''
    const phoneLink=String(lead.phone||'').replace(/[^+\d]/g,'')
    const contacts=partner?'':`<section class="detail-section"><h3>Контакты</h3><button type="button" class="contact-row" data-contact-link="tel:${esc(phoneLink)}"><span><small>Телефон</small><strong>${esc(lead.phone||'Не указан')}</strong></span><b>Позвонить</b></button>${lead.email?`<button type="button" class="contact-row" data-contact-link="mailto:${esc(lead.email)}"><span><small>E-mail</small><strong>${esc(lead.email)}</strong></span><b>Написать</b></button>`:''}${telegramLink?`<a class="contact-row" href="${esc(telegramLink)}" target="_blank" rel="noopener"><span><small>Telegram</small><strong>@${esc(username)}</strong></span><b aria-hidden="true">Открыть</b></a>`:`<div class="value-row"><span>Telegram</span><strong>${esc(lead.username||lead.telegram_id||'Не указан')}</strong></div>`}</section>`
    const answers=partner?'':Object.entries(lead.answers||{}).map(([key,value])=>`<div class="value-row"><span>${esc(questionLabels[key]||key)}</span><strong>${esc(answer(value))}</strong></div>`).join('')
    const statusEditor=editable?`<section class="detail-section status-section"><h3>Статус заявки</h3><details><summary><span><small>Текущий статус</small><strong>${esc(leadLabels[lead.status]||lead.status)}</strong></span><b>Изменить</b></summary><div class="status-grid">${statusButtons}</div></details></section>`:''
    const edit=editable?`<section class="detail-section"><h3>Работа с заявкой</h3><label class="field"><span>Внутренний комментарий</span><textarea id="lead-comment" placeholder="Заметка для команды">${esc(lead.comment||'')}</textarea></label><button class="primary-button inset-button" id="save-lead">Сохранить комментарий</button></section>`:''
    const deleteApplication=admin&&!lead.archived?`<section class="destructive-section"><button class="danger-button" id="show-delete-lead">Удалить эту заявку</button><div id="delete-lead-confirm" hidden><p>Заявка, её банки и неподтверждённые выплаты будут удалены. Telegram-аккаунт клиента и другие его заявки останутся.</p><div class="button-stack"><button class="danger-button" id="delete-lead">Да, удалить заявку</button><button class="secondary-button" id="cancel-delete-lead">Отмена</button></div></div></section>`:''
    const workflowActions=!lead.archived&&managerRole&&lead.workflow_stage==='awaiting_manager'?'<button class="primary-button inset-button" id="claim-manager">Взять в сопровождение</button>':''
    const managerOptions=state.staff.filter(item=>item.role==='manager'&&['active','pending'].includes(item.status)).map(item=>`<option value="${item.id}" ${lead.manager_id===item.id?'selected':''}>${esc(item.username||item.telegram_id)}</option>`).join('')
    const managerControl=admin&&managerOptions?`<label class="field inset-field"><span>Менеджер сопровождения</span><select id="lead-manager">${managerOptions}</select></label><button class="secondary-button inset-button" id="save-lead-manager">Назначить менеджера</button>`:`<div class="value-row"><span>Менеджер сопровождения</span><strong>${esc(lead.manager||'Не назначен')}</strong></div>`
    const workflow=`<section class="detail-section"><h3>Этап обработки</h3><div class="value-row"><span>Стадия</span><strong>${esc(workflowLabels[lead.workflow_stage]||lead.workflow_stage)}</strong></div><div class="value-row"><span>Первичный ответственный</span><strong>${esc(lead.primary_admin||'Не назначен')}</strong></div>${managerControl}${workflowActions}</section>`
    const canUseBankQuickActions=managerRole&&lead.is_assigned_manager&&lead.workflow_stage==='manager_processing'&&!lead.archived
    const banks=lead.banks.map(x=>bankCard(x,editable,admin&&!lead.archived,canUseBankQuickActions)).join('')
    const application=`<section class="detail-section"><h3>${lead.archived?'Архивная заявка':'Заявка'}</h3><div class="value-row"><span>Создана</span><strong>${dateTime(lead.date)}</strong></div><div class="value-row"><span>Обновлена</span><strong>${dateTime(lead.updated)}</strong></div><div class="value-row"><span>Источник</span><strong>${esc(lead.channel)}</strong></div><div class="value-row"><span>Менеджер</span><strong>${esc(lead.manager)}</strong></div>${partner?'':`<div class="value-row"><span>Согласие на данные</span><strong>${lead.consent?'Получено':'Нет'}${lead.consent_at?` · ${date(lead.consent_at)}`:''}</strong></div>`}</section>`
    const questionnaire=partner||!answers?'':`<section class="detail-section"><h3>Анкета</h3>${answers}</section>`
    const history=partner||!lead.previous_applications?.length?'':`<section class="detail-section"><h3>Предыдущие заявки</h3>${lead.previous_applications.map(previous=>`<button class="list-row" type="button" data-lead="${previous.id}"><span class="row-icon">${previous.is_repeat?'П':'А'}</span><span class="row-content"><span class="row-title"><strong>${esc(previous.short_id)}</strong><time>${date(previous.date).slice(0,5)}</time></span><span class="row-subtitle">${previous.is_repeat?'Повторная · ':''}${esc(leadLabels[previous.status]||previous.status)}</span></span></button>`).join('')}</section>`
    openSheet(lead.name,`${lead.short_id} · ${lead.is_repeat?'Повторная · ':''}${lead.archived?'Архив · ':''}${workflowLabels[lead.workflow_stage]||leadLabels[lead.status]||lead.status}`,`${contacts}${workflow}${application}${statusEditor}${questionnaire}${history}${edit}<div class="list-heading"><h3>Банки</h3>${canManageBanks?'<button id="add-lead-bank">Добавить</button>':''}</div>${banks||'<p class="empty">Банки не добавлены</p>'}${deleteApplication}`)
    bindLeadActions(lead,admin)
  }catch(error){ toast(error.message) }
}
function openPartnerLead(id){
  const lead=state.partnerData.leads.find(item=>item.id===id)
  if(!lead)return toast('Заявка не найдена')
  const contact=state.partnerData.contact
  const admin=contact.url?`<a class="contact-row" href="${esc(contact.url)}" target="_blank" rel="noopener"><span><small>Ваш администратор</small><strong>${esc(contact.name)}</strong></span><b>Написать</b></a>`:`<div class="value-row"><span>Ваш администратор</span><strong>Ещё не назначен</strong></div>`
  const counts=lead.bank_counts||{}
  const banks=lead.banks.map((bank,index)=>`<button type="button" class="bank-card bank-card-button" data-partner-bank="${index}">${bank.online_available?`<span class="online-badge compact">Можно онлайн <span role="button" tabindex="0" data-online-help="${esc(bank.online_help)}" aria-label="Условия открытия онлайн">${infoIcon}</span></span>`:''}<header><h4>${esc(bank.bank)}</h4><span>${money(bank.reward_estimate)}</span></header><section class="activation-action"><span>Условие активации</span><p>${esc(bank.action_text||'Условие уточняется')}</p></section><small>Нажмите, чтобы посмотреть выплаты</small></button>`).join('')
  openSheet(lead.name,`${lead.short_id} · ${lead.is_repeat?'Повторная · ':''}${leadLabels[lead.status]||lead.status}`,`<section class="detail-section"><h3>Заявка клиента</h3><div class="value-row"><span>Номер</span><strong>${esc(lead.short_id)}</strong></div><div class="value-row"><span>Дата заявки</span><strong>${dateTime(lead.date)}</strong></div><div class="value-row"><span>Последнее обновление</span><strong>${dateTime(lead.updated)}</strong></div><div class="value-row"><span>Канал</span><strong>${esc(lead.channel)}</strong></div><div class="value-row"><span>Статус</span><strong>${esc(leadLabels[lead.status]||lead.status)}</strong></div>${admin}</section><section class="detail-section"><h3>Банки и выплаты</h3><div class="value-row"><span>Запланировано / в работе / открыто</span><strong>${counts.planned||0} / ${counts.in_progress||0} / ${counts.opened||0}</strong></div><div class="value-row"><span>Не будет открыто</span><strong>${counts.will_not_open||0}</strong></div><div class="value-row"><span>Ожидаемая выплата</span><strong>${money(lead.reward_estimate)}</strong></div><div class="value-row"><span>Подтверждённая выплата</span><strong>${money(lead.reward_fact)}</strong></div></section>${banks||'<p class="empty">Банки пока не добавлены</p>'}`)
  document.querySelectorAll('[data-partner-bank]').forEach(button=>button.addEventListener('click',()=>openPartnerBank(lead,Number(button.dataset.partnerBank))))
}
function openPartnerBank(lead,index){
  const bank=lead.banks[index]
  if(!bank)return openPartnerLead(lead.id)
  openSheet(bank.bank,'Ставки по заявке',`<section class="detail-section"><div class="value-row"><span>Статус счёта</span><strong>${esc(bankLabels[bank.status]||bank.status)}</strong></div><div class="value-row"><span>Ваша ожидаемая выплата</span><strong>${money(bank.reward_estimate)}</strong></div><div class="value-row"><span>Вам подтверждено</span><strong>${money(bank.reward_fact)}</strong></div><div class="value-row"><span>Выплата клиенту</span><strong>${money(bank.lead_reward_estimate)}</strong></div><div class="value-row"><span>Можно открыть онлайн</span><strong>${String(bank.online_text||'').toLowerCase().startsWith('да')?'Да':'Нет'}</strong></div></section><section class="activation-action"><span>Условие активации</span><p>${esc(bank.action_text||'Условие уточняется')}</p></section><button class="secondary-button" id="back-to-partner-lead">Назад к заявке</button>`)
  document.querySelector('#back-to-partner-lead').addEventListener('click',()=>openPartnerLead(lead.id))
}
function bindLeadActions(lead,admin){
  document.querySelector('#save-lead-manager')?.addEventListener('click',async()=>{const managerId=document.querySelector('#lead-manager').value;if(managerId===lead.manager_id)return toast('Этот менеджер уже назначен');await api(`/api/leads/${lead.id}`,{method:'PATCH',body:JSON.stringify({manager_id:managerId,update_manager:true})});toast('Менеджер сопровождения изменён');await openLead(lead.id);await load()})
  document.querySelector('#claim-manager')?.addEventListener('click',async()=>{await api(`/api/leads/${lead.id}/claim-manager`,{method:'POST',body:'{}'});state.leadScope='mine';document.querySelector('#lead-scope').value='mine';toast('Заявка взята в сопровождение');await load();await openLead(lead.id)})
  document.querySelectorAll('[data-lead-status]').forEach(button=>button.addEventListener('click',async()=>{ if(button.dataset.leadStatus===lead.status)return; document.querySelectorAll('[data-lead-status]').forEach(item=>item.disabled=true); await api(`/api/leads/${lead.id}`,{method:'PATCH',body:JSON.stringify({internal_status:button.dataset.leadStatus})}); toast('Статус изменён'); await openLead(lead.id); await load() }))
  document.querySelector('#save-lead')?.addEventListener('click',async()=>{ await api(`/api/leads/${lead.id}`,{method:'PATCH',body:JSON.stringify({update_manager:false,internal_comment:document.querySelector('#lead-comment').value,update_comment:true})}); toast('Комментарий сохранён'); await openLead(lead.id); await load() })
  document.querySelector('#show-delete-lead')?.addEventListener('click',()=>{document.querySelector('#show-delete-lead').hidden=true;document.querySelector('#delete-lead-confirm').hidden=false})
  document.querySelector('#cancel-delete-lead')?.addEventListener('click',()=>{document.querySelector('#show-delete-lead').hidden=false;document.querySelector('#delete-lead-confirm').hidden=true})
  document.querySelector('#delete-lead')?.addEventListener('click',async()=>{const button=document.querySelector('#delete-lead');button.disabled=true;try{await api(`/api/leads/${lead.id}`,{method:'DELETE'});toast('Заявка удалена');closeSheet();await load();showScreen('leads')}catch(error){button.disabled=false;toast(error.message)}})
  document.querySelector('#add-lead-bank')?.addEventListener('click',()=>addLeadBank(lead))
  document.querySelectorAll('[data-bank-opened]').forEach(btn=>btn.addEventListener('click',async()=>{btn.disabled=true;await api(`/api/lead-banks/${btn.dataset.bankOpened}`,{method:'PATCH',body:JSON.stringify({status:'account_opened'})});toast('Счёт отмечен как активированный');await openLead(lead.id);await load()}))
  document.querySelectorAll('[data-bank-reject]').forEach(btn=>btn.addEventListener('click',()=>openBankRejection(lead,btn.dataset.bankReject,btn.dataset.bankName)))
  document.querySelectorAll('[data-save-bank]').forEach(btn=>btn.addEventListener('click',async()=>{ const c=btn.closest('[data-bank-card]'),payload={status:c.querySelector('[data-bank-status]').value,close_reason:c.querySelector('[data-reason]').value||null},estimate=c.querySelector('[data-estimate]'),fact=c.querySelector('[data-fact]');if(estimate)payload.income_estimate=estimate.value||null;if(fact)payload.income_fact=fact.value||null;await api(`/api/lead-banks/${btn.dataset.saveBank}`,{method:'PATCH',body:JSON.stringify(payload)}); toast('Изменения сохранены'); await openLead(lead.id) }))
  document.querySelectorAll('[data-confirm-lead-payment]').forEach(btn=>btn.addEventListener('click',async()=>{const card=btn.closest('[data-bank-card]'),amount=card.querySelector('[data-lead-payment-amount]').value;if(amount===''||Number(amount)<0)return toast('Укажите фактическую сумму выплаты');btn.disabled=true;try{await api(`/api/lead-banks/${btn.dataset.confirmLeadPayment}/lead-reward/confirm`,{method:'POST',body:JSON.stringify({amount})});toast('Выплата лиду сохранена');await openLead(lead.id);await load()}catch(error){btn.disabled=false;toast(error.message)}}))
  document.querySelectorAll('[data-remove-lead-bank]').forEach(btn=>btn.addEventListener('click',async()=>{if(!window.confirm('Убрать этот банк из заявки?'))return;const result=await api(`/api/lead-banks/${btn.dataset.removeLeadBank}`,{method:'DELETE'});toast(result.message);await openLead(lead.id);await load()}))
  document.querySelectorAll('[data-confirm-pay]').forEach(btn=>btn.addEventListener('click',async()=>{ await api(`/api/lead-banks/${btn.dataset.confirmPay}/payment/confirm`,{method:'POST',body:'{}'}); toast('Выплата подтверждена'); await openLead(lead.id) }))
  document.querySelectorAll('[data-next-pay]').forEach(btn=>btn.addEventListener('click',async()=>{ const status=btn.dataset.current==='confirmed'?'in_registry':'paid'; const payload={status}; if(status==='paid')payload.paid_at=localISODate(); await api(`/api/payments/${btn.dataset.nextPay}`,{method:'PATCH',body:JSON.stringify(payload)}); toast(status==='paid'?'Выплата отмечена':'Добавлено в реестр'); await openLead(lead.id) }))
}
function openBankRejection(lead,bankId,bankName){
  openSheet('Оформить отказ',bankName,`<section class="form-card"><label class="field"><span>Кто отказал</span><select id="bank-rejection-type"><option value="bank_rejected">Банк</option><option value="client_refused">Клиент</option></select></label><label class="field"><span>Причина</span><textarea id="bank-rejection-reason" placeholder="Кратко опишите причину"></textarea></label></section><div class="button-stack"><button class="danger-button" id="confirm-bank-rejection">Сохранить отказ</button><button class="secondary-button" id="cancel-bank-rejection">Отмена</button></div>`)
  document.querySelector('#confirm-bank-rejection').addEventListener('click',async()=>{const reason=document.querySelector('#bank-rejection-reason').value.trim();if(reason.length<2)return toast('Укажите краткую причину');const button=document.querySelector('#confirm-bank-rejection');button.disabled=true;await api(`/api/lead-banks/${bankId}`,{method:'PATCH',body:JSON.stringify({status:document.querySelector('#bank-rejection-type').value,close_reason:reason})});toast('Отказ сохранён');await openLead(lead.id);await load()})
  document.querySelector('#cancel-bank-rejection').addEventListener('click',()=>openLead(lead.id))
}
function addLeadBank(lead){
  const used=new Set(lead.banks.map(x=>x.bank_id)), available=state.banks.filter(x=>x.active&&!used.has(x.id))
  const options=available.map(x=>`<label class="check-field"><input type="checkbox" class="new-lead-bank" value="${x.id}"><span>${esc(x.name)}</span></label>`).join('')
  openSheet('Добавить банки',lead.short_id,available.length?`<section class="form-card"><p class="field-note">Выберите один или несколько банков. После подтверждения они сразу появятся у клиента.</p>${options}</section><button class="primary-button" id="confirm-add-bank">Добавить и показать клиенту</button>`:'<p class="empty">Все доступные банки уже добавлены</p>')
  document.querySelector('#confirm-add-bank')?.addEventListener('click',async()=>{const bank_ids=[...document.querySelectorAll('.new-lead-bank:checked')].map(input=>input.value);if(!bank_ids.length)return toast('Выберите хотя бы один банк');const button=document.querySelector('#confirm-add-bank');button.disabled=true;try{await api(`/api/leads/${lead.id}/banks`,{method:'POST',body:JSON.stringify({bank_ids})});toast(bank_ids.length===1?'Банк добавлен и показан клиенту':`Банки добавлены: ${bank_ids.length}`);await openLead(lead.id);await load()}catch(error){button.disabled=false;toast(error.message)}})
}
function openPartner(id){
  const p=state.partners.find(x=>x.id===id), channels=state.channels.filter(x=>x.partner_id===id)
  if(!p)return toast('Партнёр не найден')
  const links=channels.length?channels.map(channel=>`<button type="button" class="contact-row channel-link-row" data-channel="${channel.id}"><span><small>${esc(channel.name)}</small><strong>${esc(channel.link)}</strong></span><b>Открыть</b></button>`).join(''):'<p class="empty">Каналов пока нет</p>'
  const username=String(p.telegram_username||'').replace(/^@/,'')
  const telegram=username?`@${username}${p.telegram_id?` · ID ${p.telegram_id}`:''}`:p.telegram_id?`ID ${p.telegram_id}`:'Не привязан'
  const admins=state.staff.filter(item=>item.role==='admin'&&item.status==='active').map(item=>`<option value="${item.id}" ${p.assigned_admin_id===item.id?'selected':''}>${esc(item.username||item.telegram_id)}</option>`).join('')
  const activation=p.activated?'<div class="value-row"><span>Партнёрский кабинет</span><strong>Уже активирован</strong></div>':'<p class="field-note">Создайте одноразовую ссылку и отправьте её партнёру. Новая ссылка отменяет предыдущую.</p><button class="primary-button inset-button" id="create-partner-activation-link">Создать ссылку активации</button><div id="partner-activation-result" hidden></div>'
  openSheet(p.name,'Партнёр и каналы',`<section class="detail-section"><h3>Реферальные ссылки</h3>${links}</section><section class="form-card"><h3>Активация кабинета</h3>${activation}</section><section class="form-card"><h3>Настройки партнёра</h3><label class="field"><span>Ответственный администратор</span><select id="partner-admin">${admins}</select></label><button class="secondary-button inset-button" id="save-partner-admin">Сохранить администратора</button><label class="field"><span>Процент партнёра</span><input id="partner-commission" inputmode="decimal" value="${esc(p.commission)}"></label><button class="secondary-button inset-button" id="save-commission">Сохранить процент</button><div class="value-row"><span>Telegram</span><strong>${esc(telegram)}</strong></div><label class="field"><span>Telegram ID</span><input id="partner-id" inputmode="numeric" value="${esc(p.telegram_id||'')}" placeholder="Например, 123456789"></label><label class="field"><span>Username без @</span><input id="partner-user" value="${esc(username)}" placeholder="Например, gerasimov"></label><p class="field-note">Username привяжется при первом входе партнёра. Telegram ID можно указать сразу, если он известен.</p><button class="primary-button inset-button" id="save-partner">Сохранить доступ</button></section><section class="destructive-section"><button class="danger-button" id="show-remove-partner">Убрать партнёра</button><div id="remove-partner-confirm" hidden><p>Если по партнёру ещё нет истории, он удалится. Если заявки уже есть, доступ и ссылки отключатся, а история сохранится.</p><div class="button-stack"><button class="danger-button" id="remove-partner">Да, убрать</button><button class="secondary-button" id="cancel-remove-partner">Отмена</button></div></div></section>`)
  document.querySelector('#create-partner-activation-link')?.addEventListener('click',async()=>{const button=document.querySelector('#create-partner-activation-link');button.disabled=true;try{const result=await api(`/api/partners/${id}/activation-link`,{method:'POST',body:'{}'}),target=document.querySelector('#partner-activation-result');target.hidden=false;target.innerHTML=referralLinkRows(result);button.textContent='Создать новые ссылки';bindReferralLinkCopies(result)}catch(error){toast(error.message)}finally{button.disabled=false}})
  document.querySelector('#save-partner-admin').addEventListener('click',async()=>{const value=document.querySelector('#partner-admin').value;await api(`/api/partners/${id}`,{method:'PATCH',body:JSON.stringify({assigned_admin_id:value||null,update_assigned_admin:true})});toast('Администратор сохранён');await load();openPartner(id)})
  document.querySelector('#save-commission').addEventListener('click',async()=>{await api(`/api/partners/${id}`,{method:'PATCH',body:JSON.stringify({commission_percent:document.querySelector('#partner-commission').value.replace(',','.')})});toast('Процент сохранён');await load();openPartner(id)})
  document.querySelector('#save-partner').addEventListener('click',async()=>{const telegramId=document.querySelector('#partner-id').value.trim(),telegramUsername=document.querySelector('#partner-user').value.trim();if(telegramId){await api(`/api/partners/${id}/access`,{method:'PUT',body:JSON.stringify({telegram_id:telegramId,telegram_username:telegramUsername||null})});toast('Доступ настроен')}else{if(!telegramUsername)return toast('Укажите username или Telegram ID');await api(`/api/partners/${id}`,{method:'PATCH',body:JSON.stringify({telegram_username:telegramUsername})});toast('Username сохранён')}await load();openPartner(id)})
  document.querySelector('#show-remove-partner').addEventListener('click',()=>{document.querySelector('#show-remove-partner').hidden=true;document.querySelector('#remove-partner-confirm').hidden=false})
  document.querySelector('#cancel-remove-partner').addEventListener('click',()=>{document.querySelector('#show-remove-partner').hidden=false;document.querySelector('#remove-partner-confirm').hidden=true})
  document.querySelector('#remove-partner').addEventListener('click',async()=>{try{const result=await api(`/api/partners/${id}`,{method:'DELETE'});toast(result.message);closeSheet();await load()}catch(error){toast(error.message)}})
}
function openNewPartner(){
  openSheet('Новый партнёр','Доступ и процент',`<section class="form-card"><label class="field"><span>Название или имя партнёра</span><input id="new-partner-name" maxlength="160" placeholder="Например, Максим"></label><label class="field"><span>Процент партнёра</span><input id="new-partner-percent" inputmode="decimal" value="20"></label><label class="field"><span>Telegram username без @</span><input id="new-partner-username" placeholder="Можно оставить пустым"></label><p class="field-note">Вы автоматически станете ответственным администратором этого партнёра.</p></section><button class="primary-button" id="create-partner">Добавить партнёра</button>`)
  document.querySelector('#create-partner').addEventListener('click',async()=>{const name=document.querySelector('#new-partner-name').value.trim(),commission=document.querySelector('#new-partner-percent').value.replace(',','.'),telegram_username=document.querySelector('#new-partner-username').value.trim()||null;if(name.length<2)return toast('Укажите имя партнёра');await api('/api/partners',{method:'POST',body:JSON.stringify({name,commission_percent:commission,telegram_username})});toast('Партнёр добавлен');closeSheet();await load();showScreen('partners')})
}
function openChannel(id){
  const channel=state.channels.find(item=>item.id===id)
  if(!channel)return toast('Канал не найден')
  openSheet(channel.name,channel.active?'Канал работает':'Канал отключён',`${referralLinkRows(channel)}<div class="button-stack"><button class="danger-button" id="remove-channel">Удалить канал</button><button class="secondary-button" id="cancel-channel">Закрыть</button></div>`)
  bindReferralLinkCopies(channel)
  document.querySelector('#cancel-channel').addEventListener('click',closeSheet)
  document.querySelector('#remove-channel').addEventListener('click',async()=>{if(!window.confirm('Удалить канал? Если по нему уже были заявки, он будет отключён с сохранением истории.'))return;const result=await api(`/api/channels/${channel.id}`,{method:'DELETE'});toast(result.message);closeSheet();await load();showScreen('partners')})
}
function bankFormValues(){
  return {offer_code:document.querySelector('#catalog-offer-code').value.trim(),name:document.querySelector('#catalog-bank-name').value.trim(),online_text:document.querySelector('#catalog-online').value,base_payout:document.querySelector('#catalog-base').value.replace(',','.'),lead_payout:document.querySelector('#catalog-lead').value.replace(',','.'),lead_payout_paid_separately:document.querySelector('#catalog-lead-separate').checked,active:document.querySelector('#catalog-active').checked,display_order:Number(document.querySelector('#catalog-order').value||0)}
}
function updateCatalogPreview(){
  const base=Number(document.querySelector('#catalog-base').value.replace(',','.'))
  const lead=Number(document.querySelector('#catalog-lead').value.replace(',','.'))
  const percent=Number(document.querySelector('#catalog-preview-percent').value.replace(',','.'))
  const valid=[base,lead,percent].every(Number.isFinite)
  const partner=valid?base*percent/100:null
  const team=valid?base-partner-(document.querySelector('#catalog-lead-separate').checked?0:lead):null
  document.querySelector('#catalog-preview-partner').textContent=money(partner)
  document.querySelector('#catalog-preview-team').textContent=money(team)
  document.querySelector('#catalog-preview-team').classList.toggle('danger-text',team!==null&&team<0)
}
function openCatalogBank(id=null){
  const bank=id?state.banks.find(item=>item.id===id):null
  const online=bank?.online_text||'Нет'
  openSheet(bank?bank.name:'Новый банк',bank?'Редактирование справочника':'Добавление в справочник',`<section class="form-card"><label class="field"><span>Код предложения</span><input id="catalog-offer-code" maxlength="64" value="${esc(bank?.offer_code||'')}" ${bank?'readonly':''}></label>${bank?'<p class="field-note">Код фиксируется при создании банка и потом не меняется.</p>':''}<label class="field"><span>Название банка</span><input id="catalog-bank-name" maxlength="120" value="${esc(bank?.name||'')}"></label><label class="field"><span>Можно открыть онлайн</span><select id="catalog-online"><option value="Нет" ${online.toLowerCase().startsWith('нет')?'selected':''}>Нет</option><option value="Да" ${online.toLowerCase()==='да'?'selected':''}>Да, с КЭП</option><option value="Да, даже без КЭП" ${online.toLowerCase().includes('без кэп')?'selected':''}>Да, даже без КЭП</option></select></label><div class="field-row"><label class="field"><span>Общая ставка</span><input id="catalog-base" inputmode="decimal" value="${esc(bank?.base_payout||'')}"></label><label class="field"><span>Выплата клиенту</span><input id="catalog-lead" inputmode="decimal" value="${esc(bank?.lead_payout||'')}"></label></div><label class="check-field"><input type="checkbox" id="catalog-lead-separate" ${bank?.lead_payout_paid_separately?'checked':''}><span>Выплату клиенту банк платит отдельно</span></label><section class="detail-section"><h3>Предпросмотр расчёта</h3><label class="field"><span>Процент партнёра для примера</span><input id="catalog-preview-percent" inputmode="decimal" value="20"></label><div class="value-row"><span>Выплата партнёру</span><strong id="catalog-preview-partner">—</strong></div><div class="value-row"><span>Командная прибыль</span><strong id="catalog-preview-team">—</strong></div><p class="field-note">Процент нужен только для предпросмотра и не сохраняется в карточке банка.</p></section><p class="field-note">Условие активации берётся из Google Sheets и не редактируется здесь.</p><label class="field"><span>Порядок</span><input id="catalog-order" type="number" min="0" value="${esc(bank?.order??0)}"></label><label class="check-field"><input type="checkbox" id="catalog-active" ${bank?.active!==false?'checked':''}><span>Банк доступен для новых заявок</span></label></section><div class="button-stack"><button class="primary-button" id="save-catalog-bank">${bank?'Сохранить изменения':'Добавить банк'}</button>${bank?'<button class="danger-button" id="remove-catalog-bank">Убрать банк</button>':''}</div>`)
  ;['catalog-base','catalog-lead','catalog-preview-percent','catalog-lead-separate'].forEach(id=>document.querySelector(`#${id}`).addEventListener('input',updateCatalogPreview))
  updateCatalogPreview()
  document.querySelector('#save-catalog-bank').addEventListener('click',async()=>{const payload=bankFormValues();if(!payload.offer_code||payload.name.length<2)return toast('Заполни код и название');if(payload.base_payout===''||payload.lead_payout==='')return toast('Заполни ставки');await api(bank?`/api/banks/${bank.id}`:'/api/banks',{method:bank?'PATCH':'POST',body:JSON.stringify(payload)});toast(bank?'Банк обновлён':'Банк добавлен');closeSheet();await load();showScreen('banks')})
  document.querySelector('#remove-catalog-bank')?.addEventListener('click',async()=>{if(!window.confirm('Убрать банк из справочника? В старых заявках история сохранится.'))return;const result=await api(`/api/banks/${bank.id}`,{method:'DELETE'});toast(result.message);closeSheet();await load();showScreen('banks')})
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
  openSheet(item.name,'Возможный дубль',`<section class="detail-section"><h3>Исходная заявка</h3>${original}</section><section class="detail-section"><h3>Новая попытка</h3><div class="value-row"><span>Telegram</span><strong>${esc(item.username||item.telegram_id)}</strong></div><div class="value-row"><span>Телефон</span><strong>${esc(item.phone)}</strong></div><div class="value-row"><span>Реферальная метка</span><strong>${esc(item.referral_code||'Прямой вход')}</strong></div>${answers}</section><div class="button-stack"><button class="primary-button" data-resolve-duplicate="duplicate">Это дубль</button><button class="secondary-button" data-resolve-duplicate="separate_lead">Это другой клиент</button><button class="secondary-button" data-resolve-duplicate="update_original">Обновить исходную заявку</button></div>`)
  document.querySelectorAll('[data-resolve-duplicate]').forEach(button=>button.addEventListener('click',()=>confirmDuplicateResolution(item,button.dataset.resolveDuplicate)))
}
function confirmDuplicateResolution(item,resolution){
  const labels={duplicate:'Отклонить новую попытку как дубль',separate_lead:'Создать отдельную заявку',update_original:'Заменить данные исходной заявки'}
  openSheet('Подтвердить решение',item.name,`<section class="detail-section"><h3>Решение администратора</h3><div class="value-row"><span>Действие</span><strong>${esc(labels[resolution])}</strong></div></section><p class="confirmation-note">Операция сразу закроет проверку дубля.</p><div class="button-stack"><button class="primary-button" id="confirm-duplicate-resolution">Подтвердить</button><button class="secondary-button" id="cancel-duplicate-resolution">Отмена</button></div>`)
  document.querySelector('#confirm-duplicate-resolution').addEventListener('click',async()=>{await api(`/api/duplicate-reviews/${item.id}/resolve`,{method:'POST',body:JSON.stringify({resolution})});toast('Решение сохранено');await load();openDuplicateQueue()})
  document.querySelector('#cancel-duplicate-resolution').addEventListener('click',()=>openDuplicate(item.id))
}
function showScreen(name){ state.currentScreen=name;document.querySelectorAll('.screen').forEach(x=>x.classList.toggle('is-active',x.id===`${name}-screen`));document.querySelectorAll('[data-screen]').forEach(x=>x.classList.toggle('is-active',x.dataset.screen===name));window.scrollTo({top:0,behavior:'smooth'}) }

document.addEventListener('click',async event=>{ const lead=event.target.closest('[data-lead]'),partner=event.target.closest('[data-partner]'),channel=event.target.closest('[data-channel]'),catalogBank=event.target.closest('[data-catalog-bank]'),onlineHelp=event.target.closest('[data-online-help]'),contactLink=event.target.closest('[data-contact-link]'),telegramChat=event.target.closest('[data-telegram-chat]'),staff=event.target.closest('[data-staff]'),duplicate=event.target.closest('[data-duplicate]'),sheetLink=event.target.closest('[data-sheet-link]');try{if(onlineHelp){event.preventDefault();event.stopPropagation();showOnlineHelp(onlineHelp.dataset.onlineHelp);return}if(contactLink){event.preventDefault();window.location.assign(contactLink.dataset.contactLink);return}if(telegramChat){event.preventDefault();const url=telegramChat.dataset.telegramChat,tg=telegramWebApp();tg?.openTelegramLink?tg.openTelegramLink(url):window.open(url,'_blank','noopener');return}if(lead)await openLead(lead.dataset.lead);if(partner)openPartner(partner.dataset.partner);if(channel)openChannel(channel.dataset.channel);if(catalogBank)openCatalogBank(catalogBank.dataset.catalogBank);if(staff&&state.session.role==='admin'){await api(`/api/staff/${staff.dataset.staff}/toggle`,{method:'POST'});toast('Доступ изменён');await load()}if(duplicate)openDuplicate(duplicate.dataset.duplicate);if(sheetLink){const url=state.session?.[sheetLink.dataset.sheetLink];if(url){const tg=telegramWebApp();tg?.openLink?tg.openLink(url):window.open(url,'_blank','noopener')}}}catch(error){toast(error.message)} })
document.querySelectorAll('[data-screen]').forEach(x=>x.addEventListener('click',()=>showScreen(x.dataset.screen)))
document.querySelectorAll('[data-go]').forEach(x=>x.addEventListener('click',()=>showScreen(x.dataset.go)))
document.querySelector('#close-sheet').addEventListener('click',closeSheet);document.querySelector('#sheet-backdrop').addEventListener('click',closeSheet);document.querySelector('#retry-button').addEventListener('click',load)
document.querySelector('#lead-search').addEventListener('input',renderVisibleLeads)
document.querySelector('#lead-scope').addEventListener('change',async event=>{state.leadScope=event.target.value;await load()})
async function downloadReport(){try{const partner=state.session?.role==='partner',path=partner?`/api/partner/report.xlsx?${partnerQuery()}`:'/api/reports/leads.csv',response=await fetch(path,{headers:{'X-Telegram-Init-Data':telegramInitData()}});if(!response.ok)throw new Error('Не удалось сформировать отчёт');const link=document.createElement('a');link.href=URL.createObjectURL(await response.blob());link.download=partner?'rko-partner-report.xlsx':'rko-leads.csv';link.click();setTimeout(()=>URL.revokeObjectURL(link.href),1000);toast('Отчёт сформирован')}catch(error){toast(error.message)}}
document.querySelector('#download-report').addEventListener('click',downloadReport)
document.querySelector('#partner-report').addEventListener('click',downloadReport)
document.querySelector('#partner-contact').addEventListener('click',()=>{const url=state.partnerData?.contact?.url;if(!url)return toast('Администратор ещё не назначен');const tg=telegramWebApp();tg?.openTelegramLink?tg.openTelegramLink(url):window.open(url,'_blank','noopener')})
document.querySelectorAll('#partner-filters select').forEach(select=>select.addEventListener('change',load))
document.querySelectorAll('#partner-date-from, #partner-date-to').forEach(input=>input.addEventListener('change',load))
document.querySelector('#admin-partner').addEventListener('change',()=>{document.querySelector('#admin-channel').value='';renderAdminFilters();renderVisibleLeads()})
document.querySelectorAll('#admin-channel, #admin-period, #admin-lead-status, #admin-payment-status').forEach(select=>select.addEventListener('change',()=>{renderAdminFilters();renderVisibleLeads()}))
document.querySelectorAll('#admin-date-from, #admin-date-to').forEach(input=>input.addEventListener('change',renderVisibleLeads))
document.querySelector('#open-google-sheet').addEventListener('click',()=>{const url=state.session?.google_sheet_url;if(!url)return;const tg=telegramWebApp();tg?.openLink?tg.openLink(url):window.open(url,'_blank','noopener')})
document.querySelector('#open-duplicate-reviews').addEventListener('click',openDuplicateQueue)
document.querySelector('#add-partner-button').addEventListener('click',openNewPartner)
document.querySelector('#add-bank-button').addEventListener('click',()=>openCatalogBank())
document.querySelector('#activation-info').addEventListener('click',()=>{openSheet('Условия активации','Как банк засчитывает результат','<section class="detail-section"><p class="info-copy">Активация счёта, или целевые действия, нужна, чтобы банк засчитал активность и сделал выплату. Условия устанавливает сам банк.</p><p class="info-copy">Деньги на активацию счетов обычно выделяем мы. Если вы хотите использовать свои деньги, сообщите об этом менеджеру.</p><p class="info-copy">После открытия счёта для его активации вас переведут на другого специалиста.</p></section><button class="primary-button" id="close-activation-info">Понятно</button>');document.querySelector('#close-activation-info').addEventListener('click',closeSheet)})
document.querySelector('#add-more-banks').addEventListener('click',()=>{state.leadAddingBanks=true;renderLeadCabinet();showScreen('client-banks')})
document.querySelector('#add-staff-button').addEventListener('click',()=>{openSheet('Новый сотрудник','Доступ','<section class="form-card"><label class="field"><span>Username без @</span><input id="staff-user" placeholder="Например, anutka_rko"></label><p class="field-note">Сотрудник получит доступ после первого запуска бота через /start.</p><label class="field"><span>Роль</span><select id="staff-role"><option value="manager">Менеджер</option><option value="admin">Администратор</option></select></label></section><button class="primary-button" id="create-staff">Добавить</button>');document.querySelector('#create-staff').addEventListener('click',async()=>{await api('/api/staff',{method:'POST',body:JSON.stringify({telegram_username:document.querySelector('#staff-user').value,role:document.querySelector('#staff-role').value})});toast('Приглашение добавлено');closeSheet();await load()})})
document.querySelector('#add-channel-button').addEventListener('click',()=>{openSheet('Новый канал','Источник трафика','<section class="form-card"><label class="field"><span>Название канала</span><input id="new-channel" maxlength="160" placeholder="Например, Telegram-канал"></label><p class="field-note">Для каждого источника создавайте отдельный канал — так будет видно, откуда пришла заявка.</p></section><button class="primary-button" id="create-channel">Создать ссылки</button>');document.querySelector('#create-channel').addEventListener('click',async()=>{try{const created=await api('/api/channels',{method:'POST',body:JSON.stringify({name:document.querySelector('#new-channel').value})});await load();openSheet(created.name,'Канал создан',`<section class="detail-section"><h3>Ссылки для новых заявок</h3><div class="value-row"><span>Источник</span><strong>${esc(created.name)}</strong></div></section>${referralLinkRows(created)}`);bindReferralLinkCopies(created)}catch(error){toast(error.message)}})})
load()
