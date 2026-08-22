import { esc, number } from '../format.js?v=20260822-15';
import { pageHeader } from '../ui.js?v=20260821-19';
import { designApi } from './api.js?v=20260822-15';
import { STAGE_LABELS } from './constants.js';

const MONTHS = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'];

function firstDay(year, month) { return `${year}-${String(month + 1).padStart(2, '0')}-01`; }
function lastDay(year, month) {
  const day = new Date(year, month + 1, 0).getDate();
  return `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
}

export async function renderReport(container) {
  const now = new Date();
  let mode = 'month';
  let year = now.getFullYear();
  let month = now.getMonth();
  let start = firstDay(year, month);
  let end = lastDay(year, month);

  async function load() {
    const period = mode === 'month' ? {start: firstDay(year, month), end: lastDay(year, month)} : {start, end};
    const data = await designApi.report(period.start, period.end);
    const years = [now.getFullYear(), now.getFullYear() - 1, now.getFullYear() - 2];
    container.innerHTML = pageHeader('Relatório de desenvolvimento', 'Peças desenvolvidas e aprovadas no período, por cliente, designer e fase.', '') + `
      <div class="design-report-controls">
        <div class="design-tabs">
          <button class="${mode === 'month' ? 'active' : ''}" data-mode="month">Por mês</button>
          <button class="${mode === 'range' ? 'active' : ''}" data-mode="range">Intervalo de datas</button>
        </div>
        ${mode === 'month' ? `<div class="design-period">
          <select data-month>${MONTHS.map((label, index) => `<option value="${index}" ${index === month ? 'selected' : ''}>${label}</option>`).join('')}</select>
          <select data-year>${years.map(value => `<option ${value === year ? 'selected' : ''}>${value}</option>`).join('')}</select>
        </div>` : `<div class="design-period">
          <label>De <input type="date" data-start value="${start}"></label>
          <label>até <input type="date" data-end value="${end}"></label>
        </div>`}
      </div>
      <div class="design-report-grid">
        <article class="card">
          <div class="card-header"><h2>Peças desenvolvidas</h2><strong>${data.developments.total}</strong></div>
          <p class="muted">${data.developments.approved} aprovadas no período</p>
          ${data.developments.by_client.slice(0, 8).map(row => `<div class="design-report-row"><span>${esc(row.name)}</span><b>${row.count}</b></div>`).join('') || '<p class="muted">Sem dados neste período.</p>'}
        </article>
        <article class="card">
          <div class="card-header"><h2>Por designer</h2></div>
          ${data.developments.by_designer.slice(0, 8).map(row => `<div class="design-report-row"><span>${esc(row.name)}</span><b>${row.count}</b></div>`).join('') || '<p class="muted">Sem dados neste período.</p>'}
        </article>
        <article class="card">
          <div class="card-header"><h2>Por fase</h2></div>
          ${data.developments.by_stage.filter(row => row.count).map(row => `<div class="design-report-row"><span>${esc(STAGE_LABELS[row.id] || row.id)}</span><b>${row.count}</b></div>`).join('') || '<p class="muted">Sem dados neste período.</p>'}
        </article>
        <article class="card">
          <div class="card-header"><h2>Produções libertadas</h2><strong>${data.productions.total}</strong></div>
          <p class="muted">${number(data.productions.quantity)} unidades no total</p>
        </article>
      </div>`;
    container.querySelectorAll('[data-mode]').forEach(button => button.addEventListener('click', () => { mode = button.dataset.mode; load(); }));
    container.querySelector('[data-month]')?.addEventListener('change', event => { month = Number(event.target.value); load(); });
    container.querySelector('[data-year]')?.addEventListener('change', event => { year = Number(event.target.value); load(); });
    container.querySelector('[data-start]')?.addEventListener('change', event => { start = event.target.value; load(); });
    container.querySelector('[data-end]')?.addEventListener('change', event => { end = event.target.value; load(); });
  }
  container.innerHTML = pageHeader('Relatório de desenvolvimento', 'A calcular o período…') + '<div class="loading">A calcular…</div>';
  await load();
}
