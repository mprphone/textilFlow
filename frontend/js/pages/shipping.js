import { get, post, put } from '../api.js';
import { date, datetime, esc, number } from '../format.js?v=20260826-3';
import { state } from '../state.js';
import { closeModal, openModal, pageHeader, toast } from '../ui.js?v=20260826-3';

const EPSILON = 0.001;
const statusLabels = {
  draft: 'Rascunho', planned: 'Rascunho', preparing: 'Em preparação', closed: 'Fechado',
  ready: 'Documentos prontos', shipped: 'Expedido', invoiced: 'Faturado', cancelled: 'Cancelado',
  partially_shipped: 'Parcial', in_production: 'Em produção', available: 'Disponível',
};
let activeView = 'cockpit';

export async function render(container, view = 'cockpit') {
  activeView = view;
  container.innerHTML = pageHeader('Expedição', 'A carregar encomendas, packing lists e documentos…');
  const orders = await get(`/production/${state.companyId}/shipping-board`);
  const shipments = flattenShipments(orders);
  const metrics = buildMetrics(orders, shipments);
  const titles = {
    cockpit: ['Cockpit de expedição', 'Visão geral do estado das encomendas e expedições.'],
    prepare: ['A preparar', 'Encomendas com quantidade aprovada e embalada disponível.'],
    packing: ['Packing Lists', 'Composição, volumes e reserva de mercadoria antes da saída.'],
    ready: ['Prontas a expedir', 'Packing lists fechados e com documentação controlada.'],
    history: ['Expedidas', 'Histórico de saídas parciais, transportes, guias e faturas.'],
  };
  const [title, subtitle] = titles[view] || titles.cockpit;
  const action = view === 'history'
    ? '<a class="btn" href="#/erp-docs"><span data-icon="document"></span> Documentos comerciais</a>'
    : '<button class="btn primary" type="button" data-new-packing><span data-icon="add"></span> Criar Packing List</button>';
  container.innerHTML = `${pageHeader(title, subtitle, action, 'shipping-page-head')}
    <div class="shipping-workspace" data-shipping-view="${view}">
      ${view === 'cockpit' ? cockpitView(orders, shipments, metrics) : listView(view, orders, shipments, metrics)}
    </div>`;
  bind(container, orders, shipments);
}

function flattenShipments(orders) {
  return orders.flatMap(order => (order.shipments || []).map(item => ({
    ...item, order_id: order.id, order_no: order.order_no, customer_po: order.customer_po,
    customer_name: order.customer_name, delivery_date: order.delivery_date,
  }))).sort((a, b) => Number(b.id) - Number(a.id));
}

function isToday(value) {
  if (!value) return false;
  const parsed = new Date(value), now = new Date();
  return parsed.getFullYear() === now.getFullYear() && parsed.getMonth() === now.getMonth() && parsed.getDate() === now.getDate();
}

function daysTo(value) {
  if (!value) return null;
  const target = new Date(`${String(value).slice(0, 10)}T12:00:00`), now = new Date();
  now.setHours(12, 0, 0, 0);
  return Math.ceil((target - now) / 86400000);
}

function buildMetrics(orders, shipments) {
  const open = orders.filter(row => Number(row.dispatch?.remaining_quantity) > EPSILON);
  return {
    prepare: open.filter(row => Number(row.dispatch?.available_quantity) > EPSILON).length,
    packing: shipments.filter(row => ['draft', 'planned', 'preparing'].includes(row.status)).length,
    ready: shipments.filter(row => ['closed', 'ready'].includes(row.status)).length,
    partial: open.filter(row => Number(row.dispatch?.shipped_quantity) > EPSILON).length,
    today: shipments.filter(row => ['shipped', 'invoiced'].includes(row.status) && isToday(row.shipped_at)),
    overdue: open.filter(row => daysTo(row.delivery_date) !== null && daysTo(row.delivery_date) < 0).length,
  };
}

function metricCards(metrics) {
  const cards = [
    ['box', 'blue', 'A preparar', metrics.prepare, 'com quantidade disponível'],
    ['document', 'amber', 'Packing Lists', metrics.packing, 'em preparação'],
    ['quality', 'violet', 'Prontas a expedir', metrics.ready, 'fechadas ou documentadas'],
    ['truck', 'green', 'Expedidas parcialmente', metrics.partial, 'com saldo por entregar'],
    ['clock', 'blue', 'Expedidas hoje', metrics.today.length, `${number(metrics.today.reduce((sum, row) => sum + Number(row.quantity || 0), 0))} peças`],
    ['warning', 'red', 'Atrasadas', metrics.overdue, 'com saldo em atraso'],
  ];
  return `<section class="shipping-metrics" aria-label="Indicadores de expedição">${cards.map(([icon, tone, label, value, note]) => `
    <article class="shipping-metric ${tone}"><span class="shipping-metric-icon" data-icon="${icon}"></span><div><small>${label}</small><strong>${number(value)}</strong><span>${note}</span></div></article>`).join('')}</section>`;
}

function cockpitView(orders, shipments, metrics) {
  const open = orders.filter(row => Number(row.dispatch?.remaining_quantity) > EPSILON);
  const queue = [...open].sort((a, b) => (daysTo(a.delivery_date) ?? 9999) - (daysTo(b.delivery_date) ?? 9999)).slice(0, 8);
  return `${metricCards(metrics)}
    <div class="shipping-cockpit-grid">
      <section class="shipping-panel shipping-queue-panel">${panelHead('Encomendas / OF com quantidade disponível', `${open.length} encomendas abertas`, true)}${orderTable(queue)}<footer class="shipping-panel-footer"><span>A mostrar ${queue.length} de ${open.length} encomendas</span><a href="#/shipping-prepare">Ver todas</a></footer></section>
      <aside class="shipping-side-stack">${alertsPanel(orders, shipments)}${todayPanel(metrics.today)}${deliveriesPanel(open)}</aside>
    </div>${processPanel(metrics)}`;
}

function listView(view, orders, shipments, metrics) {
  if (view === 'prepare') {
    const rows = orders.filter(row => Number(row.dispatch?.remaining_quantity) > EPSILON);
    return `${metricCards(metrics)}<section class="shipping-panel">${panelHead('Encomendas por preparar', `${rows.length} com saldo por enviar`, true)}${orderTable(rows)}</section>`;
  }
  const wanted = view === 'packing' ? ['draft', 'planned', 'preparing'] : view === 'ready' ? ['closed', 'ready'] : ['shipped', 'invoiced', 'cancelled'];
  const rows = shipments.filter(row => wanted.includes(row.status));
  return `<section class="shipping-list-summary"><article><small>Registos nesta vista</small><strong>${rows.length}</strong></article><article><small>Total de peças</small><strong>${number(rows.reduce((sum, row) => sum + Number(row.quantity || 0), 0))}</strong></article><label class="shipping-search"><span data-icon="search"></span><input type="search" data-shipping-search placeholder="Pesquisar packing list, encomenda ou cliente…"></label></section>
    <section class="shipping-panel">${panelHead(view === 'packing' ? 'Packing lists em preparação' : view === 'ready' ? 'Packing lists prontas' : 'Histórico de expedições', `${rows.length} registos`)}${packingTable(rows, view)}</section>`;
}

function panelHead(title, meta = '', filters = false) {
  return `<header class="shipping-panel-head"><div><h2>${esc(title)}</h2>${meta ? `<span>${esc(meta)}</span>` : ''}</div>${filters ? '<div class="shipping-table-tools"><select data-shipping-state aria-label="Filtrar estado"><option value="all">Todos</option><option value="available">Prontas</option><option value="partial">Parciais</option><option value="in_production">Em produção</option></select><label class="shipping-inline-search"><span data-icon="search"></span><input type="search" data-shipping-search placeholder="Pesquisar…" aria-label="Pesquisar encomendas"></label></div>' : ''}</header>`;
}

function orderState(order) {
  const info = order.dispatch || {};
  if (Number(info.shipped_quantity) > EPSILON) return ['partial', 'Parcial'];
  if (Number(info.available_quantity) > EPSILON) return ['available', 'Pronta'];
  return ['in_production', 'Em produção'];
}

function statusPill(status, label = null) {
  const tone = ['shipped', 'invoiced', 'available'].includes(status) ? 'green' : ['cancelled', 'overdue'].includes(status) ? 'red' : ['closed', 'ready'].includes(status) ? 'violet' : ['partial', 'preparing'].includes(status) ? 'amber' : 'blue';
  return `<span class="shipping-status ${tone}">${esc(label || statusLabels[status] || status)}</span>`;
}

function deliveryCell(value) {
  const days = daysTo(value);
  const label = days === null ? '' : days < 0 ? `${Math.abs(days)} dias em atraso` : days === 0 ? 'hoje' : days === 1 ? 'amanhã' : `${days} dias`;
  return `<b>${date(value)}</b>${label ? `<small class="${days < 0 ? 'danger' : ''}">${esc(label)}</small>` : ''}`;
}

function orderTable(rows) {
  return `<div class="shipping-table-wrap"><table class="shipping-table"><thead><tr><th>Encomenda</th><th>Cliente</th><th>Entrega</th><th>Encomendado</th><th>Disponível</th><th>Reservado</th><th>Expedido</th><th>Saldo</th><th>Estado</th><th><span class="sr-only">Ação</span></th></tr></thead><tbody>${rows.map(order => {
    const info = order.dispatch || {}, [key, label] = orderState(order), canCreate = Number(info.available_quantity) > EPSILON;
    return `<tr data-shipping-row data-state="${key}" data-search="${esc(`${order.order_no} ${order.customer_po || ''} ${order.customer_name || ''}`.toLowerCase())}">
      <td><button class="shipping-link" type="button" data-order-detail="${order.id}">${esc(order.order_no)}</button><small>${esc(order.customer_po || 'Sem PO do cliente')}</small></td><td><b>${esc(order.customer_name || '—')}</b></td><td>${deliveryCell(order.delivery_date)}</td>
      <td><b>${number(info.ordered_quantity)}</b><small>peças</small></td><td class="quantity ${canCreate ? 'positive' : 'zero'}"><b>${number(info.available_quantity)}</b><small>peças</small></td><td><b>${number(info.reserved_quantity)}</b><small>peças</small></td><td><b>${number(info.shipped_quantity)}</b><small>peças</small></td><td><b>${number(info.remaining_quantity)}</b><small>peças</small></td>
      <td>${statusPill(key, label)}</td><td class="shipping-row-action">${canCreate ? `<button class="btn small" type="button" data-new-packing="${order.id}">Criar Packing List</button>` : '<span class="shipping-wait">Aguardar</span>'}</td></tr>`;
  }).join('') || '<tr><td colspan="10"><div class="shipping-empty"><span data-icon="check"></span><b>Sem encomendas pendentes</b><small>Não existe saldo para preparar nesta vista.</small></div></td></tr>'}</tbody></table></div>`;
}

function packingTable(rows, view) {
  return `<div class="shipping-table-wrap"><table class="shipping-table packing-table"><thead><tr><th>Packing List</th><th>Encomenda</th><th>Cliente</th><th>Peças</th><th>Volumes</th><th>Documentos</th><th>${view === 'history' ? 'Saída' : 'Estado'}</th><th>Ações</th></tr></thead><tbody>${rows.map(item => {
    const docs = item.commercial_documents || [], guide = docs.find(doc => doc.doc_type === 'sales_delivery'), invoice = docs.find(doc => doc.doc_type === 'sales_invoice');
    return `<tr data-shipping-row data-state="${item.status}" data-search="${esc(`${item.shipment_no} ${item.order_no} ${item.customer_name}`.toLowerCase())}"><td><button class="shipping-link" type="button" data-view-packing="${item.id}">${esc(item.shipment_no)}</button><small>${item.packing_mode === 'boxes' ? 'Detalhe por caixa' : 'Packing simples'}</small></td><td><b>${esc(item.order_no)}</b><small>${esc(item.customer_po || 'Sem PO')}</small></td><td><b>${esc(item.customer_name || '—')}</b></td><td><b>${number(item.quantity)}</b><small>un.</small></td><td><b>${number(item.package_count)}</b><small>${number(item.gross_weight)} kg bruto</small></td>
      <td><div class="shipping-docs">${guide ? `<span title="Guia de transporte">${esc(guide.doc_no)}</span>` : '<span class="missing">Sem guia</span>'}${invoice ? `<span title="Fatura">${esc(invoice.doc_no)}</span>` : '<span class="muted">Por faturar</span>'}</div></td><td>${view === 'history' ? `<b>${datetime(item.shipped_at)}</b><small>${esc(item.carrier || '—')}</small>` : statusPill(item.status)}</td><td><div class="shipping-actions">${packingActions(item, guide, invoice)}</div></td></tr>`;
  }).join('') || '<tr><td colspan="8"><div class="shipping-empty"><span data-icon="box"></span><b>Sem packing lists</b><small>Os registos desta fase aparecerão aqui.</small></div></td></tr>'}</tbody></table></div>`;
}

function packingActions(item, guide, invoice) {
  const view = `<button class="btn icon" type="button" data-icon="eye" data-view-packing="${item.id}" aria-label="Ver detalhe" title="Ver detalhe"></button>`;
  if (['draft', 'planned', 'preparing'].includes(item.status)) return `${view}<button class="btn icon" type="button" data-icon="edit" data-edit-packing="${item.id}" aria-label="Editar" title="Editar"></button><button class="btn small primary" type="button" data-close-packing="${item.id}"><span data-icon="check"></span> Fechar</button><button class="btn icon danger" type="button" data-icon="delete" data-cancel-packing="${item.id}" aria-label="Cancelar" title="Cancelar"></button>`;
  if (['closed', 'ready'].includes(item.status)) return `${view}${guide ? '<span class="shipping-action-done"><span data-icon="check"></span> Guia pronta</span>' : `<button class="btn small" type="button" data-doc-packing="${item.id}" data-doc-type="sales_delivery"><span data-icon="document"></span> Gerar guia</button>`}<button class="btn small primary" type="button" data-dispatch-packing="${item.id}" ${guide ? '' : 'disabled'}><span data-icon="truck"></span> Confirmar saída</button>`;
  if (['shipped', 'invoiced'].includes(item.status)) return `${view}${invoice ? '<span class="shipping-action-done"><span data-icon="check"></span> Faturado</span>' : `<button class="btn small primary" type="button" data-doc-packing="${item.id}" data-doc-type="sales_invoice"><span data-icon="document"></span> Criar fatura</button>`}`;
  return view;
}

function alertsPanel(orders, shipments) {
  const alerts = [];
  orders.filter(order => Number(order.dispatch?.remaining_quantity) > EPSILON).forEach(order => {
    const days = daysTo(order.delivery_date);
    if (days !== null && days < 0) alerts.push(['danger', 'Entrega vencida e ainda existe saldo', `${order.order_no} · ${order.customer_name} · ${number(order.dispatch.remaining_quantity)} un.`]);
    else if (days !== null && days <= 5 && Number(order.dispatch.available_quantity) + EPSILON < Number(order.dispatch.remaining_quantity)) alerts.push(['warning', 'Entrega próxima e quantidade insuficiente', `${order.order_no} · saldo ${number(order.dispatch.remaining_quantity)} un.`]);
  });
  shipments.filter(row => row.status === 'closed').forEach(row => alerts.push(['warning', 'Packing list fechado sem documentos', `${row.shipment_no} · ${row.customer_name}`]));
  orders.filter(order => Number(order.dispatch?.shipped_quantity) > EPSILON && Number(order.dispatch?.remaining_quantity) > EPSILON).forEach(order => alerts.push(['info', 'Expedição parcial com saldo por entregar', `${order.order_no} · ${number(order.dispatch.remaining_quantity)} un.`]));
  return `<section class="shipping-panel shipping-alerts">${panelHead('Alertas importantes', `${alerts.length} ativos`)}<div>${alerts.slice(0, 6).map(([tone, title, detail]) => `<article><i class="${tone}"></i><div><b>${esc(title)}</b><small>${esc(detail)}</small></div></article>`).join('') || '<div class="shipping-empty compact"><span data-icon="check"></span><b>Sem alertas críticos</b></div>'}</div></section>`;
}

function todayPanel(rows) {
  return `<section class="shipping-panel shipping-today">${panelHead('Expedidas hoje', `${rows.length} saídas`)}<div>${rows.slice(0, 5).map(row => `<article><button class="shipping-link" data-view-packing="${row.id}">${esc(row.shipment_no)}</button><span>${esc(row.customer_name)}</span><b>${number(row.quantity)} un.</b></article>`).join('') || '<p class="shipping-muted">Ainda não existem saídas hoje.</p>'}</div></section>`;
}

function deliveriesPanel(rows) {
  const next = [...rows].sort((a, b) => (a.delivery_date || '').localeCompare(b.delivery_date || '')).slice(0, 5);
  return `<section class="shipping-panel shipping-deliveries">${panelHead('Próximas entregas', `${next.length} visíveis`)}<div>${next.map(row => `<article><b>${date(row.delivery_date)}</b><span>${esc(row.order_no)}</span><small>${esc(row.customer_name)}</small><em>Saldo: ${number(row.dispatch.remaining_quantity)} un.</em></article>`).join('') || '<p class="shipping-muted">Sem entregas pendentes.</p>'}</div></section>`;
}

function processPanel(metrics) {
  const steps = [['box', 'A preparar', 'Quantidade aprovada e embalada', metrics.prepare], ['document', 'Packing List', 'Compor e reservar volumes', metrics.packing], ['quality', 'Documentos', 'Gerar guia para a saída', metrics.ready], ['truck', 'Expedir', 'Confirmar transporte e hora', metrics.today.length], ['document', 'Faturar', 'Fatura exata do packing list', '']];
  return `<section class="shipping-panel shipping-process">${panelHead('Processo de expedição', 'Fluxo recomendado até à faturação')}<div>${steps.map(([icon, title, detail, count], index) => `<article><span class="shipping-step-no">${index + 1}</span><i data-icon="${icon}"></i><div><b>${title}</b><small>${detail}</small></div>${count !== '' ? `<strong>${number(count)}</strong>` : ''}</article>${index < steps.length - 1 ? '<span class="shipping-step-arrow" data-icon="forward"></span>' : ''}`).join('')}</div></section>`;
}

function bind(container, orders, shipments) {
  container.querySelectorAll('[data-new-packing]').forEach(button => button.addEventListener('click', event => openPackingEditor(container, orders, Number(event.currentTarget.dataset.newPacking) || null)));
  container.querySelectorAll('[data-order-detail]').forEach(button => button.addEventListener('click', () => openOrderDetail(orders.find(row => row.id === Number(button.dataset.orderDetail)), container, orders)));
  container.querySelectorAll('[data-view-packing]').forEach(button => button.addEventListener('click', () => openPackingDetail(shipments.find(row => row.id === Number(button.dataset.viewPacking)))));
  container.querySelectorAll('[data-edit-packing]').forEach(button => button.addEventListener('click', () => { const shipment = shipments.find(row => row.id === Number(button.dataset.editPacking)); openPackingEditor(container, orders, shipment.order_id, shipment); }));
  container.querySelectorAll('[data-close-packing]').forEach(button => button.addEventListener('click', () => runAction(container, button, `/production/packing-lists/${button.dataset.closePacking}/close`, {}, 'Packing list fechado e stock reservado.')));
  container.querySelectorAll('[data-cancel-packing]').forEach(button => button.addEventListener('click', async () => { if (window.confirm('Cancelar este packing list e libertar as reservas?')) await runAction(container, button, `/production/packing-lists/${button.dataset.cancelPacking}/cancel`, {}, 'Packing list cancelado.'); }));
  container.querySelectorAll('[data-doc-packing]').forEach(button => button.addEventListener('click', () => createDocument(container, button)));
  container.querySelectorAll('[data-dispatch-packing]').forEach(button => button.addEventListener('click', () => openDispatch(container, shipments.find(row => row.id === Number(button.dataset.dispatchPacking)))));
  const search = container.querySelector('[data-shipping-search]');
  search?.addEventListener('input', () => filterRows(container));
  container.querySelector('[data-shipping-state]')?.addEventListener('change', () => filterRows(container));
}

function filterRows(container) {
  const query = String(container.querySelector('[data-shipping-search]')?.value || '').trim().toLowerCase();
  const status = container.querySelector('[data-shipping-state]')?.value || 'all';
  container.querySelectorAll('[data-shipping-row]').forEach(row => { row.hidden = (Boolean(query) && !row.dataset.search.includes(query)) || (status !== 'all' && row.dataset.state !== status); });
}

async function refresh(container) { await render(container, activeView); }
async function runAction(container, button, path, payload, success) { button.disabled = true; try { await post(path, payload); toast(success); await refresh(container); } catch (error) { toast(error.message, 'error'); button.disabled = false; } }

function openOrderDetail(order, container, orders) {
  const info = order.dispatch || {};
  openModal(`Encomenda ${order.order_no}`, `<div class="shipping-detail-grid"><article><small>Cliente</small><b>${esc(order.customer_name)}</b></article><article><small>PO cliente</small><b>${esc(order.customer_po || '—')}</b></article><article><small>Entrega</small><b>${date(order.delivery_date)}</b></article><article><small>Encomendado</small><b>${number(info.ordered_quantity)} un.</b></article><article><small>Disponível</small><b>${number(info.available_quantity)} un.</b></article><article><small>Saldo</small><b>${number(info.remaining_quantity)} un.</b></article><section><h3>Disponibilidade por artigo / variante</h3>${(info.allocations || []).map(row => `<div><span><b>${esc(row.production_order_no)}</b><small>${esc(row.variant || 'Sem variante')}</small></span><strong>${number(row.available_quantity)} un.</strong></div>`).join('') || '<p>Sem quantidade disponível.</p>'}</section><footer><button class="btn" type="button" data-close-detail>Fechar</button>${Number(info.available_quantity) > EPSILON ? `<button class="btn primary" type="button" data-detail-new="${order.id}">Criar Packing List</button>` : ''}</footer></div>`, 'Estado logístico e saldo da encomenda');
  document.querySelector('[data-close-detail]')?.addEventListener('click', closeModal);
  document.querySelector('[data-detail-new]')?.addEventListener('click', () => { closeModal(); openPackingEditor(container, orders, order.id); });
}

function openPackingEditor(container, orders, orderId = null, shipment = null) {
  const candidates = orders.filter(row => Number(row.dispatch?.available_quantity) > EPSILON || row.id === shipment?.order_id);
  const order = orders.find(row => row.id === (orderId || shipment?.order_id)) || candidates[0];
  if (!order) { toast('Não existem encomendas com quantidade disponível.', 'error'); return; }
  const current = new Map((shipment?.lines || []).map(row => [`${row.production_order_id}:${row.variant_id || 0}`, Number(row.quantity || 0)]));
  const allocations = order.dispatch?.allocations || [], boxes = Array.isArray(shipment?.packing_data?.boxes) ? shipment.packing_data.boxes : [];
  openModal(shipment ? `Editar ${shipment.shipment_no}` : 'Criar Packing List', `<form class="shipping-pl-form"><div class="shipping-form-intro"><span data-icon="box"></span><div><b>${shipment ? 'Ajuste quantidades e volumes' : 'Prepare uma saída parcial ou total'}</b><p>Guardar não mexe no stock. A reserva só acontece quando fechar o packing list.</p></div></div><div class="shipping-form-grid"><label class="span-2">Encomenda<select data-pl-order ${shipment ? 'disabled' : ''}>${candidates.map(row => `<option value="${row.id}" ${row.id === order.id ? 'selected' : ''}>${esc(row.order_no)} · ${esc(row.customer_name)} · ${number(row.dispatch.available_quantity)} un.</option>`).join('')}</select></label><label>Modo de preparação<select name="packing_mode" data-packing-mode><option value="simple" ${shipment?.packing_mode !== 'boxes' ? 'selected' : ''}>Packing simples</option><option value="boxes" ${shipment?.packing_mode === 'boxes' ? 'selected' : ''}>Detalhe por caixa</option></select></label><label class="span-3">Morada / destino<input name="destination" value="${esc(shipment?.destination || order.shipping_address || '')}" placeholder="Morada de entrega"></label></div>
    <section class="shipping-allocation-editor"><header><div><h3>Artigos e variantes</h3><p>Indique apenas o que entra neste packing list.</p></div><strong>${number(order.dispatch.available_quantity)} un. disponíveis</strong></header><div>${allocations.map((row, index) => { const key = `${row.production_order_id}:${row.variant_id || 0}`, preset = shipment ? current.get(key) || 0 : row.available_quantity; return `<label><span><b>${esc(row.variant || 'Sem variante')}</b><small>${esc(row.production_order_no)}</small></span><span class="shipping-qty-input"><input type="number" min="0" max="${row.available_quantity}" step="1" value="${preset}" data-allocation="${index}"><em>un.</em></span></label>`; }).join('')}</div></section>
    <div class="shipping-form-grid compact"><label>Volumes<input name="package_count" type="number" min="0" step="1" value="${shipment?.package_count || boxes.length || 1}" data-package-count></label><label>Paletes<input name="pallet_count" type="number" min="0" step="1" value="${shipment?.packing_data?.pallet_count || 0}"></label><label>Peso líquido (kg)<input name="net_weight" type="number" min="0" step="0.01" value="${shipment?.net_weight || ''}"></label><label>Peso bruto (kg)<input name="gross_weight" type="number" min="0" step="0.01" value="${shipment?.gross_weight || ''}"></label><label class="span-all">Observações<textarea name="notes" rows="2" placeholder="Instruções de embalagem, palete ou entrega…">${esc(shipment?.notes || '')}</textarea></label></div><section class="shipping-box-editor" data-box-editor ${shipment?.packing_mode === 'boxes' ? '' : 'hidden'}><header><h3>Composição das caixas</h3><p>Código, peças, peso e dimensões por volume.</p></header><div data-box-rows></div></section><footer class="shipping-form-footer"><button class="btn" type="button" data-cancel-form>Cancelar</button><button class="btn primary" type="submit"><span data-icon="save"></span>${shipment ? 'Guardar alterações' : 'Criar packing list'}</button></footer></form>`, shipment ? 'Packing list editável, ainda sem reserva' : `${order.order_no} · ${order.customer_name}`);
  const form = document.querySelector('.shipping-pl-form');
  const renderBoxes = () => { const count = Math.max(0, Number(form.querySelector('[data-package-count]').value || 0)); form.querySelector('[data-box-rows]').innerHTML = Array.from({ length: count }, (_, index) => { const box = boxes[index] || {}; return `<div class="shipping-box-row"><b>Caixa ${String(index + 1).padStart(2, '0')}</b><input data-box-code value="${esc(box.code || `${shipment?.shipment_no || 'PL'}-CX${String(index + 1).padStart(2, '0')}`)}" aria-label="Código da caixa ${index + 1}"><input data-box-qty type="number" min="0" step="1" value="${box.quantity || ''}" placeholder="Peças" aria-label="Peças da caixa ${index + 1}"><input data-box-weight type="number" min="0" step="0.01" value="${box.weight || ''}" placeholder="kg" aria-label="Peso da caixa ${index + 1}"><input data-box-dim value="${esc(box.dimensions || '')}" placeholder="CxLxA cm" aria-label="Dimensões da caixa ${index + 1}"></div>`; }).join(''); };
  renderBoxes();
  form.querySelector('[data-pl-order]')?.addEventListener('change', event => openPackingEditor(container, orders, Number(event.target.value)));
  form.querySelector('[data-packing-mode]').addEventListener('change', event => { form.querySelector('[data-box-editor]').hidden = event.target.value !== 'boxes'; });
  form.querySelector('[data-package-count]').addEventListener('change', renderBoxes);
  form.querySelector('[data-cancel-form]').addEventListener('click', closeModal);
  form.addEventListener('submit', async event => {
    event.preventDefault(); const data = new FormData(form);
    const selected = allocations.map((row, index) => ({ production_order_id: row.production_order_id, variant_id: row.variant_id, quantity: Number(form.querySelector(`[data-allocation="${index}"]`).value || 0) })).filter(row => row.quantity > EPSILON);
    if (!selected.length) { toast('Indique pelo menos uma quantidade.', 'error'); return; }
    const boxRows = [...form.querySelectorAll('.shipping-box-row')].map(row => ({ code: row.querySelector('[data-box-code]').value.trim(), quantity: Number(row.querySelector('[data-box-qty]').value || 0), weight: Number(row.querySelector('[data-box-weight]').value || 0), dimensions: row.querySelector('[data-box-dim]').value.trim() }));
    if (data.get('packing_mode') === 'boxes') {
      const selectedTotal = selected.reduce((sum, row) => sum + row.quantity, 0), boxTotal = boxRows.reduce((sum, row) => sum + row.quantity, 0);
      if (boxRows.some(row => !row.code || row.quantity <= 0) || Math.abs(selectedTotal - boxTotal) > EPSILON) { toast(`Complete as caixas: devem somar ${number(selectedTotal)} peças.`, 'error'); return; }
    }
    const payload = { allocations: selected, packing_mode: data.get('packing_mode'), destination: data.get('destination'), package_count: Number(data.get('package_count') || 0), net_weight: Number(data.get('net_weight') || 0), gross_weight: Number(data.get('gross_weight') || 0), notes: data.get('notes'), packing_data: { pallet_count: Number(data.get('pallet_count') || 0), boxes: data.get('packing_mode') === 'boxes' ? boxRows : [] } };
    const submit = form.querySelector('[type="submit"]'); submit.disabled = true;
    try { if (shipment) await put(`/production/packing-lists/${shipment.id}`, payload); else await post(`/production/sales-orders/${order.id}/packing-lists`, payload); closeModal(); toast(shipment ? 'Packing list atualizado.' : 'Packing list criado em preparação.'); await refresh(container); } catch (error) { toast(error.message, 'error'); submit.disabled = false; }
  });
}

function openPackingDetail(item) {
  if (!item) return;
  const docs = item.commercial_documents || [];
  openModal(item.shipment_no, `<div class="shipping-packing-detail"><div class="shipping-detail-grid"><article><small>Encomenda</small><b>${esc(item.order_no)}</b></article><article><small>Cliente</small><b>${esc(item.customer_name)}</b></article><article><small>Estado</small>${statusPill(item.status)}</article><article><small>Peças</small><b>${number(item.quantity)} un.</b></article><article><small>Volumes</small><b>${number(item.package_count)}</b></article><article><small>Peso bruto</small><b>${number(item.gross_weight)} kg</b></article></div><section><h3>Artigos / variantes</h3>${(item.lines || []).map(line => `<div><span><b>${esc(line.description || line.production_order_no)}</b><small>${esc(line.production_order_no)} · ${esc(line.variant || 'Sem variante')}</small></span><strong>${number(line.quantity)} un.</strong></div>`).join('')}</section><section><h3>Documentos</h3>${docs.map(doc => `<div><span><b>${esc(doc.type_label)}</b><small>${esc(doc.primavera_status)}</small></span><strong>${esc(doc.doc_no)}</strong></div>`).join('') || '<p>Sem documentos comerciais.</p>'}</section><footer><button class="btn" type="button" data-close-detail>Fechar</button></footer></div>`, `${item.packing_mode === 'boxes' ? 'Detalhe por caixa' : 'Packing simples'} · ${item.package_count || 0} volumes`);
  document.querySelector('[data-close-detail]')?.addEventListener('click', closeModal);
}

async function createDocument(container, button) {
  button.disabled = true; const type = button.dataset.docType;
  try { const doc = await post(`/erp/${state.companyId}/documents/from-shipment/${button.dataset.docPacking}`, { doc_type: type, prepare: true }); toast(`${type === 'sales_invoice' ? 'Fatura' : 'Guia'} ${doc.doc_no} preparada com as quantidades deste packing list.`); await refresh(container); } catch (error) { toast(error.message, 'error'); button.disabled = false; }
}

function openDispatch(container, item) {
  if (!item) return;
  const local = new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 16);
  openModal(`Confirmar saída · ${item.shipment_no}`, `<form class="shipping-dispatch-form"><div class="shipping-dispatch-summary"><span data-icon="truck"></span><div><small>Mercadoria a expedir</small><b>${number(item.quantity)} peças · ${number(item.package_count)} volumes</b></div>${statusPill(item.status)}</div><div class="shipping-form-grid"><label>Data e hora<input name="shipped_at" type="datetime-local" value="${local}" required></label><label>Transportador<input name="carrier" value="${esc(item.carrier || '')}" required placeholder="Nome do transportador"></label><label>Matrícula<input name="vehicle_plate" value="${esc(item.vehicle_plate || '')}" placeholder="00-AA-00"></label><label>Tracking / referência<input name="tracking_no" value="${esc(item.tracking_no || '')}"></label><label>Volumes<input name="package_count" type="number" min="1" step="1" value="${item.package_count || 1}"></label><label>Custo transporte (€)<input name="transport_cost" type="number" min="0" step="0.01" value="0"></label><label class="span-3">Observações<textarea name="notes" rows="2">${esc(item.notes || '')}</textarea></label></div><div class="shipping-confirm-note"><span data-icon="warning"></span><p>Ao confirmar, a reserva é abatida ao produto acabado e esta saída fica disponível para faturar.</p></div><footer class="shipping-form-footer"><button class="btn" type="button" data-cancel-form>Cancelar</button><button class="btn primary" type="submit"><span data-icon="truck"></span>Confirmar saída</button></footer></form>`, `${item.order_no} · ${item.customer_name}`);
  const form = document.querySelector('.shipping-dispatch-form'); form.querySelector('[data-cancel-form]').addEventListener('click', closeModal);
  form.addEventListener('submit', async event => { event.preventDefault(); const data = Object.fromEntries(new FormData(form)), submit = form.querySelector('[type="submit"]'); submit.disabled = true; try { await post(`/production/packing-lists/${item.id}/dispatch`, data); closeModal(); toast('Saída confirmada. O packing list está pronto para faturar.'); await refresh(container); } catch (error) { toast(error.message, 'error'); submit.disabled = false; } });
}
