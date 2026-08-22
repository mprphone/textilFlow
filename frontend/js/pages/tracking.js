import { crudList, get, post } from '../api.js';
import { badge, date, esc, number } from '../format.js?v=20260819-9';
import { loadOrderDossier } from '../production/dossier.js?v=20260822-13';
import { recordModal } from '../quick_create.js';
import { state } from '../state.js';
import { pageHeader } from '../ui.js?v=20260820-5';

const JOB_STATUS = {planned:'A enviar', sent:'No fornecedor', partial:'Parcial', received:'Recebido', problem:'Incidência', cancelled:'Anulado'};
const SERVICE = {sewing:'Confeção', dyeing:'Tinturaria', printing:'Estamparia', embroidery:'Bordado', laundry:'Lavandaria', finishing:'Acabamento', transport:'Transporte', cutting:'Corte', other:'Outro'};
const ACTIVE_PLAN = new Set(['planned', 'released', 'in_progress', 'confirmed']);

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

function jobOut(job) {
  if (['received', 'cancelled'].includes(job.status)) return 0;
  if (job.status === 'partial') return Math.max(0, (job.quantity || 0) - (job.accepted_quantity || 0) - (job.rejected_quantity || 0));
  return Math.max(0, job.quantity || 0);
}

function jobOverdue(job, today) {
  return job.expected_date && job.expected_date < today && ['sent', 'partial', 'planned'].includes(job.status);
}

function shippedQty(order) {
  return Number(order.custom_data?.shipped_quantity || 0);
}

function places(order, jobs, plans, maps) {
  const chips = [];
  jobs.forEach(job => {
    const qty = jobOut(job);
    if (!qty) return;
    const service = maps.serviceMap[job.subcontract_service_id];
    chips.push({
      kind: 'external',
      label: maps.supplierMap[job.supplier_id]?.name || 'Subcontrato',
      detail: `${SERVICE[service?.category] || service?.name || 'Serviço externo'} · ${JOB_STATUS[job.status] || job.status}`,
      qty,
    });
  });
  plans.filter(plan => plan.allocation_type === 'internal' && ACTIVE_PLAN.has(plan.status) && plan.line_id && plan.quantity > 0).forEach(plan => {
    chips.push({
      kind: 'internal',
      label: maps.lineMap[plan.line_id]?.name || 'Confeção',
      detail: 'Confeção interna',
      qty: plan.quantity,
    });
  });
  const shipped = shippedQty(order);
  if (shipped) chips.push({kind:'shipped', label:'Expedido', detail:'Já saiu para o cliente', qty: shipped});
  const used = chips.reduce((sum, chip) => sum + chip.qty, 0);
  let leftover = Math.max(0, (order.quantity || 0) - used);
  if (!chips.some(chip => chip.kind === 'internal') && order.line_id && leftover > 0) {
    chips.push({kind:'internal', label: maps.lineMap[order.line_id]?.name || 'Confeção', detail:'Confeção interna', qty: leftover});
    leftover = 0;
  }
  if (leftover > 0) chips.push({kind:'unassigned', label:'Por distribuir', detail:'Ainda sem destino', qty: leftover});
  return chips;
}

function qtyOf(chips, kind) {
  return chips.filter(chip => chip.kind === kind).reduce((sum, chip) => sum + chip.qty, 0);
}

function buildRows(orders, jobs, plans, maps, today) {
  const plansByOrder = {};
  plans.forEach(plan => { (plansByOrder[plan.production_order_id || 0] ||= []).push(plan); });
  return orders.filter(row => !['completed', 'cancelled'].includes(row.status)).map(order => {
    const related = maps.jobsByOrder[order.id] || [];
    const chips = places(order, related, plansByOrder[order.id] || [], maps);
    const late = Boolean(order.planned_end && order.planned_end < today);
    const stuck = related.some(job => job.status === 'problem' || jobOverdue(job, today));
    const mixed = chips.filter(chip => chip.qty > 0).length > 1;
    return {
      order, style: maps.styleMap[order.style_id], chips, jobs: related, late, stuck, mixed,
      internal: qtyOf(chips, 'internal'),
      external: qtyOf(chips, 'external'),
      unassigned: qtyOf(chips, 'unassigned'),
      shipped: qtyOf(chips, 'shipped'),
    };
  }).sort((a, b) => Number(b.stuck) - Number(a.stuck) || Number(b.late) - Number(a.late) || Number(b.unassigned > 0) - Number(a.unassigned > 0) || String(a.order.planned_end || '9').localeCompare(String(b.order.planned_end || '9')));
}

export async function render(container) {
  const [orders, jobs, styles, lines, suppliers, services, plans] = await Promise.all([
    crudList('production-orders', state.companyId, 'limit=2000'),
    crudList('subcontract-jobs', state.companyId, 'limit=2000'),
    crudList('styles', state.companyId, 'limit=2000'),
    crudList('production-lines', state.companyId, 'limit=2000'),
    crudList('suppliers', state.companyId, 'limit=2000'),
    crudList('subcontract-services', state.companyId, 'limit=2000'),
    crudList('sewing-plans', state.companyId, 'limit=2000'),
  ]);
  const today = todayIso();
  const maps = {
    styleMap: Object.fromEntries(styles.map(row => [row.id, row])),
    lineMap: Object.fromEntries(lines.map(row => [row.id, row])),
    supplierMap: Object.fromEntries(suppliers.map(row => [row.id, row])),
    serviceMap: Object.fromEntries(services.map(row => [row.id, row])),
    jobsByOrder: {},
  };
  jobs.forEach(job => { (maps.jobsByOrder[job.production_order_id || 0] ||= []).push(job); });
  const allRows = buildRows(orders, jobs, plans, maps, today);
  const counts = {
    all: allRows.length,
    mixed: allRows.filter(row => row.mixed).length,
    internal: allRows.filter(row => row.internal > 0).length,
    external: allRows.filter(row => row.external > 0).length,
    unassigned: allRows.filter(row => row.unassigned > 0).length,
    alert: allRows.filter(row => row.late || row.stuck).length,
  };
  const options = {
    lines: lines.filter(row => row.active !== false).map(row => ({value: row.id, label: row.name})),
    services: services.filter(row => row.active).map(row => ({value: row.id, label: `${row.code} · ${row.name} · ${maps.supplierMap[row.supplier_id]?.name || 'Fornecedor'}`, category: row.category})),
  };
  const openJobs = jobs.filter(job => jobOut(job) > 0)
    .sort((a, b) => Number(b.status === 'problem' || jobOverdue(b, today)) - Number(a.status === 'problem' || jobOverdue(a, today)) || String(a.expected_date || '9').localeCompare(String(b.expected_date || '9')));
  let filter = 'all';

  const draw = () => {
    const visible = allRows.filter(row => {
      if (filter === 'all') return true;
      if (filter === 'alert') return row.late || row.stuck;
      if (filter === 'mixed') return row.mixed;
      return row[filter] > 0;
    });
    container.innerHTML = pageHeader('Controlo da produção', 'Clique numa OF para ver produzido, distribuído, entregue, onde está e as matérias-primas. Uma ordem pode estar em vários sítios ao mesmo tempo.', '<a class="btn" href="#/corte">Planear corte</a><a class="btn" href="#/confection-map">Planear confeção</a><a class="btn" href="#/subcontracts">Subcontratos</a>', 'compact') + `
      <div class="track-kpis">
        <button type="button" data-track-filter="all" class="${filter==='all'?'active':''}"><span>OF ativas</span><strong>${number(counts.all)}</strong></button>
        <button type="button" data-track-filter="mixed" class="${filter==='mixed'?'active':''}"><span>Em vários sítios</span><strong>${number(counts.mixed)}</strong></button>
        <button type="button" data-track-filter="internal" class="${filter==='internal'?'active':''}"><span>Na confeção</span><strong>${number(counts.internal)}</strong></button>
        <button type="button" data-track-filter="external" class="${filter==='external'?'active':''}"><span>Em subcontrato</span><strong>${number(counts.external)}</strong></button>
        <button type="button" data-track-filter="unassigned" class="${filter==='unassigned'?'active':''}"><span>Por distribuir</span><strong>${number(counts.unassigned)}</strong></button>
        <button type="button" data-track-filter="alert" class="${filter==='alert'?'active':''}"><span>Atrasos / incidências</span><strong>${number(counts.alert)}</strong></button>
      </div>
      <section class="listing-panel"><div class="table-wrap listing-table"><table class="data-table track-table"><thead><tr><th>OF</th><th>Artigo</th><th>Onde está agora</th><th>Qtd.</th><th>Prazo</th><th>Alerta</th><th></th></tr></thead>
      <tbody>${visible.length ? visible.map(row => {
        const {order, style, chips, late, stuck, unassigned} = row;
        return `<tr class="${late || stuck || unassigned ? 'track-risk' : ''} track-row" data-open-order="${order.id}">
        <td><b>${esc(order.order_no)}</b></td>
        <td>${esc(style ? `${style.reference} · ${style.description}` : '—')}</td>
        <td><div class="track-splits">${chips.map(chip => `<span class="track-split ${chip.kind}"><b>${esc(chip.label)}</b><small>${number(chip.qty)} un. · ${esc(chip.detail)}</small></span>`).join('')}</div></td>
        <td>${number(order.completed_quantity)} / ${number(order.quantity)}</td>
        <td>${date(order.planned_end)}</td>
        <td>${stuck ? '<span class="track-flag">Incidência externa</span>' : late ? '<span class="track-flag late">Atraso</span>' : unassigned ? '<span class="track-flag wait">Distribuir</span>' : '—'}</td>
        <td class="listing-actions"><button class="btn small primary" data-distribute="${order.id}">Distribuir</button></td>
      </tr>`;
      }).join('') : '<tr><td colspan="7"><div class="empty"><strong>Nada neste filtro</strong>Não há OF neste estado.</div></td></tr>'}</tbody></table></div></section>
      ${openJobs.length ? `<section class="card track-jobs"><div class="card-header"><h2>Trabalhos fora de casa</h2><span>${number(openJobs.length)} envios abertos</span></div><div class="table-wrap"><table class="data-table"><thead><tr><th>Guia</th><th>OF</th><th>Serviço</th><th>Fornecedor</th><th>Qtd. fora</th><th>Estado</th><th>Regresso</th></tr></thead><tbody>
        ${openJobs.map(job => `<tr class="${jobOverdue(job, today) || job.status === 'problem' ? 'track-risk' : ''}"><td><b>${esc(job.reference)}</b></td><td>${esc(orders.find(row => row.id === job.production_order_id)?.order_no || 'Sem OF')}</td><td>${esc(maps.serviceMap[job.subcontract_service_id]?.name || SERVICE[maps.serviceMap[job.subcontract_service_id]?.category] || '—')}</td><td>${esc(maps.supplierMap[job.supplier_id]?.name || '—')}</td><td>${number(jobOut(job))}</td><td>${badge(JOB_STATUS[job.status] || job.status)}</td><td>${date(job.expected_date)}${jobOverdue(job, today) ? ' · atraso' : ''}</td></tr>`).join('')}
      </tbody></table></div></section>` : ''}`;
    container.querySelectorAll('[data-track-filter]').forEach(button => button.addEventListener('click', () => { filter = button.dataset.trackFilter; draw(); }));
    container.querySelectorAll('[data-distribute]').forEach(button => button.addEventListener('click', event => {
      event.stopPropagation();
      openDistribute(allRows.find(row => row.order.id === Number(button.dataset.distribute)), options, () => render(container));
    }));
    container.querySelectorAll('[data-open-order]').forEach(row => row.addEventListener('click', event => {
      if (event.target.closest('button')) return;
      loadOrderDossier(Number(row.dataset.openOrder));
    }));
  };
  draw();
}

function openDistribute(row, options, reload) {
  if (!row) return;
  const {order, unassigned, internal} = row;
  const defaultQty = unassigned || internal || 0;
  const defaultSource = unassigned ? 'unassigned' : 'internal';
  get(`/production/orders/${order.id}/trace`).then(data => {
    const steps = data.services || [];
    const current = steps.find(step => step.can_distribute && step.kind === 'external') || steps.find(step => step.status === 'ready');
    const sewingLocked = steps.some(step => step.key === 'sewing' && step.locked);
    const destinations = [];
    if (!sewingLocked) destinations.push({value:'internal', label:'Confeção interna'});
    destinations.push({value:'subcontract', label: current ? `Subcontrato · ${current.label} (só este)` : 'Subcontrato'});
    destinations.push({value:'shipped', label:'Expedição (já saiu)'});
    const serviceOptions = (options.services || []).filter(option => !current || current.kind !== 'external' || option.category === current.key);
    recordModal({
      title: `Distribuir ${order.order_no}`,
      values: {quantity: defaultQty, source: defaultSource, destination: current && current.kind === 'external' ? 'subcontract' : (sewingLocked ? 'subcontract' : 'internal')},
      fields: [
        {key:'quantity',label:'Quantidade',type:'number',required:true,section:'Quantidade',help:`Por distribuir ${number(unassigned)} · na confeção ${number(internal)} · total ${number(order.quantity)}${current ? ` · próximo passo: ${current.label}` : ''}`},
        {key:'source',label:'Sair de',type:'select',required:true,options:[{value:'unassigned',label:`Por distribuir (${number(unassigned)})`},{value:'internal',label:`Confeção interna (${number(internal)})`}],section:'Origem'},
        {key:'destination',label:'Enviar para',type:'select',required:true,options:destinations,section:'Destino'},
        {key:'line_id',label:'Linha de confeção',type:'select',options:options.lines,section:'Destino'},
        {key:'subcontract_service_id',label: current ? `Serviço (só ${current.label})` : 'Serviço e fornecedor',type:'select',options:serviceOptions.length ? serviceOptions : options.services,section:'Destino'},
      ],
      save: payload => post(`/production/orders/${order.id}/distribute`, payload),
      onSaved: reload,
    });
  }).catch(() => {
    recordModal({
      title: `Distribuir ${order.order_no}`,
      values: {quantity: defaultQty, source: defaultSource, destination: unassigned ? 'internal' : 'subcontract'},
      fields: [
        {key:'quantity',label:'Quantidade',type:'number',required:true,section:'Quantidade',help:`Por distribuir ${number(unassigned)} · na confeção ${number(internal)} · total ${number(order.quantity)}`},
        {key:'source',label:'Sair de',type:'select',required:true,options:[{value:'unassigned',label:`Por distribuir (${number(unassigned)})`},{value:'internal',label:`Confeção interna (${number(internal)})`}],section:'Origem'},
        {key:'destination',label:'Enviar para',type:'select',required:true,options:[{value:'internal',label:'Confeção interna'},{value:'subcontract',label:'Subcontrato'},{value:'shipped',label:'Expedição (já saiu)'}],section:'Destino'},
        {key:'line_id',label:'Linha de confeção',type:'select',options:options.lines,section:'Destino'},
        {key:'subcontract_service_id',label:'Serviço e fornecedor',type:'select',options:options.services,section:'Destino'},
      ],
      save: payload => post(`/production/orders/${order.id}/distribute`, payload),
      onSaved: reload,
    });
  });
}

export async function renderPrepared(container, kind) {
  const catalog = {
    dyeing: {title:'Tinturaria', body:'Capacidade, cubas e pessoas da tinturaria interna. Neste cliente o tingimento sai por subcontrato.'},
    printing: {title:'Estamparia', body:'Mesas, telas e pessoas da estamparia interna. Neste cliente a estampagem sai por subcontrato.'},
    corte: {title:'Corte', body:'Mesas, marcadores e o Gantt do planeamento. Abra Corte para arrastar as OFs pelos dias.'},
  }[kind] || {title:'Processo', body:'Módulo preparado para uma unidade interna futura.'};
  container.innerHTML = pageHeader(catalog.title, 'Módulo preparado · este cliente subcontrata.', '<a class="btn primary" href="#/subcontracts">Abrir subcontratos</a><a class="btn" href="#/tracking">Controlo da produção</a>', 'compact') + `
    <section class="card prepared-module">
      <p>${esc(catalog.body)}</p>
      <p>Quando existir internamente, máquinas e pessoas ficam <b>neste módulo</b>. O rasto da OF continua em Produção.</p>
    </section>`;
}
