import { crudList, get, post } from '../api.js';
import { on } from '../events.js?v=20260822-30';
import { badge, date, esc, number } from '../format.js?v=20260819-9';
import { readForm, renderForm } from '../forms.js?v=20260822-2';
import { loadOrderDossier } from '../production/dossier.js?v=20260822-21';
import { state } from '../state.js';
import { closeModal, openModal, pageHeader, toast } from '../ui.js?v=20260820-5';
import { startSupplierOrder } from './commercial_docs.js?v=20260822-31';

const JOB_STATUS = {planned:'A enviar', sent:'No fornecedor', partial:'Parcial', received:'Recebido', problem:'Incidência', cancelled:'Anulado'};
const SERVICE = {sewing:'Confeção', dyeing:'Tinturaria', printing:'Estamparia', embroidery:'Bordado', laundry:'Lavandaria', finishing:'Acabamento', transport:'Transporte', cutting:'Corte', other:'Outro'};
const ACTIVE_PLAN = new Set(['planned', 'released', 'in_progress', 'confirmed']);
let stopOps = null;

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
  stopOps?.();
  stopOps = on('ops-changed', () => {
    if (!container.isConnected) { stopOps?.(); return; }
    render(container).catch(() => {});
  });
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
    services: services.filter(row => row.active).map(row => ({value: row.id, label: `${row.code} · ${row.name} · ${maps.supplierMap[row.supplier_id]?.name || 'Fornecedor'}`, category: row.category, supplier_id: row.supplier_id})),
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
    container.innerHTML = pageHeader('Controlo da produção', 'A produção vai até à costura. A revista está no menu Revista e Qualidade; a embalagem e a saída no menu Embalagem / Expedição.', '<a class="btn" href="#/revista">Revista</a><a class="btn" href="#/embalagem">Embalagem</a><a class="btn" href="#/corte">Corte</a><a class="btn" href="#/subcontracts">Serviços fora</a>', 'compact') + `
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
      ${openJobs.length ? `<section class="card track-jobs"><div class="card-header"><h2>Trabalhos fora de casa</h2><span>${number(openJobs.length)} envios abertos</span></div><div class="table-wrap"><table class="data-table"><thead><tr><th>Guia</th><th>OF</th><th>Serviço</th><th>Fornecedor</th><th>Qtd. fora</th><th>Estado</th><th>Regresso</th><th></th></tr></thead><tbody>
        ${openJobs.map(job => `<tr class="${jobOverdue(job, today) || job.status === 'problem' ? 'track-risk' : ''}"><td><b>${esc(job.reference)}</b></td><td>${esc(orders.find(row => row.id === job.production_order_id)?.order_no || 'Sem OF')}</td><td>${esc(maps.serviceMap[job.subcontract_service_id]?.name || SERVICE[maps.serviceMap[job.subcontract_service_id]?.category] || '—')}</td><td>${esc(maps.supplierMap[job.supplier_id]?.name || '—')}</td><td>${number(jobOut(job))}</td><td>${badge(JOB_STATUS[job.status] || job.status)}</td><td>${date(job.expected_date)}${jobOverdue(job, today) ? ' · atraso' : ''}</td><td class="listing-actions"><button class="btn small" data-job-transport="${job.id}">Guia de transporte</button></td></tr>`).join('')}
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
    container.querySelectorAll('[data-job-transport]').forEach(button => button.addEventListener('click', async event => {
      event.stopPropagation();
      const job = jobs.find(item => item.id === Number(button.dataset.jobTransport));
      if (!job) return;
      const relatedOrder = orders.find(item => item.id === job.production_order_id);
      const styleRow = relatedOrder ? maps.styleMap[relatedOrder.style_id] : null;
      try {
        await startSupplierOrder({
          supplier_id: job.supplier_id || maps.serviceMap[job.subcontract_service_id]?.supplier_id,
          style_id: relatedOrder?.style_id,
          code: styleRow?.reference || '',
          description: styleRow?.description || '',
          quantity: jobOut(job),
          unit: job.unit || 'un',
          extra: {subcontract_job_id: job.id, production_order_id: job.production_order_id},
        }, 'supplier_transport');
      } catch (error) { toast(error.message, 'error'); }
    }));
  };
  draw();
}

const STEP_STATUS = {
  locked: {label: 'Bloqueado', cls: 'red'},
  ready: {label: 'Pronto', cls: 'green'},
  in_progress: {label: 'Em curso', cls: 'amber'},
  done: {label: 'Concluído', cls: 'green'},
};

function stepBadge(status) {
  const meta = STEP_STATUS[status] || {label: status || '—', cls: 'blue'};
  return `<span class="badge ${meta.cls}">${esc(meta.label)}</span>`;
}

function distributeFields(order, row, current, sewingLocked, options) {
  const {unassigned, internal} = row;
  const destinations = [
    {value: 'internal', label: sewingLocked ? 'Confeção interna (fora de sequência)' : 'Confeção interna'},
    {value: 'subcontract', label: current ? `Serviço externo · recomendado: ${current.label}` : 'Serviço externo (tinturaria / costura / outros)'},
    {value: 'shipped', label: 'Expedição (já saiu)'},
  ];
  return [
    {key: 'quantity', label: 'Quantidade', type: 'number', required: true, section: 'Quantidade', help: `Por distribuir ${number(unassigned)} · na confeção ${number(internal)} · total ${number(order.quantity)}${current ? ` · passo recomendado: ${current.label}` : ''}`},
    {key: 'source', label: 'Sair de', type: 'select', required: true, options: [{value: 'unassigned', label: `Por distribuir (${number(unassigned)})`}, {value: 'internal', label: `Confeção interna (${number(internal)})`}], section: 'Origem'},
    {key: 'destination', label: 'Enviar para', type: 'select', required: true, options: destinations, section: 'Destino'},
    {key: 'line_id', label: 'Linha de confeção', type: 'select', options: options.lines, section: 'Destino'},
    {key: 'subcontract_service_id', label: 'Serviço e fornecedor', type: 'select', options: options.services, section: 'Destino'},
    {key: 'planned_date', label: 'Data prevista', type: 'date', section: 'Destino', help: 'Opcional — início na confeção interna ou envio ao serviço.'},
    {key: 'override', label: 'Exceção — avançar mesmo fora da sequência', type: 'checkbox', section: 'Exceção', help: 'Use só quando esta encomenda tiver de sair do ciclo normal.'},
  ];
}

function quantitiesTabHtml(order, row, steps) {
  const {internal, external, shipped} = row;
  return `
    <div class="qty-summary">
      <div class="qty-card"><span>Encomendada</span><strong>${number(order.quantity)}</strong></div>
      <div class="qty-card"><span>Em produção</span><strong>${number(internal + external)}</strong><small>${number(internal)} interna · ${number(external)} externa</small></div>
      <div class="qty-card"><span>Terminada</span><strong>${number(order.completed_quantity)}</strong></div>
      <div class="qty-card"><span>Enviada</span><strong>${number(shipped)}</strong></div>
    </div>
    ${steps.length ? `<div class="qty-steps">${steps.map(step => `
      <div class="qty-step">
        <div class="qty-step-head"><b>${esc(step.label)}</b>${stepBadge(step.status)}</div>
        <small>${number(step.quantity_sent ?? step.out_quantity ?? 0)} enviada${step.quantity_received != null ? ` · ${number(step.quantity_received)} recebida/produzida` : ''}${step.reason ? ` · ${esc(step.reason)}` : ''}</small>
      </div>`).join('')}</div>` : '<p class="muted">Sem sequência configurada para este artigo — segue a ordem por omissão (corte → confeção → serviços externos).</p>'}
  `;
}

function trancheRowHtml(index) {
  return `<tr data-tranche-row="${index}">
    <td><input type="number" min="0.01" step="any" placeholder="Quantidade" data-tr-qty></td>
    <td><input type="date" data-tr-date></td>
    <td class="tranche-status" data-tr-status>—</td>
    <td><button type="button" class="btn icon ghost" data-remove-tranche aria-label="Remover linha">×</button></td>
  </tr>`;
}

function datesTabHtml() {
  return `
    <p class="muted tranche-intro">As linhas usam a origem, o destino e a exceção escolhidos no separador "Distribuir" — aqui só varia a quantidade e a data.</p>
    <table class="data-table tranche-table">
      <thead><tr><th>Quantidade</th><th>Data</th><th>Estado</th><th></th></tr></thead>
      <tbody data-tranche-rows>${trancheRowHtml(0)}</tbody>
    </table>
    <button type="button" class="btn small" data-add-tranche>+ Adicionar linha</button>
    <div class="form-footer">
      <button type="button" class="btn" data-close-modal>Fechar</button>
      <button type="button" class="btn primary" data-save-tranches>Distribuir linhas</button>
    </div>
    <p class="muted tranche-note">Cada linha é aplicada uma a uma. Se uma falhar, as anteriores mantêm-se — o estado de cada linha aparece na tabela.</p>
  `;
}

function openDistribute(row, options, reload) {
  if (!row) return;
  const {order, unassigned, internal, style} = row;
  const defaultQty = unassigned || internal || 0;
  const defaultSource = unassigned ? 'unassigned' : 'internal';

  get(`/production/orders/${order.id}/trace`).then(data => data.services || []).catch(() => []).then(steps => {
    const current = steps.find(step => step.can_distribute && step.kind === 'external') || steps.find(step => step.status === 'ready');
    const sewingLocked = steps.some(step => step.key === 'sewing' && step.locked);
    const fields = distributeFields(order, row, current, sewingLocked, options);
    const defaultDestination = current && current.kind === 'external' && !sewingLocked ? 'subcontract' : 'internal';
    const values = {quantity: defaultQty, source: defaultSource, destination: defaultDestination};

    openModal(`Distribuir ${order.order_no}`, `
      <div class="tabs distribute-tabs">
        <button type="button" class="tab active" data-tab="distribute">Distribuir</button>
        <button type="button" class="tab" data-tab="quantities">Quantidades</button>
        <button type="button" class="tab" data-tab="dates">Datas</button>
      </div>
      <div data-tab-panel="distribute">
        ${renderForm(fields, values, {formId: 'distribute-form'})}
        <div class="transport-action" data-transport-action hidden>
          <button type="button" class="btn" data-transport-guide>Guia de transporte</button>
          <small class="muted">Cria a guia de transporte (GTS) para o fornecedor do serviço, já com o artigo e a quantidade preenchidos, e abre no ERP.</small>
        </div>
      </div>
      <div data-tab-panel="quantities" hidden>${quantitiesTabHtml(order, row, steps)}</div>
      <div data-tab-panel="dates" hidden>${datesTabHtml()}</div>
    `, 'A sequência é uma recomendação. Se a encomenda sair do normal, marque a exceção.');

    const body = document.getElementById('modal-body');
    body.querySelectorAll('[data-close-modal]').forEach(button => button.addEventListener('click', closeModal));

    body.querySelectorAll('.distribute-tabs [data-tab]').forEach(button => button.addEventListener('click', () => {
      body.querySelectorAll('.distribute-tabs [data-tab]').forEach(item => item.classList.toggle('active', item === button));
      body.querySelectorAll('[data-tab-panel]').forEach(panel => { panel.hidden = panel.dataset.tabPanel !== button.dataset.tab; });
    }));

    const form = document.getElementById('distribute-form');
    const destinationField = form.elements.destination;
    const serviceField = form.elements.subcontract_service_id;
    const lineField = form.elements.line_id;
    const transportAction = body.querySelector('[data-transport-action]');
    const updateVisibility = () => {
      const isInternal = destinationField.value === 'internal';
      const isSubcontract = destinationField.value === 'subcontract';
      lineField.closest('.field').hidden = !isInternal;
      serviceField.closest('.field').hidden = !isSubcontract;
      transportAction.hidden = !(isSubcontract && serviceField.value);
    };
    destinationField.addEventListener('change', updateVisibility);
    serviceField.addEventListener('change', updateVisibility);
    updateVisibility();

    form.addEventListener('submit', async event => {
      event.preventDefault();
      try {
        const payload = readForm(form, fields);
        await post(`/production/orders/${order.id}/distribute`, payload);
        toast('Distribuição guardada.');
        closeModal();
        await reload();
      } catch (error) { toast(error.message, 'error'); }
    });

    body.querySelector('[data-transport-guide]')?.addEventListener('click', async () => {
      const serviceId = Number(serviceField.value || 0);
      const quantity = Number(form.elements.quantity.value || 0);
      const service = (options.services || []).find(item => Number(item.value) === serviceId);
      if (!serviceId || !service || !quantity) { toast('Escolha o serviço e a quantidade antes de gerar a guia.', 'error'); return; }
      try {
        await startSupplierOrder({
          supplier_id: service.supplier_id,
          style_id: order.style_id,
          code: style?.reference || '',
          description: style?.description || '',
          quantity,
          unit: 'un',
          extra: {production_order_id: order.id},
        }, 'supplier_transport');
        closeModal();
      } catch (error) { toast(error.message, 'error'); }
    });

    let trancheSeq = 1;
    const trancheBody = () => body.querySelector('[data-tranche-rows]');
    const bindTrancheRemovals = scope => scope.querySelectorAll('[data-remove-tranche]').forEach(button => {
      if (button.dataset.bound) return;
      button.dataset.bound = '1';
      button.addEventListener('click', () => {
        if (trancheBody().children.length > 1) button.closest('[data-tranche-row]').remove();
      });
    });
    bindTrancheRemovals(trancheBody());
    body.querySelector('[data-add-tranche]')?.addEventListener('click', () => {
      trancheBody().insertAdjacentHTML('beforeend', trancheRowHtml(trancheSeq++));
      bindTrancheRemovals(trancheBody());
    });

    body.querySelector('[data-save-tranches]')?.addEventListener('click', async () => {
      const base = readForm(form, fields);
      const rows = [...trancheBody().children];
      let stopped = false;
      let anyOk = false;
      for (const rowEl of rows) {
        const statusEl = rowEl.querySelector('[data-tr-status]');
        if (stopped) { statusEl.textContent = 'Não tentada'; statusEl.className = 'tranche-status skip'; continue; }
        const qty = Number(rowEl.querySelector('[data-tr-qty]').value || 0);
        const plannedDate = rowEl.querySelector('[data-tr-date]').value || null;
        if (!qty) { statusEl.textContent = 'Sem quantidade'; statusEl.className = 'tranche-status error'; stopped = true; continue; }
        statusEl.textContent = 'A processar…'; statusEl.className = 'tranche-status pending';
        try {
          await post(`/production/orders/${order.id}/distribute`, {...base, quantity: qty, planned_date: plannedDate});
          statusEl.textContent = 'OK'; statusEl.className = 'tranche-status ok';
          anyOk = true;
        } catch (error) {
          statusEl.textContent = error.message; statusEl.className = 'tranche-status error';
          stopped = true;
        }
      }
      if (anyOk) { toast('Linhas distribuídas.'); await reload(); }
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
