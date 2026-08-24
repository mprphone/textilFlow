import { get, post } from '../api.js';
import { badge, date, esc, money, number } from '../format.js?v=20260819-9';
import { state } from '../state.js';
import { pageHeader, toast } from '../ui.js?v=20260820-5';

function kpi(label, value, tone = '') {
  return `<div class="tower-kpi ${tone}"><span>${esc(label)}</span><strong>${value}</strong></div>`;
}

function renderAlerts(rows) {
  if (!rows.length) return '<div class="empty-state compact">Sem exceções operacionais abertas.</div>';
  return `<div class="tower-alerts">${rows.map(row => `<article class="tower-alert ${row.severity}">
    <div><b>${esc(row.title)}</b><p>${esc(row.detail || '')}</p></div>
    <div class="tower-alert-actions">${row.action_route ? `<button class="btn small" data-route="${esc(row.action_route)}">${esc(row.action_label || 'Abrir')}</button>` : ''}<button class="btn small" data-resolve="${row.id}">Resolver</button></div>
  </article>`).join('')}</div>`;
}

function planTable(rows) {
  if (!rows.length) return '<div class="empty-state compact">Sem OF ativas para sequenciar.</div>';
  return `<div class="table-wrap"><table class="data-table"><thead><tr><th>#</th><th>OF</th><th>Linha</th><th>Carga</th><th>Início</th><th>Fim finito</th><th>Prometido</th><th>Risco</th><th></th></tr></thead><tbody>${rows.map(row => `<tr>
    <td>${row.sequence}</td><td><b>${esc(row.order_no)}</b></td><td>${esc(row.line)}</td><td>${number(row.required_minutes)} min</td><td>${date(row.planned_start)}</td><td>${date(row.planned_end)}</td><td>${date(row.promised_date)}</td><td>${badge(row.risk)}</td><td><button class="btn small" data-flow="${row.production_order_id}">Sequência</button></td>
  </tr>`).join('')}</tbody></table></div>`;
}

function orderTable(rows) {
  return `<div class="table-wrap"><table class="data-table"><thead><tr><th>OF</th><th>Estado</th><th>Produzido</th><th>Receita</th><th>Custo previsto</th><th>Margem prevista</th></tr></thead><tbody>${rows.map(row => `<tr>
    <td><button class="link-button" data-dossier="${row.id}">${esc(row.order_no)}</button></td><td>${badge(row.status)}</td><td>${number(row.completed_quantity)} / ${number(row.quantity)}</td><td>${money(row.revenue)}</td><td>${money(row.forecast_cost)}</td><td class="${row.forecast_margin < 0 ? 'text-danger' : ''}">${money(row.forecast_margin)}</td>
  </tr>`).join('')}</tbody></table></div>`;
}

function flowHtml(flow) {
  if (!flow.steps.length) return '<div class="empty-state compact">Este artigo ainda não tem roteiro de operações.</div>';
  return `<div class="operation-flow">${flow.steps.map((step, index) => `<div class="operation-step ${step.status}">
    <div class="operation-sequence">${index + 1}</div><div><b>${esc(step.operation_name || `Operação ${step.operation_id}`)}</b><small>${esc(step.operation_code || '')}${step.operation_code ? ' · ' : ''}${number(step.produced_quantity)} produzidas · ${number(step.transferred_quantity)} transferidas · ${number(step.available_to_transfer)} disponíveis</small></div>
    ${step.available_to_transfer > 0 ? `<div class="operation-transfer"><input type="number" min="0.01" max="${step.available_to_transfer}" step="0.01" value="${step.available_to_transfer}" data-qty><button class="btn small primary" data-transfer="${step.id}" data-order="${flow.order.id}">Transferir →</button></div>` : badge(step.status)}
  </div>`).join('')}</div>`;
}

export async function render(container) {
  const data = await get(`/production/${state.companyId}/control-tower`);
  const k = data.kpis;
  container.innerHTML = pageHeader('Torre de controlo', 'Uma fila única de decisões: capacidade finita, exceções, execução e margem.', '<button class="btn" data-refresh>↻ Atualizar</button><button class="btn primary" data-apply-plan>Aplicar plano finito</button>') + `
    <div class="tower-kpis">${kpi('OF ativas', number(k.active_orders))}${kpi('Alertas críticos', number(k.critical_alerts), k.critical_alerts ? 'critical' : '')}${kpi('Receita prevista', money(k.forecast_revenue))}${kpi('Custo previsto', money(k.forecast_cost))}${kpi('Margem prevista', money(k.forecast_margin), k.forecast_margin < 0 ? 'critical' : 'positive')}</div>
    <div class="tower-grid"><section class="card"><div class="card-header"><div><h2>Exceções que exigem ação</h2><span>Alertas persistentes, resolvidos automaticamente quando a causa desaparece.</span></div></div>${renderAlerts(data.alerts)}</section>
    <section class="card"><div class="card-header"><div><h2>Carga por linha · 90 dias úteis</h2><span>Capacidade nominal corrigida por presenças, eficiência, setups e manutenção.</span></div></div><div class="line-loads">${data.plan.lines.map(line => `<div><span>${esc(line.name)}</span><b>${number(line.planned_minutes)} / ${number(line.capacity_minutes)} min</b></div>`).join('') || 'Sem linhas ativas.'}</div></section></div>
    <section class="card"><div class="card-header"><div><h2>Sequência produtiva finita</h2><span>Prioridade, prazo prometido e capacidade disponível determinam a ordem.</span></div></div>${planTable(data.plan.orders)}<div data-flow-panel></div></section>
    <section class="card"><div class="card-header"><div><h2>Custo e margem por OF</h2><span>Real consumido + custo estimado à conclusão.</span></div></div>${orderTable(data.orders)}</section>`;

  container.querySelector('[data-refresh]').addEventListener('click', () => render(container));
  container.querySelector('[data-apply-plan]').addEventListener('click', async () => {
    try { await post(`/production/${state.companyId}/finite-plan`, {}); toast('Plano finito aplicado às OF.', 'success'); await render(container); }
    catch (error) { toast(error.message, 'error'); }
  });
  container.addEventListener('click', async event => {
    const route = event.target.closest('[data-route]')?.dataset.route;
    if (route) location.hash = `#/${route}`;
    const resolve = event.target.closest('[data-resolve]')?.dataset.resolve;
    if (resolve) { try { await post(`/production/alerts/${resolve}/resolve`, {}); await render(container); } catch (error) { toast(error.message, 'error'); } }
    const flowId = event.target.closest('[data-flow]')?.dataset.flow;
    if (flowId) { try { const flow = await get(`/production/orders/${flowId}/operation-flow`); container.querySelector('[data-flow-panel]').innerHTML = `<h3 class="flow-title">Fluxo da OF ${esc(flow.order.order_no)}</h3>${flowHtml(flow)}`; } catch (error) { toast(error.message, 'error'); } }
    const transfer = event.target.closest('[data-transfer]');
    if (transfer) {
      const input = transfer.parentElement.querySelector('[data-qty]');
      try { const result = await post(`/production/orders/${transfer.dataset.order}/transfer-operation`, {product_operation_id:Number(transfer.dataset.transfer), quantity:Number(input.value)}); container.querySelector('[data-flow-panel]').innerHTML = `<h3 class="flow-title">Fluxo da OF ${esc(result.flow.order.order_no)}</h3>${flowHtml(result.flow)}`; toast('Quantidade transferida com rastreabilidade.', 'success'); } catch (error) { toast(error.message, 'error'); }
    }
    const dossier = event.target.closest('[data-dossier]')?.dataset.dossier;
    if (dossier) location.hash = `#/tracking?order=${dossier}`;
  });
}
