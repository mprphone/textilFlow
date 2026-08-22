import { crudCreate, crudList, crudUpdate, get } from '../api.js';
import { renderEntityPage } from '../entity.js?v=20260819-9';
import { badge, date, esc, money, number } from '../format.js?v=20260819-9';
import { loadOrderDossier } from '../production/dossier.js?v=20260822-21';
import { stageLabel } from '../production/cycle.js?v=20260822-20';
import { recordModal } from '../quick_create.js';
import { state } from '../state.js';
import { pageHeader, toast } from '../ui.js?v=20260820-5';

const JOB_STATUS = {planned:'A enviar', sent:'No fornecedor', partial:'Receção parcial', received:'Recebido', problem:'Incidência', cancelled:'Anulado'};
const SERVICE = {dyeing:'Tinturaria', printing:'Estamparia', sewing:'Costura', cutting:'Corte fora', embroidery:'Bordado', laundry:'Lavandaria', finishing:'Acabamento', transport:'Transporte', other:'Outro'};
const namedOptions = (rows, label) => rows.map(row => ({value:row.id,label:label(row)}));
const todayIso = () => new Date().toISOString().slice(0, 10);
const CLOSED = new Set(['received', 'cancelled']);

function addDays(iso, days) {
  const parsed = new Date(`${iso}T12:00:00`);
  parsed.setDate(parsed.getDate() + days);
  return parsed.toISOString().slice(0, 10);
}

function dayDiff(iso, today) {
  if (!iso) return null;
  return Math.round((new Date(`${iso}T12:00:00`) - new Date(`${today}T12:00:00`)) / 86400000);
}

function dueLabel(job, today) {
  const days = dayDiff(job.expected_date, today);
  if (days === null) return {text:'Sem prazo', kind:'wait'};
  if (days < 0) return {text:`Atraso ${-days} d`, kind:'late'};
  if (days === 0) return {text:'Regressa hoje', kind:'today'};
  if (days <= 3) return {text:`Em ${days} d`, kind:'soon'};
  return {text:`Em ${days} d`, kind:'ok'};
}

function jobPayload(job, patch = {}) {
  return {
    company_id: state.companyId,
    production_order_id: job.production_order_id || null,
    subcontract_service_id: job.subcontract_service_id,
    supplier_id: job.supplier_id,
    reference: job.reference,
    quantity: job.quantity,
    unit: job.unit,
    unit_cost: job.unit_cost,
    actual_cost: job.actual_cost,
    sent_date: job.sent_date,
    expected_date: job.expected_date,
    received_date: job.received_date,
    status: job.status,
    accepted_quantity: job.accepted_quantity,
    rejected_quantity: job.rejected_quantity,
    notes: job.notes,
    ...patch,
  };
}

export async function render(container) {
  const [suppliers, services, orders, jobs, styles] = await Promise.all([
    crudList('suppliers', state.companyId, 'limit=2000'),
    crudList('subcontract-services', state.companyId, 'limit=2000'),
    crudList('production-orders', state.companyId, 'limit=2000'),
    crudList('subcontract-jobs', state.companyId, 'limit=2000'),
    crudList('styles', state.companyId, 'limit=2000'),
  ]);
  const maps = {
    supplierById: Object.fromEntries(suppliers.map(row => [row.id, row])),
    serviceById: Object.fromEntries(services.map(row => [row.id, row])),
    orderById: Object.fromEntries(orders.map(row => [row.id, row])),
    styleById: Object.fromEntries(styles.map(row => [row.id, row])),
  };
  const options = {
    supplier: namedOptions(suppliers.filter(row => row.active), row => row.name),
    service: namedOptions(services.filter(row => row.active), row => `${row.code} · ${row.name} · ${maps.supplierById[row.supplier_id]?.name || 'Fornecedor'}`),
    order: namedOptions(orders.filter(row => !['completed', 'cancelled'].includes(row.status)), row => `${row.order_no} · ${number(row.quantity)} un.`),
  };
  let tab = 0;
  container.innerHTML = `<div class="tabs"><button class="tab active" data-sub-tab="0">Controlo</button><button class="tab" data-sub-tab="1">Tabela de serviços</button></div><div data-tab-panel></div>`;
  const panel = container.querySelector('[data-tab-panel]');
  container.querySelector('.tabs').addEventListener('click', async event => {
    const button = event.target.closest('[data-sub-tab]');
    if (!button) return;
    tab = Number(button.dataset.subTab);
    container.querySelectorAll('[data-sub-tab]').forEach(item => item.classList.toggle('active', item === button));
    if (tab === 1) await renderEntityPage(panel, serviceCatalog(options, maps));
    else await drawBoard(panel, jobs, maps, options, () => render(container));
  });
  await drawBoard(panel, jobs, maps, options, () => render(container));
}

function stockCell(trace) {
  const rows = (trace && (trace.materials || []).length) ? trace.materials : [];
  if (!rows.length) return '<small class="muted">Sem explosão de MP nesta OF</small>';
  return `<div class="stock-cell">${rows.map(row => {
    const unit = row.unit || '';
    const others = (row.allocations || []).filter(item => Number(item.reserved_quantity) > 0)
      .map(item => `${item.order_no}: ${number(item.reserved_quantity)}`).join(', ');
    return `<span class="table-subline"><b>${esc(row.material_name || row.description || 'Material')}</b> · armazém ${number(row.on_hand_quantity)} ${esc(unit)} · outras OF ${number(row.allocated_other_quantity)} · livre ${number(row.available_quantity)}${others ? ` · ${esc(others)}` : ''}</span>`;
  }).join('')}</div>`;
}

async function loadTraces(jobs) {
  const traces = {};
  const ids = [...new Set(jobs.map(job => job.production_order_id).filter(Boolean))];
  await Promise.all(ids.slice(0, 40).map(async id => {
    try { traces[id] = await get(`/production/orders/${id}/trace`); }
    catch { traces[id] = null; }
  }));
  return traces;
}

async function drawBoard(container, jobs, maps, options, reload) {
  const today = todayIso();
  const open = jobs.filter(job => !CLOSED.has(job.status));
  const overdue = open.filter(job => job.expected_date && job.expected_date < today && ['sent', 'partial', 'planned'].includes(job.status));
  const dueSoon = open.filter(job => {
    const days = dayDiff(job.expected_date, today);
    return days !== null && days >= 0 && days <= 3;
  });
  const counts = {
    open: open.length,
    planned: open.filter(job => job.status === 'planned').length,
    sent: open.filter(job => ['sent', 'partial'].includes(job.status)).length,
    soon: dueSoon.length,
    late: overdue.length,
    problem: open.filter(job => job.status === 'problem').length,
  };
  let filter = counts.late ? 'late' : 'open';
  let category = 'all';
  let pageSize = 50;
  let page = 1;
  let search = '';
  const traces = await loadTraces(jobs);
  const categories = [...new Set(jobs.map(job => maps.serviceById[job.subcontract_service_id]?.category).filter(Boolean))];

  const matches = job => {
    const service = maps.serviceById[job.subcontract_service_id];
    if (category !== 'all' && service?.category !== category) return false;
    if (filter === 'open') return !CLOSED.has(job.status);
    if (filter === 'planned') return job.status === 'planned';
    if (filter === 'sent') return ['sent', 'partial'].includes(job.status);
    if (filter === 'soon') return dueSoon.includes(job);
    if (filter === 'late') return overdue.includes(job);
    if (filter === 'problem') return job.status === 'problem';
    if (filter === 'closed') return CLOSED.has(job.status);
    return true;
  };

  const paint = () => {
    const visible = jobs.filter(matches).sort((a, b) => {
      const rank = job => (job.status === 'problem' ? 3 : overdue.includes(job) ? 2 : dueSoon.includes(job) ? 1 : 0);
      return rank(b) - rank(a) || String(a.expected_date || '9').localeCompare(String(b.expected_date || '9'));
    });
    const found = visible.filter(job => {
      if (!search) return true;
      const service = maps.serviceById[job.subcontract_service_id];
      const order = maps.orderById[job.production_order_id];
      const style = order ? maps.styleById[order.style_id] : null;
      const hay = [job.reference, order?.order_no, style?.reference, style?.description, service?.name, maps.supplierById[job.supplier_id]?.name, JOB_STATUS[job.status]].join(' ').toLowerCase();
      return hay.includes(search);
    });
    const pages = Math.max(1, Math.ceil(found.length / pageSize));
    page = Math.min(page, pages);
    const slice = found.slice((page - 1) * pageSize, page * pageSize);
    const start = found.length ? (page - 1) * pageSize + 1 : 0;
    const end = Math.min(page * pageSize, found.length);
    container.innerHTML = pageHeader('Controlo de subcontratos', 'Tinturaria e serviços fora. O stock da OF aparece ao lado — o mesmo lote não é prometido a duas encomendas.', '<a class="btn" href="#/tracking">Controlo da produção</a><a class="btn" href="#/erp-docs">ERP / guias</a><button class="btn primary" data-new-job>+ Novo envio</button>', 'compact') + `
      <div class="cycle-banner">
        <div>
          <b>Ciclo desta fábrica</b>
          Matérias (alocadas à OF) → tinturaria → corte interno → costura casa ou fora → revista → outros serviços → embalagem → expedição.
          <small>Isto é o normal. Se esta encomenda tiver de sair da sequência, use a excepção. Corte fora só em casos pontuais.</small>
        </div>
      </div>
      <div class="proposal-list-toolbar">
        <div class="proposal-stage-filters">
          <button type="button" data-sub-filter="open" class="${filter==='open'?'active':''}">Fora de casa <b>${number(counts.open)}</b></button>
          <button type="button" data-sub-filter="planned" class="${filter==='planned'?'active':''}">A enviar <b>${number(counts.planned)}</b></button>
          <button type="button" data-sub-filter="sent" class="${filter==='sent'?'active':''}">No fornecedor <b>${number(counts.sent)}</b></button>
          <button type="button" data-sub-filter="soon" class="${filter==='soon'?'active':''}">Regresso 3 dias <b>${number(counts.soon)}</b></button>
          <button type="button" data-sub-filter="late" class="${filter==='late'?'active':''}">Atrasos <b>${number(counts.late)}</b></button>
          <button type="button" data-sub-filter="problem" class="${filter==='problem'?'active':''}">Incidências <b>${number(counts.problem)}</b></button>
        </div>
        <label class="sub-closed"><input type="checkbox" data-show-closed ${filter==='closed'?'checked':''}> Ver recebidos</label>
      </div>
      <div class="sub-cats">${[['all','Todos os processos'], ...categories.map(key => [key, SERVICE[key] || key])].map(([key, label]) => `<button type="button" class="sub-cat ${category===key?'active':''}" data-sub-cat="${key}">${esc(label)}</button>`).join('')}</div>
      <section class="listing-panel">
        <div class="listing-bar">
          <label class="listing-size">Mostrar <select data-page-size><option ${pageSize===25?'selected':''}>25</option><option ${pageSize===50?'selected':''}>50</option><option ${pageSize===100?'selected':''}>100</option></select> registos</label>
          <div class="table-search"><span>⌕</span><input class="filter-input" data-sub-search value="${esc(search)}" placeholder="Procurar guia, OF, fornecedor…"></div>
        </div>
        <div class="table-wrap listing-table"><table class="data-table"><thead><tr><th>Guia</th><th>OF / artigo</th><th>Fase da OF</th><th>Stock MP</th><th>Processo</th><th>Fornecedor</th><th>Quantidade</th><th>Regresso</th><th>Estado</th><th></th></tr></thead>
        <tbody>${slice.length ? slice.map(job => {
        const service = maps.serviceById[job.subcontract_service_id];
        const order = maps.orderById[job.production_order_id];
        const style = order ? maps.styleById[order.style_id] : null;
        const due = dueLabel(job, today);
        const risk = job.status === 'problem' || overdue.includes(job);
        const trace = traces[job.production_order_id];
        return `<tr class="${risk?'track-risk':''}">
          <td><b>${esc(job.reference)}</b><small class="table-subline">Saída ${date(job.sent_date)}</small></td>
          <td>${order ? `<b>${esc(order.order_no)}</b>` : 'Sem OF'}${style ? `<small class="table-subline">${esc(style.reference)} · ${esc(style.description)}</small>` : ''}</td>
          <td>${order ? badge(stageLabel(trace?.order?.current_stage || order.current_stage)) : '—'}</td>
          <td>${job.production_order_id ? stockCell(trace) : '—'}</td>
          <td>${badge(SERVICE[service?.category] || service?.category || 'Outro')}<small class="table-subline">${esc(service?.name || '—')}</small></td>
          <td>${esc(maps.supplierById[job.supplier_id]?.name || '—')}</td>
          <td>${number(job.quantity)} ${esc(job.unit)}${job.accepted_quantity || job.rejected_quantity ? `<small class="table-subline">${number(job.accepted_quantity)} aceites · ${number(job.rejected_quantity)} rejeitadas</small>` : ''}</td>
          <td>${date(job.expected_date)}<small class="table-subline"><span class="track-flag ${due.kind==='late'||due.kind==='today'?'late':due.kind==='soon'?'soon':'wait'}">${esc(due.text)}</span></small></td>
          <td>${badge(JOB_STATUS[job.status] || job.status)}</td>
          <td class="listing-actions">${jobActions(job)}</td>
        </tr>`;
      }).join('') : '<tr><td colspan="10"><div class="empty"><strong>Nada neste filtro</strong>Não há trabalhos externos neste estado.</div></td></tr>'}</tbody></table></div>
        <div class="list-pager"><span>${found.length ? `Mostrar ${start} a ${end} de ${found.length} registos` : 'Mostrar 0 registos'}</span><div><button class="btn small" data-list-page="${page-1}" ${page<=1?'disabled':''}>← Anterior</button><button class="btn small" data-list-page="${page+1}" ${page>=pages?'disabled':''}>Seguinte →</button></div></div>
      </section>`;
    container.querySelectorAll('[data-sub-filter]').forEach(button => button.addEventListener('click', () => { filter = button.dataset.subFilter; page = 1; paint(); }));
    container.querySelectorAll('[data-sub-cat]').forEach(button => button.addEventListener('click', () => { category = button.dataset.subCat; page = 1; paint(); }));
    container.querySelector('[data-show-closed]')?.addEventListener('change', event => { filter = event.currentTarget.checked ? 'closed' : 'open'; page = 1; paint(); });
    container.querySelector('[data-page-size]')?.addEventListener('change', event => { pageSize = Number(event.target.value); page = 1; paint(); });
    container.querySelector('[data-sub-search]')?.addEventListener('input', event => {
      search = event.currentTarget.value.trim().toLowerCase();
      page = 1;
      const caret = event.currentTarget.selectionStart;
      paint();
      const next = container.querySelector('[data-sub-search]');
      if (next) { next.focus(); next.setSelectionRange(caret, caret); }
    });
    container.querySelectorAll('[data-list-page]').forEach(button => button.addEventListener('click', () => { page = Number(button.dataset.listPage); paint(); }));
    container.querySelector('[data-new-job]')?.addEventListener('click', () => openJob(null, maps, options, reload));
    container.querySelectorAll('[data-job-edit]').forEach(button => button.addEventListener('click', () => openJob(jobs.find(row => row.id === Number(button.dataset.jobEdit)), maps, options, reload)));
    container.querySelectorAll('[data-job-send]').forEach(button => button.addEventListener('click', () => act(jobs.find(row => row.id === Number(button.dataset.jobSend)), maps, reload)));
    container.querySelectorAll('[data-job-receive]').forEach(button => button.addEventListener('click', () => receiveJob(jobs.find(row => row.id === Number(button.dataset.jobReceive)), maps, reload)));
    container.querySelectorAll('[data-job-problem]').forEach(button => button.addEventListener('click', () => problemJob(jobs.find(row => row.id === Number(button.dataset.jobProblem)), reload)));
    container.querySelectorAll('[data-open-of]').forEach(button => button.addEventListener('click', () => loadOrderDossier(Number(button.dataset.openOf))));
  };
  paint();
}

function jobActions(job) {
  const ofBtn = job.production_order_id ? `<button class="btn small" data-open-of="${job.production_order_id}">Ver OF</button>` : '';
  if (job.status === 'planned') {
    return `<button class="btn small primary" data-job-send="${job.id}">Enviar</button><button class="btn small" data-job-edit="${job.id}">Editar</button>${ofBtn}`;
  }
  if (['sent', 'partial'].includes(job.status)) {
    return `<button class="btn small primary" data-job-receive="${job.id}">Receber</button><button class="btn small" data-job-problem="${job.id}">Incidência</button>${ofBtn}`;
  }
  if (job.status === 'problem') {
    return `<button class="btn small primary" data-job-receive="${job.id}">Receber</button><button class="btn small" data-job-edit="${job.id}">Notas</button>${ofBtn}`;
  }
  return `<button class="btn small" data-job-edit="${job.id}">Ver</button>${ofBtn}`;
}

function jobFields(maps, options, job) {
  const order = job ? maps.orderById[job.production_order_id] : null;
  const remaining = order ? Math.max(0, (order.quantity || 0) - (order.completed_quantity || 0)) : 0;
  return [
    {key:'reference',label:'Guia / referência',help:'Vazio gera EXT-AAAAMMDD-001',section:'Ligação'},
    {key:'production_order_id',label:'Ordem de fabrico',type:'select',options:options.order,section:'Ligação'},
    {key:'subcontract_service_id',label:'Serviço e fornecedor',type:'select',required:true,options:options.service,section:'Ligação'},
    {key:'quantity',label:'Quantidade enviada',type:'number',required:true,default:remaining || 0,section:'Quantidade e custo'},
    {key:'unit',label:'Unidade',default:'un',section:'Quantidade e custo'},
    {key:'unit_cost',label:'Preço acordado',type:'number',default:0,section:'Quantidade e custo'},
    {key:'actual_cost',label:'Custo real faturado',type:'number',default:0,section:'Quantidade e custo'},
    {key:'sent_date',label:'Data de saída',type:'date',section:'Prazos'},
    {key:'expected_date',label:'Regresso previsto',type:'date',help:'Se vazio, usa o prazo do serviço após enviar',section:'Prazos'},
    {key:'received_date',label:'Receção real',type:'date',section:'Prazos'},
    {key:'status',label:'Estado',type:'select',options:[{value:'planned',label:'A enviar'},{value:'sent',label:'No fornecedor'},{value:'partial',label:'Receção parcial'},{value:'received',label:'Recebido'},{value:'problem',label:'Incidência'},{value:'cancelled',label:'Anulado'}],default:'planned',section:'Receção'},
    {key:'accepted_quantity',label:'Quantidade aceite',type:'number',default:0,section:'Receção'},
    {key:'rejected_quantity',label:'Quantidade rejeitada',type:'number',default:0,section:'Receção'},
    {key:'notes',label:'Notas / incidências',type:'textarea',full:true,section:'Receção'},
  ];
}

function fillFromCatalog(payload, maps) {
  const service = maps.serviceById[payload.subcontract_service_id];
  if (!service) return payload;
  payload.supplier_id = service.supplier_id;
  if (!payload.unit || payload.unit === 'un') payload.unit = service.unit || payload.unit;
  if (!payload.unit_cost) payload.unit_cost = service.unit_cost;
  if (!payload.quantity) {
    const order = maps.orderById[payload.production_order_id];
    if (order) payload.quantity = Math.max(0, (order.quantity || 0) - (order.completed_quantity || 0));
  }
  return payload;
}

function openJob(job, maps, options, reload) {
  const defaults = job || {
    status: 'planned',
    sent_date: todayIso(),
    quantity: 0,
    unit: 'un',
    unit_cost: 0,
  };
  recordModal({
    title: job ? `Editar ${job.reference}` : 'Novo envio externo',
    values: defaults,
    fields: jobFields(maps, options, job),
    transform: payload => fillFromCatalog(payload, maps),
    save: payload => job ? crudUpdate('subcontract-jobs', job.id, jobPayload(job, payload)) : crudCreate('subcontract-jobs', payload),
    onSaved: reload,
  });
}

async function act(job, maps, reload) {
  if (!job) return;
  const service = maps.serviceById[job.subcontract_service_id];
  const sent = job.sent_date || todayIso();
  const expected = job.expected_date || (service?.lead_time_days ? addDays(sent, service.lead_time_days) : sent);
  try {
    await crudUpdate('subcontract-jobs', job.id, jobPayload(job, {status:'sent', sent_date:sent, expected_date:expected}));
    toast(`Enviado. Regresso previsto ${date(expected)}.`);
    await reload();
  } catch (error) { toast(error.message, 'error'); }
}

function receiveJob(job, maps, reload) {
  const remaining = Math.max(0, (job.quantity || 0) - (job.accepted_quantity || 0) - (job.rejected_quantity || 0));
  recordModal({
    title: `Receber ${job.reference}`,
    values: {accepted_quantity: remaining || job.quantity, rejected_quantity: 0, received_date: todayIso(), actual_cost: job.actual_cost || job.planned_cost, notes: job.notes || ''},
    fields: [
      {key:'accepted_quantity',label:'Quantidade aceite',type:'number',required:true,section:'Receção'},
      {key:'rejected_quantity',label:'Quantidade rejeitada',type:'number',default:0,section:'Receção'},
      {key:'received_date',label:'Data de receção',type:'date',required:true,section:'Receção'},
      {key:'actual_cost',label:'Custo faturado',type:'number',section:'Custo'},
      {key:'notes',label:'Notas',type:'textarea',full:true,section:'Custo'},
    ],
    save: payload => {
      const handled = Number(payload.accepted_quantity || 0) + Number(payload.rejected_quantity || 0);
      const status = handled < (job.quantity || 0) ? 'partial' : 'received';
      return crudUpdate('subcontract-jobs', job.id, jobPayload(job, {...payload, status}));
    },
    onSaved: reload,
  });
}

function problemJob(job, reload) {
  recordModal({
    title: `Incidência · ${job.reference}`,
    values: {notes: job.notes || ''},
    fields: [{key:'notes',label:'O que aconteceu',type:'textarea',required:true,full:true,section:'Incidência'}],
    save: payload => crudUpdate('subcontract-jobs', job.id, jobPayload(job, {status:'problem', notes: payload.notes})),
    onSaved: reload,
  });
}

function serviceCatalog(options, maps) {
  return {
    resource:'subcontract-services',title:'Serviços subcontratados',subtitle:'Preços acordados, prazos e fornecedores usados nos envios.',singular:'serviço',newLabel:'Novo serviço',
    extraActions:'<a class="btn" href="#/partners">Fornecedores</a>',
    fields:[
      {key:'code',label:'Código',required:true,section:'Identificação'},{key:'name',label:'Serviço',required:true,section:'Identificação'},
      {key:'supplier_id',label:'Fornecedor',type:'select',required:true,options:options.supplier,section:'Identificação'},
      {key:'category',label:'Tipo',type:'select',options:[{value:'dyeing',label:'Tinturaria'},{value:'printing',label:'Estamparia'},{value:'sewing',label:'Costura'},{value:'cutting',label:'Corte (excepção)'},{value:'embroidery',label:'Bordado'},{value:'laundry',label:'Lavandaria'},{value:'finishing',label:'Acabamento'},{value:'transport',label:'Transporte'},{value:'other',label:'Outro'}],default:'other',section:'Condições'},
      {key:'unit',label:'Unidade',required:true,default:'un',section:'Condições'},{key:'unit_cost',label:'Preço acordado',type:'number',required:true,default:0,section:'Condições'},
      {key:'minimum_quantity',label:'Quantidade mínima',type:'number',default:0,section:'Condições'},{key:'lead_time_days',label:'Prazo (dias)',type:'number',default:0,section:'Condições'},
      {key:'quality_score',label:'Qualidade (%)',type:'number',default:100,section:'Controlo'},{key:'active',label:'Estado',type:'checkbox',default:true,help:'Disponível em novas propostas',section:'Controlo'},
      {key:'notes',label:'Notas e condições',type:'textarea',full:true,section:'Controlo'},
    ],
    columns:[
      {key:'code',label:'Código',render:r=>`<b>${esc(r.code)}</b>`},{key:'name',label:'Serviço'},
      {key:'supplier_id',label:'Fornecedor',render:r=>esc(maps.supplierById[r.supplier_id]?.name || '—')},{key:'category',label:'Tipo',render:r=>esc(SERVICE[r.category]||r.category)},
      {key:'unit_cost',label:'Preço',render:r=>`<b>${money(r.unit_cost)} / ${esc(r.unit)}</b>`},{key:'minimum_quantity',label:'Mínimo',render:r=>`${number(r.minimum_quantity)} ${esc(r.unit)}`},
      {key:'lead_time_days',label:'Prazo',render:r=>`${number(r.lead_time_days)} dias`},{key:'quality_score',label:'Qualidade',render:r=>`${number(r.quality_score)}%`},{key:'active',label:'Estado',render:r=>badge(r.active?'ativo':'inativo')},
    ],
  };
}
