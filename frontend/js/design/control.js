import { date, esc } from '../format.js?v=20260826-3';
import { pageHeader } from '../ui.js?v=20260826-3';
import { designApi } from './api.js?v=20260826-3';
import { STAGE_LABELS } from './constants.js';
import { openDevelopment } from './detail.js?v=20260826-3';
import { openCreateRequest } from './create.js?v=20260826-3';

export async function renderToday(container) {
  async function load() {
    const data = await designApi.today();
    const stats = [
      [data.overdue_count, 'Prazos ultrapassados', 'peach'],
      [data.waiting_supplier_count, 'Aguardam fornecedor', 'yellow'],
      [data.waiting_client_count, 'Aguardam cliente', 'lilac'],
      [data.blocked_count, 'Bloqueados', 'pink'],
      [data.unassigned_count, 'Por distribuir', 'sky'],
      [data.approved_count, 'Aprovados a produzir', 'mint'],
    ];
    container.innerHTML = pageHeader('Prioridades de hoje', 'Prazo, risco, bloqueios e distribuição — o que a designer deve tratar primeiro.', '<button class="btn primary" data-new-request>＋ Novo pedido</button>') + `
      <div class="design-stats">${stats.map(([value, label, tone]) => `<article class="${tone}"><strong>${value}</strong><span>${esc(label)}</span></article>`).join('')}</div>
      <div class="design-today-grid">
        <section class="card">
          <div class="card-header"><h2>O que fazer primeiro</h2><span>${data.priorities.length} prioridades</span></div>
          ${data.priorities.map((item, index) => `<button class="design-priority" data-open="${item.id}">
            <i>${index + 1}</i>
            <div><b>${esc(item.code)} — ${esc(item.title)}</b><small>${esc(item.customer_name)} · ${esc(item.next_action)}</small></div>
            <em class="risk-${item.risk}">${item.days_in_stage} d · ${esc(STAGE_LABELS[item.current_stage] || item.current_stage)}</em>
          </button>`).join('') || '<p class="muted">Nada urgente. Bom trabalho.</p>'}
        </section>
        <section class="card">
          <div class="card-header"><h2>Fora de prazo</h2><span>${data.overdue.length}</span></div>
          ${data.overdue.map(item => `<button class="design-priority" data-open="${item.id}">
            <div><b>${esc(item.code)}</b><small>${esc(item.customer_name)} · ${date(item.due_date)}</small></div>
            <em class="risk-high">${esc(item.owner_name)}</em>
          </button>`).join('') || '<p class="muted">Sem prazos ultrapassados.</p>'}
        </section>
      </div>`;
    container.querySelector('[data-new-request]').addEventListener('click', () => openCreateRequest(() => { location.hash = '#/design-requests'; }));
    container.querySelectorAll('[data-open]').forEach(button => button.addEventListener('click', async () => {
      const items = await designApi.list();
      const item = items.find(row => row.id === Number(button.dataset.open));
      if (item) openDevelopment(item, {onChanged: load});
    }));
  }
  container.innerHTML = pageHeader('Prioridades de hoje', 'A carregar o controlo do desenvolvimento…') + '<div class="loading">A ordenar prioridades…</div>';
  await load();
}
