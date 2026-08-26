import { esc } from '../format.js?v=20260826-3';
import { pageHeader, toast } from '../ui.js?v=20260826-3';
import { designApi } from './api.js?v=20260826-3';
import { columnsFor, initials, isPhaseOne, STAGE_LABELS } from './constants.js';
import { openCreateRequest } from './create.js?v=20260826-3';
import { openDevelopment } from './detail.js?v=20260826-3';

const META = {
  portfolio: {
    title: 'Pedidos de clientes & Referências',
    subtitle: 'Pedidos recebidos, referências criadas e distribuição do trabalho pelas designers.',
    tab: 'Pedidos',
  },
  samples: {
    title: 'Desenvolvimento de amostras',
    subtitle: 'Da ficha técnica à amostra final: materiais, modelagem, confeção, envio e decisão do cliente.',
    tab: 'Amostras',
  },
};

function card(item, showStage) {
  return `<article class="design-card risk-${item.risk}" draggable="true" data-card="${item.id}">
    ${item.cover_url ? `<img src="${esc(item.cover_url)}" alt="">` : ''}
    <div>
      <b>${esc(item.code)}</b>
      ${item.title !== item.code ? `<span class="design-card-title">${esc(item.title)}</span>` : ''}
      ${item.request_group ? `<em>Pedido: ${esc(item.request_group)}</em>` : ''}
      <div class="design-card-chips">
        <span>${showStage ? esc(STAGE_LABELS[item.current_stage] || item.current_stage) : esc(item.customer_name)}</span>
        ${item.status?.includes('waiting') ? '<span class="wait">Em espera</span>' : ''}
      </div>
      ${item.waiting_reason ? `<p class="design-wait">${esc(item.waiting_reason)}</p>` : ''}
      <small>${esc(item.owner_name || 'Por distribuir')}${item.requested_quantity ? ` · ${item.requested_quantity} un.` : ''}</small>
      <p class="design-next-line">${esc(item.next_action)}</p>
      <footer><span>${item.days_in_stage} d</span>${item.open_tasks_count ? `<span>${item.open_tasks_count} pend.</span>` : ''}<i>${esc(initials(item.assignees?.[0]?.name || item.owner_name))}</i></footer>
    </div>
  </article>`;
}

export async function renderBoard(container, board) {
  const meta = META[board];
  let items = [];
  let view = 'board';
  let query = '';
  let clientFilter = '';
  let riskFilter = '';
  let assigneeFilter = '';
  const reload = async () => { items = await designApi.list(); draw(); };

  function filtered() {
    return items.filter(item => {
      const text = `${item.code} ${item.title} ${item.request_group || ''} ${item.owner_name} ${item.customer_name}`.toLowerCase();
      if (query && !text.includes(query.toLowerCase())) return false;
      if (clientFilter && item.customer_name !== clientFilter) return false;
      if (riskFilter && item.risk !== riskFilter) return false;
      if (assigneeFilter && !(item.assignees || []).some(person => person.name === assigneeFilter) && item.owner_name !== assigneeFilter) return false;
      return true;
    });
  }

  function draw() {
    const rows = filtered();
    const archived = rows.filter(item => item.archived);
    const active = rows.filter(item => !item.archived && (board === 'portfolio' ? isPhaseOne(item.current_stage) : !isPhaseOne(item.current_stage)));
    const clients = [...new Set(items.map(item => item.customer_name).filter(Boolean))].sort();
    const assignees = [...new Set(items.flatMap(item => [item.owner_name, ...(item.assignees || []).map(person => person.name)].filter(Boolean)))].sort();
    const byClient = view === 'client';
    const columns = byClient
      ? [...new Set(active.map(item => item.customer_name))].sort().map(name => [name, name])
      : columnsFor(board);
    const grouped = Object.fromEntries(columns.map(([id]) => [id, active.filter(item => byClient ? item.customer_name === id : item.current_stage === id)]));
    container.innerHTML = pageHeader(meta.title, meta.subtitle, '<button class="btn primary" data-new-request>＋ Novo pedido</button>') + `
      <div class="design-legend"><span class="mint">Concluído</span><span class="sky">Em curso</span><span class="yellow">Aguarda</span><span class="pink">Atraso</span></div>
      <div class="design-tabs">
        <button class="${view === 'board' ? 'active' : ''}" data-view="board">${meta.tab} <b>${active.length}</b></button>
        <button class="${view === 'client' ? 'active' : ''}" data-view="client">Por cliente <b>${active.length}</b></button>
        <button class="${view === 'archive' ? 'active' : ''}" data-view="archive">Arquivo <b>${archived.length}</b></button>
      </div>
      <div class="design-filters">
        <input data-query placeholder="Pesquisar código, modelo, responsável…" value="${esc(query)}">
        <select data-client><option value="">Todos os clientes</option>${clients.map(name => `<option ${clientFilter === name ? 'selected' : ''}>${esc(name)}</option>`).join('')}</select>
        <select data-risk>
          <option value="">Todos os riscos</option>
          <option value="high" ${riskFilter === 'high' ? 'selected' : ''}>Risco alto</option>
          <option value="medium" ${riskFilter === 'medium' ? 'selected' : ''}>Risco médio</option>
          <option value="low" ${riskFilter === 'low' ? 'selected' : ''}>Sem risco</option>
        </select>
        <select data-assignee><option value="">Toda a equipa</option>${assignees.map(name => `<option ${assigneeFilter === name ? 'selected' : ''}>${esc(name)}</option>`).join('')}</select>
      </div>
      ${view === 'archive' ? `<div class="design-archive">${archived.map(item => `<article>
        <div><b>${esc(item.code)}</b><span>${esc(item.customer_name)} · ${esc(item.owner_name)}</span>${item.waiting_reason ? `<em>${esc(item.waiting_reason)}</em>` : ''}</div>
        <button class="btn small" data-reactivate="${item.id}">Reativar</button>
      </article>`).join('') || '<p class="muted">Arquivo vazio.</p>'}</div>` : `<div class="design-board">${columns.map(([id, title]) => `<section class="design-column" data-drop="${esc(id)}">
        <header><strong>${esc(title)}</strong><span>${(grouped[id] || []).length}</span></header>
        <div class="design-column-cards">${(grouped[id] || []).map(item => card(item, byClient)).join('')}</div>
      </section>`).join('')}</div>`}`;
    bind(active);
  }

  function bind() {
    container.querySelector('[data-new-request]').addEventListener('click', () => openCreateRequest(() => { location.hash = '#/design-requests'; reload(); }));
    container.querySelectorAll('[data-view]').forEach(button => button.addEventListener('click', () => { view = button.dataset.view; draw(); }));
    const queryInput = container.querySelector('[data-query]');
    queryInput?.addEventListener('input', event => {
      query = event.target.value;
      const caret = event.target.selectionStart;
      draw();
      const next = container.querySelector('[data-query]');
      next.focus();
      next.setSelectionRange(caret, caret);
    });
    container.querySelector('[data-client]').addEventListener('change', event => { clientFilter = event.target.value; draw(); });
    container.querySelector('[data-risk]').addEventListener('change', event => { riskFilter = event.target.value; draw(); });
    container.querySelector('[data-assignee]').addEventListener('change', event => { assigneeFilter = event.target.value; draw(); });
    container.querySelectorAll('[data-reactivate]').forEach(button => button.addEventListener('click', async () => {
      try { await designApi.patch(button.dataset.reactivate, {status: 'active', waiting_reason: null}); toast('Desenvolvimento reativado.'); await reload(); }
      catch (error) { toast(error.message, 'error'); }
    }));
    let dragging = false;
    container.querySelectorAll('[data-card]').forEach(node => {
      const id = Number(node.dataset.card);
      const item = items.find(row => row.id === id);
      node.addEventListener('click', () => { if (dragging) { dragging = false; return; } openDevelopment(item, {onChanged: reload}); });
      node.addEventListener('dragstart', event => {
        dragging = true;
        event.dataTransfer.setData('text/plain', String(id));
        node.classList.add('is-dragging');
      });
      node.addEventListener('dragend', () => { node.classList.remove('is-dragging'); setTimeout(() => { dragging = false; }, 50); });
    });
    if (view === 'client') return;
    container.querySelectorAll('[data-drop]').forEach(column => {
      column.addEventListener('dragover', event => { event.preventDefault(); column.classList.add('is-over'); });
      column.addEventListener('dragleave', () => column.classList.remove('is-over'));
      column.addEventListener('drop', async event => {
        event.preventDefault();
        column.classList.remove('is-over');
        const id = Number(event.dataTransfer.getData('text/plain'));
        const item = items.find(row => row.id === id);
        const stage = column.dataset.drop;
        if (!item || item.current_stage === stage) return;
        try {
          await designApi.move(id, {to_stage: stage});
          if (board === 'portfolio' && stage === 'ficha_tecnica') toast('Referência distribuída — passou para a ficha técnica.');
          await reload();
        } catch (error) { toast(error.message, 'error'); }
      });
    });
  }

  container.innerHTML = pageHeader(meta.title, meta.subtitle) + '<div class="loading">A carregar o pipeline…</div>';
  await reload();
}
