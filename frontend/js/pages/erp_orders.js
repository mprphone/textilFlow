import { crudUpdate, get } from '../api.js';
import { date, esc, number, progress } from '../format.js?v=20260826-3';
import { state } from '../state.js';
import { pageHeader, toast } from '../ui.js?v=20260826-3';
import { prepareFromSales } from './commercial_docs.js?v=20260826-3';

function orderStageIndex(status) {
  if (status === 'finished') return 3;
  if (status === 'shipped') return 2;
  if (status === 'in_production') return 1;
  return 0;
}

function orderFlow(row) {
  const index = orderStageIndex(row.status);
  const stepClass = position => position < index ? 'done' : position === index ? 'current' : 'next';
  const canFinish = row.status === 'shipped';
  return `<div class="proposal-click-flow compact" aria-label="Estado da encomenda">
    <button type="button" class="${stepClass(0)}" data-set-status="${row.id}" data-status-value="confirmed" title="Aceite"><i>${index > 0 ? '✓' : '1'}</i><span>Aceite</span></button>
    <b>›</b>
    <button type="button" class="${stepClass(1)}" data-set-status="${row.id}" data-status-value="in_production" title="Em produção"><i>${index > 1 ? '✓' : '2'}</i><span>Em produção</span></button>
    <b>›</b>
    <button type="button" class="${stepClass(2)}" data-open-shipping title="Ver em Expedição"><i>${index > 2 ? '✓' : '3'}</i><span>Expedido</span></button>
    <b>›</b>
    <button type="button" class="${stepClass(3)}" ${canFinish ? `data-set-status="${row.id}" data-status-value="finished"` : 'disabled'} title="${canFinish ? 'Marcar como finalizada' : 'Finalizado'}"><i>${index >= 3 ? '✓' : '4'}</i><span>Finalizado</span></button>
  </div>`;
}

function progressCell(produced, total) {
  const pct = total ? (produced / total * 100) : 0;
  return `<div class="qty-cell"><span><b>${number(produced)}</b> / ${number(total)}</span>${progress(pct)}</div>`;
}

export async function render(container) {
  const rows = await get(`/erp/${state.companyId}/sales-orders`);
  container.innerHTML = pageHeader('Encomendas de cliente', 'Quantidade total, produzida e faturada — estado e documentos do Primavera num só sítio.', '') + `
    <div class="table-wrap listing-table"><table class="data-table" aria-label="Encomendas"><thead><tr>
      <th>Encomenda</th><th>Cliente</th><th>Data</th><th>Entrega</th><th>Produzido</th><th>Faturado</th><th>Estado</th><th>Documentos</th>
    </tr></thead><tbody>${rows.length ? rows.map(row => `<tr>
        <td><b>${esc(row.order_no)}</b>${row.customer_po ? `<div class="table-subline">PO ${esc(row.customer_po)}</div>` : ''}</td>
        <td>${esc(row.customer_name)}</td>
        <td>${date(row.order_date)}</td>
        <td>${date(row.delivery_date)}</td>
        <td>${progressCell(row.quantity_produced, row.quantity_total)}</td>
        <td>${number(row.quantity_invoiced)} / ${number(row.quantity_total)}</td>
        <td>${orderFlow(row)}</td>
        <td class="listing-actions"><div class="row-actions">
          <button class="btn small primary" type="button" data-erp-so="sales_invoice" data-id="${row.id}">Fatura</button>
          <button class="btn small" type="button" data-erp-so="sales_credit" data-id="${row.id}">NC</button>
          <button class="btn small" type="button" data-erp-so="sales_debit" data-id="${row.id}">ND</button>
          <button class="btn small" type="button" data-erp-so="sales_delivery" data-id="${row.id}">Guia</button>
        </div></td>
      </tr>`).join('') : `<tr><td colspan="8"><div class="empty"><strong>Sem encomendas</strong>As encomendas de cliente aparecem aqui assim que forem criadas em Comercial.</div></td></tr>`}</tbody></table></div>`;

  container.addEventListener('click', async event => {
    const setStatus = event.target.closest('[data-set-status]');
    if (setStatus) {
      try {
        await crudUpdate('sales-orders', Number(setStatus.dataset.setStatus), { status: setStatus.dataset.statusValue });
        toast('Estado atualizado.');
        await render(container);
      } catch (error) { toast(error.message, 'error'); }
      return;
    }
    if (event.target.closest('[data-open-shipping]')) { location.hash = '#/shipping'; return; }
    const erpButton = event.target.closest('[data-erp-so]');
    if (erpButton) {
      try {
        const saved = await prepareFromSales(Number(erpButton.dataset.id), erpButton.dataset.erpSo);
        toast(`${saved.doc_no} preparado para o Primavera.`);
      } catch (error) { toast(error.message, 'error'); }
    }
  });
}
