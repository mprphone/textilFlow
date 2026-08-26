import { crudList, get, post } from '../api.js';
import { badge, date, datetime, esc, number } from '../format.js?v=20260826-3';
import { recordModal } from '../quick_create.js';
import { state } from '../state.js';
import { openModal, toast } from '../ui.js?v=20260826-3';

const SOURCE_LABEL = { unassigned: 'Por distribuir', internal: 'Confeção interna', revista: 'Revista' };
const DESTINATION_LABEL = { internal: 'Confeção interna', subcontract: 'Serviço externo', revista: 'Revista' };

const MAT_STATE = {
  delivered_to_floor: 'Entregue à linha',
  partial_issue: 'Saída parcial para a OF',
  reserved: 'Reservada em stock',
  po_received: 'Recebida na compra',
  on_order: 'Encomendada ao fornecedor',
  shortage: 'Em falta',
  available: 'Disponível em stock',
  unlinked_material: 'Sem material ligado',
  unit_mismatch: 'Unidade incompatível',
  pending: 'Pendente',
  ready: 'Coberto por stock',
};

const JOB_STATUS = {
  planned: 'A enviar', sent: 'No fornecedor', partial: 'Receção parcial',
  received: 'Recebido', problem: 'Incidência', cancelled: 'Anulado',
};

const STEP_STATUS = {
  ready: 'Liberto — distribuir agora',
  in_progress: 'Em curso',
  done: 'Concluído',
  locked: 'Cadeado',
};

function rowsOrEmpty(rows, cols, message) {
  return rows || `<tr><td colspan="${cols}" class="muted">${esc(message)}</td></tr>`;
}

function prazoLabel(order) {
  const days = order.days_to_delivery;
  if (days == null) return date(order.delivery_date || order.planned_end);
  if (days < 0) return `${date(order.delivery_date)} · atraso ${number(Math.abs(days))} dias`;
  if (days === 0) return `${date(order.delivery_date)} · hoje`;
  return `${date(order.delivery_date)} · faltam ${number(days)} dias`;
}

function materialTable(rows, empty) {
  const body = (rows || []).map(row => `<tr>
    <td><b>${esc(row.material_code || '—')}</b><div class="table-subline">${esc(row.material_name || row.description || '')}</div></td>
    <td>${number(row.required_quantity)} ${esc(row.unit || '')}</td>
    <td>${number(row.available_quantity)}</td>
    <td>${number(row.reserved_quantity)}</td>
    <td>${number(row.ordered_quantity)}</td>
    <td>${number(row.po_received_quantity)}</td>
    <td>${number(row.to_order_quantity)}</td>
    <td>${badge(MAT_STATE[row.state] || row.state)}</td>
  </tr>`).join('');
  return `<div class="table-wrap"><table class="data-table"><thead><tr>
    <th>Artigo</th><th>Necessário</th><th>Em stock</th><th>Reservado</th><th>Encomendado</th><th>Recebido</th><th>A encomendar</th><th>Estado</th>
  </tr></thead><tbody>${rowsOrEmpty(body, 8, empty)}</tbody></table></div>`;
}

export function dossierHtml(data) {
  const order = data.order || {};
  const holdings = data.holdings || {};
  const locations = data.locations || [];
  const goods = data.goods || [];
  const accessories = data.accessories || [];
  const jobs = data.jobs || [];
  const events = data.events || [];
  const shipments = data.shipments || [];
  const productionMovements = data.production_movements || [];
  const services = data.services || [];
  const alerts = data.alerts || [];
  const fabricPurchases = data.fabric_purchases || [];
  const cutting = data.cutting || [];
  const distributed = (holdings.internal || 0) + (holdings.external || 0) + (holdings.revista || 0) + (holdings.finished_goods || 0) + (holdings.shipped || 0);
  const article = [order.reference, order.description].filter(Boolean).join(' · ') || '—';
  const locationCards = locations.length
    ? locations.map(loc => `<span class="track-split ${esc(loc.kind)}"><b>${esc(loc.label)}</b><small>${number(loc.quantity)} un. · ${esc(loc.detail || '')}</small></span>`).join('')
    : '<p class="muted">Ainda sem destinos nesta OF.</p>';
  const jobRows = jobs.map(job => `<tr>
    <td><b>${esc(job.reference)}</b></td>
    <td>${esc(job.supplier_name || '—')}</td>
    <td>${esc(job.service_name || '—')}</td>
    <td>${number(job.out_quantity || job.quantity)}</td>
    <td>${badge(JOB_STATUS[job.status] || job.status)}</td>
    <td>${date(job.expected_date)}</td>
  </tr>`).join('');
  const eventRows = events.map(row => `<tr>
    <td>${datetime(row.event_time)}</td>
    <td>${esc(row.event_type || row.notes || `Operação ${row.operation_id || '—'}`)}</td>
    <td>${number(row.quantity_good)} boas</td>
    <td>${number(row.quantity_rejected)} rejeitadas</td>
    <td>${row.event_type === 'correction' ? '<small class="muted">Estorno</small>' : `<button class="btn small" data-compensate-event="${row.id}">Estornar</button>`}</td>
  </tr>`).join('');
  const shipRows = shipments.map(row => `<tr>
    <td><b>${esc(row.shipment_no)}</b></td>
    <td>${number(row.quantity)}</td>
    <td>${badge(row.status)}</td>
    <td>${datetime(row.shipped_at)}</td>
  </tr>`).join('');
  const movementRows = productionMovements.map(row => `<tr>
    <td>${datetime(row.occurred_at)}</td><td>${badge(row.movement_type)}</td><td>${number(row.quantity)}</td>
    <td>${esc(row.location_from || '—')} → ${esc(row.location_to || '—')}</td><td>${esc(row.reference || '—')}</td>
  </tr>`).join('');
  const serviceRail = services.length
    ? `<ol class="service-rail">${services.map(step => {
        const detail = [
          step.reason || STEP_STATUS[step.status] || step.status,
          step.out_quantity ? `${number(step.out_quantity)} un. fora` : '',
          step.required === false ? 'Opcional' : '',
          step.notes || '',
        ].filter(Boolean).join(' · ');
        return `<li class="${esc(step.status)}">
        <span class="service-lock">${step.locked ? '🔒' : step.status === 'done' ? '✓' : step.sequence}</span>
        <div><b>${esc(step.label)}</b><small>${esc(detail)}</small></div>
      </li>`;
      }).join('')}</ol>`
    : '<p class="muted">Sem sequência de produção definida — aplica-se a regra geral.</p>';
  const unseenAlerts = alerts.filter(row => !row.seen);
  const alertBox = alerts.length
    ? `<div class="dossier-alerts">${alerts.map(row => `<div class="dossier-alert ${esc(row.level)} ${row.seen ? 'seen' : ''}"><b>${esc(row.title)}</b><span>${esc(row.detail || '')}</span>${row.seen ? '<small>Visto</small>' : ''}</div>`).join('')}<button class="btn small" data-mark-alerts-seen data-order-id="${order.id}">${unseenAlerts.length ? `Marcar ${unseenAlerts.length} alerta${unseenAlerts.length > 1 ? 's' : ''} como visto` : 'Marcar todos como vistos'}</button></div>`
    : '';

  return `<div class="order-dossier">
    <p class="dossier-meta">${esc(article)}${order.customer_name ? ` · ${esc(order.customer_name)}` : ''}${order.sales_order_no ? ` · Enc. ${esc(order.sales_order_no)}` : ''}</p>
    <div class="dossier-distribute-toggle">
      <button type="button" class="btn primary" data-toggle-distribute>⇄ Distribuir</button>
    </div>
    <div data-distribute-panel hidden></div>
    <div class="dossier-kpis">
      <div><span>Prazo de entrega</span><strong>${prazoLabel(order)}</strong></div>
      <div><span>Comercial responsável</span><strong>${esc(order.commercial_name || '—')}</strong></div>
      <div><span>Encomendado</span><strong>${number(order.quantity)}</strong></div>
      <div><span>Produzido</span><strong>${number(order.completed_quantity)}</strong></div>
      <div><span>Por distribuir</span><strong>${number(holdings.unassigned)}</strong></div>
    </div>
    <div class="dossier-kpis dossier-kpis-secondary">
      <div><span>Distribuído</span><strong>${number(distributed)}</strong></div>
      <div><span>Na confeção</span><strong>${number(holdings.internal)}</strong></div>
      <div><span>Em subcontrato</span><strong>${number(holdings.external)}</strong></div>
      <div><span>Produto acabado</span><strong>${number(holdings.finished_goods)}</strong></div>
      <div><span>Entregue / expedido</span><strong>${number(holdings.shipped)}</strong></div>
    </div>
    ${alertBox}
    <section class="dossier-block">
      <h3>Onde está agora</h3>
      <div class="track-splits dossier-places">${locationCards}</div>
    </section>
    <section class="dossier-block">
      <h3>Sequência de produção <small>um passo de cada vez · os seguintes ficam cadeados</small></h3>
      ${serviceRail}
    </section>
    <section class="dossier-block">
      <h3>Mercadorias</h3>
      ${fabricPurchases.length ? `<p class="muted">Encomenda de malha: ${fabricPurchases.map(row => `${row.order_no} (${row.status})`).join(' · ')}</p>` : ''}
      ${materialTable(goods, 'Sem malhas/tecidos nesta OF.')}
      ${cutting.length ? `<p class="muted">Malha enviada ao corte: ${cutting.map(row => `${number(row.actual_fabric || 0)} (plano ${number(row.planned_fabric || 0)})`).join(' · ')}</p>` : ''}
      ${(order.custom_data?.fabric_issue_docs || []).length ? `<p class="muted">Documentos de saída: ${(order.custom_data.fabric_issue_docs || []).map(row => row.doc_no).join(' · ')}</p>` : ''}
    </section>
    <section class="dossier-block">
      <h3>Acessórios</h3>
      ${materialTable(accessories, 'Sem acessórios, linhas ou embalagem nesta OF.')}
    </section>
    <section class="dossier-block">
      <h3>Envios externos</h3>
      <div class="table-wrap"><table class="data-table"><thead><tr><th>Guia</th><th>Fornecedor</th><th>Serviço</th><th>Qtd. fora</th><th>Estado</th><th>Regresso</th></tr></thead>
      <tbody>${rowsOrEmpty(jobRows, 6, 'Nada fora de casa neste momento.')}</tbody></table></div>
    </section>
    <div class="dossier-grid">
      <section class="dossier-block">
        <h3>Expedições</h3>
        <div class="table-wrap"><table class="data-table"><thead><tr><th>Documento</th><th>Qtd.</th><th>Estado</th><th>Data</th></tr></thead>
        <tbody>${rowsOrEmpty(shipRows, 4, 'Ainda sem expedição.')}</tbody></table></div>
      </section>
      <section class="dossier-block">
        <h3>Últimos eventos</h3>
        <div class="table-wrap"><table class="data-table"><thead><tr><th>Quando</th><th>O quê</th><th>Boas</th><th>Rejeitadas</th><th></th></tr></thead>
        <tbody>${rowsOrEmpty(eventRows, 5, 'Ainda sem registos de chão de fábrica.')}</tbody></table></div>
      </section>
    </div>
    <section class="dossier-block">
      <h3>Livro de movimentos <small>histórico imutável de WIP, qualidade, embalagem e expedição</small></h3>
      <div class="table-wrap"><table class="data-table"><thead><tr><th>Quando</th><th>Movimento</th><th>Qtd.</th><th>Origem → destino</th><th>Referência</th></tr></thead>
      <tbody>${rowsOrEmpty(movementRows, 5, 'Ainda sem movimentos produtivos registados.')}</tbody></table></div>
    </section>
  </div>`;
}

function distributeFormHtml(holdings, lines, services, batches = []) {
  const sources = ['unassigned', 'internal', 'revista'].filter(key => (holdings[key] || 0) > 0.001);
  if (!sources.length) sources.push('unassigned');
  return `<form class="dossier-distribute-form" data-distribute-form>
    <div class="form-grid">
      <label>Origem<select name="source">${sources.map(key => `<option value="${key}">${esc(SOURCE_LABEL[key])} · ${number(holdings[key])} disponíveis</option>`).join('')}</select></label>
      <label>Destino<select name="destination">${Object.entries(DESTINATION_LABEL).map(([key, label]) => `<option value="${key}">${esc(label)}</option>`).join('')}</select></label>
      <label>Quantidade<input type="number" name="quantity" min="1" step="1" required></label>
      ${batches.length ? `<label>Lote produtivo<select name="batch_id" required><option value="">Selecionar…</option>${batches.map(row => `<option value="${row.id}">${esc(row.batch_no)}</option>`).join('')}</select></label>` : ''}
      <label data-distribute-line>Linha de confeção<select name="line_id"><option value="">Selecionar…</option>${lines.map(row => `<option value="${row.id}">${esc(row.name)}</option>`).join('')}</select></label>
      <label data-distribute-service hidden>Serviço / fornecedor<select name="subcontract_service_id"><option value="">Selecionar…</option>${services.map(row => `<option value="${row.id}">${esc(row.code)} · ${esc(row.name)}</option>`).join('')}</select></label>
      <label>Data planeada<input type="date" name="planned_date"></label>
    </div>
    <div class="form-footer">
      <button type="button" class="btn" data-cancel-distribute>Cancelar</button>
      <button type="submit" class="btn primary">Confirmar distribuição</button>
    </div>
  </form>`;
}

function bindDistributeForm(container, orderId, lines, services) {
  const panel = container.querySelector('[data-distribute-panel]');
  container.querySelector('[data-toggle-distribute]')?.addEventListener('click', () => {
    panel.hidden = !panel.hidden;
  });
  const form = panel.querySelector('[data-distribute-form]');
  if (!form) return;
  const destinationField = form.querySelector('select[name="destination"]');
  const lineField = form.querySelector('[data-distribute-line]');
  const serviceField = form.querySelector('[data-distribute-service]');
  const syncFields = () => {
    lineField.hidden = destinationField.value !== 'internal';
    serviceField.hidden = destinationField.value !== 'subcontract';
  };
  syncFields();
  destinationField.addEventListener('change', syncFields);
  panel.querySelector('[data-cancel-distribute]').addEventListener('click', () => { panel.hidden = true; });
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const submit = form.querySelector('[type="submit"]');
    submit.disabled = true;
    try {
      const payload = {
        source: form.source.value,
        destination: destinationField.value,
        quantity: Number(form.quantity.value),
        planned_date: form.planned_date.value || null,
      };
      if (form.batch_id?.value) payload.batch_id = Number(form.batch_id.value);
      if (destinationField.value === 'internal') payload.line_id = form.line_id.value ? Number(form.line_id.value) : null;
      if (destinationField.value === 'subcontract') payload.subcontract_service_id = form.subcontract_service_id.value ? Number(form.subcontract_service_id.value) : null;
      const result = await post(`/production/orders/${orderId}/distribute-and-document`, payload);
      toast(result.document ? `Distribuído. Documento ${result.document.doc_no} criado.` : 'Distribuído.');
      await loadOrderDossier(orderId);
    } catch (error) {
      submit.disabled = false;
      toast(error.message, 'error');
    }
  });
}

export function openOrderDossier(data, lines = [], services = []) {
  const order = data.order || {};
  const subtitle = [
    order.customer_name,
    order.sales_order_no ? `Enc. ${order.sales_order_no}` : '',
    order.commercial_name ? `Comercial ${order.commercial_name}` : '',
    order.delivery_date ? `Entrega ${date(order.delivery_date)}` : '',
  ].filter(Boolean).join(' · ') || 'Produzido, distribuído, entregue, locais e matérias-primas.';
  openModal(`OF ${order.order_no || ''}`.trim(), dossierHtml(data), subtitle);
  const body = document.getElementById('modal-body');
  const distributePanel = body.querySelector('[data-distribute-panel]');
  if (distributePanel) {
    distributePanel.innerHTML = distributeFormHtml(data.holdings || {}, lines, services, data.batches || []);
    bindDistributeForm(body, order.id, lines, services);
  }
  document.querySelector('[data-mark-alerts-seen]')?.addEventListener('click', async event => {
    const button = event.target.closest('[data-mark-alerts-seen]');
    if (!button) return;
    const id = Number(button.dataset.orderId);
    try {
      await post(`/production/orders/${id}/alerts/seen`, {});
      button.textContent = 'Alertas marcados como vistos';
      button.disabled = true;
      document.querySelectorAll('.dossier-alert').forEach(el => { el.classList.add('seen'); });
    } catch (error) { toast(error.message, 'error'); }
  });
  document.querySelectorAll('[data-compensate-event]').forEach(button => button.addEventListener('click', () => {
    const eventId = Number(button.dataset.compensateEvent);
    recordModal({
      title: 'Estornar evento de produção',
      values: {},
      fields: [{key:'reason',label:'Motivo do estorno',type:'textarea',required:true,full:true}],
      save: payload => post(`/production/events/${eventId}/compensate`, {reason: payload.reason}),
      onSaved: () => loadOrderDossier(order.id),
    });
  }));
}

export async function loadOrderDossier(orderId) {
  openModal('Ordem de fabrico', '<div class="loading">A carregar o dossier da OF…</div>', 'Produzido, distribuído, entregue e materiais.');
  try {
    const [data, lines, services] = await Promise.all([
      get(`/production/orders/${orderId}/trace`),
      crudList('production-lines', state.companyId).catch(() => []),
      crudList('subcontract-services', state.companyId).catch(() => []),
    ]);
    openOrderDossier(data, lines, services);
  } catch (error) {
    toast(error.message, 'error');
    openModal('Ordem de fabrico', `<div class="empty"><strong>Não foi possível abrir o dossier</strong><span>${esc(error.message)}</span></div>`);
  }
}
