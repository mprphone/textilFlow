import { esc } from '../format.js?v=20260826-3';
import { pageHeader } from '../ui.js?v=20260826-3';
import { designApi } from './api.js?v=20260826-3';
import { STAGE_LABELS } from './constants.js';
import { openDevelopment } from './detail.js?v=20260826-3';

export async function renderOrganization(container) {
  let tab = 'designers';
  async function load() {
    const data = await designApi.organization();
    const groups = tab === 'designers' ? data.designers : data.clients;
    container.innerHTML = pageHeader('Organização do desenvolvimento', 'Quem tem o quê: carga por designer e por cliente, incluindo o que ainda não foi distribuído.', '') + `
      <div class="design-tabs">
        <button class="${tab === 'designers' ? 'active' : ''}" data-org="designers">Por designer <b>${data.designers.length}</b></button>
        <button class="${tab === 'clients' ? 'active' : ''}" data-org="clients">Por cliente <b>${data.clients.length}</b></button>
      </div>
      ${data.unassigned.length ? `<div class="design-unassigned"><strong>Por distribuir (${data.unassigned.length})</strong>${data.unassigned.map(item => `<button data-open="${item.id}">${esc(item.code)} · ${esc(item.customer_name)}</button>`).join('')}</div>` : ''}
      <div class="design-org-grid">${groups.map(group => `<section class="card">
        <div class="card-header">
          <div><h2>${esc(group.name)}</h2><p class="muted">${group.open} em curso · ${group.overdue} fora de prazo · ${group.waiting} à espera</p></div>
          <span class="${group.high_risk ? 'badge red' : 'badge blue'}">${group.total}</span>
        </div>
        ${group.items.filter(item => !item.archived).slice(0, 8).map(item => `<button class="design-priority" data-open="${item.id}">
          <div><b>${esc(item.code)}</b><small>${esc(STAGE_LABELS[item.current_stage] || item.current_stage)} · ${esc(item.next_action)}</small></div>
          <em class="risk-${item.risk}">${item.days_in_stage} d</em>
        </button>`).join('') || '<p class="muted">Sem modelos.</p>'}
      </section>`).join('')}</div>`;
    container.querySelectorAll('[data-org]').forEach(button => button.addEventListener('click', () => { tab = button.dataset.org; load(); }));
    const allItems = [...data.designers, ...data.clients].flatMap(group => group.items);
    container.querySelectorAll('[data-open]').forEach(button => button.addEventListener('click', () => {
      const item = allItems.find(row => row.id === Number(button.dataset.open));
      if (item) openDevelopment(item, {onChanged: load});
    }));
  }
  container.innerHTML = pageHeader('Organização do desenvolvimento', 'A carregar a distribuição…') + '<div class="loading">A agrupar o trabalho…</div>';
  await load();
}
