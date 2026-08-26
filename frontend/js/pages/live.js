import { get } from '../api.js';
import { badge, esc, number, percent, progress } from '../format.js?v=20260826-3';
import { state } from '../state.js';
import { pageHeader } from '../ui.js?v=20260826-3';

export async function render(container) {
  const data = await get(`/production/${state.companyId}/live`);
  container.innerHTML = pageHeader('Produção em direto · Confeção', 'Estado de cada operador e linha de costura.', '<a class="btn success" href="#/floor">Abrir terminal</a>') + `
    <div class="line-cards">${data.lines.map(line => `<div class="line-card card"><h3>${esc(line.name)}</h3><div class="line-kpis"><div><small>Produção</small><b>${number(line.good)}</b></div><div><small>Eficiência</small><b>${percent(line.efficiency)}</b></div><div><small>Rejeitadas</small><b>${number(line.rejected)}</b></div></div>${progress(line.efficiency, line.efficiency >= line.target ? 'green' : 'red')}</div>`).join('')}</div>
    <div class="card section-spaced"><div class="card-header"><h2>Postos ativos</h2><span>Atualizar a página para dados mais recentes</span></div><div class="table-wrap"><table class="data-table"><thead><tr><th>Ordem</th><th>Operador</th><th>Operação</th><th>Máquina</th><th>Produzido</th><th>Progresso</th><th>Eficiência</th><th>Estado</th></tr></thead><tbody>
    ${data.assignments.map(row => `<tr><td><b>${esc(row.order_no)}</b><br><small>${esc(row.reference)}</small></td><td>${esc(row.employee)}</td><td>${esc(row.operation)}</td><td>${esc(row.machine)}</td><td>${number(row.completed_quantity)} / ${number(row.planned_quantity)}</td><td>${progress(row.progress)}</td><td>${percent(row.efficiency)}</td><td>${badge(row.status)}</td></tr>`).join('')}
    </tbody></table></div></div>`;
}
