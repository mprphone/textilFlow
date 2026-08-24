import { get, post } from '../api.js';
import { badge, date, datetime, esc, number } from '../format.js?v=20260824-2';
import { recordModal } from '../quick_create.js';
import { state } from '../state.js';
import { pageHeader, toast } from '../ui.js?v=20260820-5';

export async function render(container) {
  const orders = await get(`/production/${state.companyId}/shipping-board`);
  const open = orders.filter(row => row.dispatch.remaining_quantity > 0.001);
  const ready = open.filter(row => row.dispatch.available_quantity > 0.001 && row.dispatch.shipped_quantity <= 0.001);
  const partial = open.filter(row => row.dispatch.shipped_quantity > 0.001);
  const preparing = open.filter(row => row.dispatch.available_quantity <= 0.001 && row.dispatch.shipped_quantity <= 0.001);
  const shipped = orders.filter(row => row.dispatch.remaining_quantity <= 0.001 && row.dispatch.ordered_quantity > 0);

  container.innerHTML = pageHeader(
    'Expedição',
    'Envios parciais, saldo por expedir e rastreabilidade até à ordem de fabrico.',
    '<a class="btn" href="#/erp-docs">Documentos Primavera</a><a class="btn" href="#/embalagem">Embalagem</a><a class="btn primary" href="#/orders">Ver encomendas</a>',
  ) + `
    <div class="shipping-kpis">
      <article><span>A preparar</span><strong>${preparing.length}</strong><small>sem quantidade disponível</small></article>
      <article><span>Prontas</span><strong>${ready.length}</strong><small>podem iniciar expedição</small></article>
      <article><span>Parciais</span><strong>${partial.length}</strong><small>ainda têm saldo por enviar</small></article>
      <article><span>Expedidas</span><strong>${shipped.length}</strong><small>encomendas concluídas</small></article>
    </div>
    <div class="shipping-board">
      <section class="card">
        <div class="card-header"><h2>Fila de expedição</h2><span>${open.length} encomendas abertas · próxima entrega ${date(nextDelivery(open))}</span></div>
        <div class="shipping-list">${[...partial, ...ready, ...preparing].map(shippingRow).join('') || '<div class="empty"><strong>Sem expedições pendentes</strong>As encomendas com saldo por expedir aparecerão aqui.</div>'}</div>
      </section>
      <aside class="card shipping-check">
        <div class="card-header"><h2>Regra de disponibilidade</h2><span>Automática</span></div>
        <label><i>1</i> Quantidade produzida</label><label><i>2</i> Aprovada na revista/qualidade final</label><label><i>3</i> Embalada e ainda não expedida</label><label><i>4</i> Dentro do saldo da encomenda</label>
        <div class="shipping-tip"><b>Expedições múltiplas</b><p>Cada saída cria um registo e uma guia apenas com as quantidades desse envio. A encomenda só fica concluída quando o saldo chega a zero.</p></div>
      </aside>
    </div>
    ${shipmentHistory(orders)}`;

  container.querySelectorAll('[data-dispatch-order]').forEach(button => button.addEventListener('click', () => {
    const order = orders.find(item => item.id === Number(button.dataset.dispatchOrder));
    openDispatch(order, container);
  }));
}

function shippingRow(order) {
  const info = order.dispatch;
  const canDispatch = info.available_quantity > 0.001;
  const stateLabel = info.shipped_quantity > 0.001 ? 'partially_shipped' : (canDispatch ? 'ready' : 'in_production');
  const pct = info.ordered_quantity ? Math.min(100, info.shipped_quantity / info.ordered_quantity * 100) : 0;
  return `<article>
    <div class="shipping-order"><i>${canDispatch ? '✓' : '▷'}</i><div><b>${esc(order.order_no)}</b><small>${esc(order.customer_po || 'Sem PO de cliente')} · ${number(info.ordered_quantity)} un.</small><div class="shipping-balance"><span style="width:${pct}%"></span></div></div></div>
    <div><span>Expedido / saldo</span><b>${number(info.shipped_quantity)} / ${number(info.remaining_quantity)}</b></div>
    <div>${badge(stateLabel)}<small>${canDispatch ? `${number(info.available_quantity)} disponíveis` : esc(info.reason)}</small></div>
    <button class="btn small ${canDispatch ? 'primary' : ''}" data-dispatch-order="${order.id}" ${canDispatch ? '' : 'disabled'}>${info.shipment_count ? 'Nova saída' : 'Confirmar saída'}</button>
  </article>`;
}

function openDispatch(order, container) {
  const info = order.dispatch;
  const local = new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 16);
  const sequence = String(info.shipment_count + 1).padStart(2, '0');
  const allocationFields = info.allocations.map((row, index) => ({
    key: `allocation_${index}`,
    label: `${row.variant || row.production_order_no} (máx. ${number(row.available_quantity)})`,
    type: 'number',
    section: 'Quantidades por variante',
  }));
  const allocationValues = Object.fromEntries(info.allocations.map((row, index) => [`allocation_${index}`, row.available_quantity]));
  recordModal({
    title: `Nova saída · ${order.order_no}`,
    values: {
      shipment_no: `EXP-${order.order_no}-${sequence}`,
      ...allocationValues,
      shipped_at: local,
      quantities_checked: false,
      quality_checked: false,
      documents_checked: false,
      carrier_checked: false,
    },
    fields: [
      { key: 'shipment_no', label: 'Documento de expedição', required: true, section: 'Transporte' },
      { key: 'carrier', label: 'Transportador', required: true, section: 'Transporte' },
      { key: 'tracking_no', label: 'Referência / tracking', section: 'Transporte' },
      { key: 'transport_cost', label: 'Custo real do transporte (€)', type: 'number', default: 0, section: 'Transporte' },
      { key: 'destination', label: 'Destino', type: 'textarea', section: 'Transporte' },
      { key: 'shipped_at', label: 'Data e hora', type: 'datetime-local', required: true, section: 'Saída' },
      ...allocationFields,
      { key: 'quantities_checked', label: 'Quantidades e variantes conferidas', type: 'checkbox', section: 'Checklist' },
      { key: 'quality_checked', label: 'Qualidade concluída', type: 'checkbox', section: 'Checklist' },
      { key: 'documents_checked', label: 'Documentação preparada', type: 'checkbox', section: 'Checklist' },
      { key: 'carrier_checked', label: 'Transportador e volumes confirmados', type: 'checkbox', section: 'Checklist' },
    ],
    save: payload => {
      payload.allocations = info.allocations.map((row, index) => ({
        production_order_id: row.production_order_id,
        variant_id: row.variant_id,
        quantity: Number(payload[`allocation_${index}`]) || 0,
      })).filter(row => row.quantity > 0);
      payload.quantity = payload.allocations.reduce((sum, row) => sum + row.quantity, 0);
      allocationFields.forEach(field => { delete payload[field.key]; });
      return post(`/production/sales-orders/${order.id}/dispatch`, payload);
    },
    onSaved: async result => {
      const remaining = result.dispatch_status?.remaining_quantity || 0;
      toast(remaining > 0 ? `Saída registada. Ficam ${number(remaining)} unidades por expedir.` : 'Encomenda integralmente expedida.');
      await render(container);
    },
  });
}

function shipmentHistory(orders) {
  const rows = orders.flatMap(order => (order.shipments || []).map(shipment => ({ ...shipment, order_no: order.order_no })));
  return `<section class="card shipping-history"><div class="card-header"><h2>Histórico de saídas</h2><span>${rows.length} documentos</span></div><div class="table-wrap"><table class="data-table"><thead><tr><th>Documento</th><th>Encomenda</th><th>Data</th><th>Quantidade</th><th>Transportador</th><th>Tracking</th></tr></thead><tbody>${rows.map(row => `<tr><td><b>${esc(row.shipment_no)}</b></td><td>${esc(row.order_no)}</td><td>${datetime(row.shipped_at)}</td><td>${number(row.quantity)}</td><td>${esc(row.carrier || '—')}</td><td>${esc(row.tracking_no || '—')}</td></tr>`).join('') || '<tr><td colspan="6">Ainda não existem saídas registadas.</td></tr>'}</tbody></table></div></section>`;
}

function nextDelivery(rows) { return rows.map(row => row.delivery_date).filter(Boolean).sort()[0] || null; }
