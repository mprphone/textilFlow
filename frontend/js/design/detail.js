import { date, datetime, esc, humanize } from '../format.js?v=20260822-15';
import { toast } from '../ui.js?v=20260821-19';
import { designApi } from './api.js?v=20260822-15';
import { PIPELINE, PHASE_ONE, ROLE_NAMES, STAGE_LABELS, STATUS_BADGE, TASK_KINDS, TASK_STATUSES, isPhaseOne } from './constants.js';

let overlay = null;
let onChanged = null;

export function closeDevelopment() {
  overlay?.remove();
  overlay = null;
}

if (typeof window !== 'undefined' && !window.__tfDesignOverlayBound) {
  window.addEventListener('hashchange', closeDevelopment);
  window.__tfDesignOverlayBound = true;
}

export async function openDevelopment(item, options = {}) {
  onChanged = options.onChanged || null;
  closeDevelopment();
  overlay = document.createElement('div');
  overlay.className = 'design-overlay';
  overlay.innerHTML = `<div class="design-drawer"><div class="loading">A abrir o desenvolvimento…</div></div>`;
  overlay.addEventListener('mousedown', event => { if (event.target === overlay) closeDevelopment(); });
  document.body.appendChild(overlay);
  await renderDetail(item.id);
}

async function renderDetail(id) {
  if (!overlay) return;
  try {
    const [item, team] = await Promise.all([designApi.detail(id), designApi.team()]);
    overlay.querySelector('.design-drawer').innerHTML = markup(item, team);
    bind(item, team);
  } catch (error) {
    overlay.querySelector('.design-drawer').innerHTML = `<div class="card"><h2>Não foi possível abrir</h2><p class="muted">${esc(error.message)}</p></div>`;
  }
}

function nextStage(item) {
  const index = PIPELINE.findIndex(([id]) => id === item.current_stage);
  return PIPELINE[Math.min(index + 1, PIPELINE.length - 1)];
}

function advanceMarkup(item) {
  const next = nextStage(item);
  if (item.current_stage === 'proposta_cliente') {
    return `<button class="btn primary wide" data-move="ficha_tecnica">Distribuição concluída — criar ficha técnica</button>`;
  }
  if (item.current_stage === 'envio_cliente') {
    return `<button class="btn primary wide" data-move="resposta_cliente" data-note="Amostra enviada ao cliente; aguarda resposta.">Amostra enviada — aguardar resposta do cliente</button>`;
  }
  if (item.current_stage === 'resposta_cliente') {
    return `<div class="design-decision">
      <button class="btn success" data-move="aprovado" data-note="Cliente aprovou a amostra.">Cliente aprovou</button>
      <button class="btn" data-retouch>Pediu retificações</button>
      <button class="btn danger" data-reject>Cliente reprovou</button>
    </div>`;
  }
  if (item.current_stage === 'retificacoes') {
    return `<button class="btn primary wide" data-move="envio_cliente" data-note="Retificações concluídas; nova versão pronta para envio.">Retificações concluídas — reenviar ao cliente</button>`;
  }
  if (item.current_stage === 'aprovado') {
    return `<button class="btn primary wide" data-production>Criar produção industrial</button>`;
  }
  return `<button class="btn primary wide" data-move="${next[0]}">Concluir “${esc(STAGE_LABELS[item.current_stage])}” e avançar para “${esc(next[1])}”</button>`;
}

function markup(item, team) {
  const badge = STATUS_BADGE[item.status] || STATUS_BADGE.active;
  const index = PIPELINE.findIndex(([id]) => id === item.current_stage);
  const stages = isPhaseOne(item.current_stage) ? PIPELINE.filter(([id]) => PHASE_ONE.includes(id)) : PIPELINE;
  const photos = [...new Set([...(item.images || []), item.cover_url].filter(Boolean))];
  return `
    <header class="design-drawer-head">
      <div>
        <small>${esc(item.customer_name)} · ${esc(STAGE_LABELS[item.current_stage] || item.current_stage)}</small>
        <h2>${esc(item.title === item.code ? item.title : `${item.code} — ${item.title}`)}</h2>
      </div>
      <span class="design-status tone-${badge.tone}">${esc(badge.label)}</span>
      <button class="icon-button" type="button" data-icon="close" data-close-dev aria-label="Fechar" title="Fechar"></button>
    </header>
    <div class="design-drawer-body">
      <div class="design-drawer-main">
        ${photos.length ? `<div class="design-photos">${photos.map(url => `<img src="${esc(url)}" alt="">`).join('')}</div>` : ''}
        <div class="design-meta">
          <span>Designer: <b>${esc(item.owner_name || 'Por distribuir')}</b></span>
          <span>${item.days_in_stage} dias nesta fase</span>
          <span>Prazo: ${date(item.due_date)}</span>
          ${item.estimated_completion ? `<span class="${item.eta_at_risk ? 'is-risk' : ''}">Previsão: ${date(item.estimated_completion)}</span>` : ''}
        </div>
        ${(item.request_group || item.request_notes || item.requested_quantity) ? `<div class="design-brief">
          ${item.request_group ? `<div><small>Pedido / campanha</small><b>${esc(item.request_group)}</b></div>` : ''}
          <div><small>Origem</small><b>${esc(humanize(item.request_source || '—'))}</b></div>
          <div><small>Quantidade</small><b>${item.requested_quantity ? `${item.requested_quantity} un.` : 'Por definir'}</b></div>
          ${item.request_notes ? `<p>${esc(item.request_notes)}</p>` : ''}
        </div>` : ''}
        <section class="design-focus">
          <div class="design-trace">${stages.map(([id, label], pos) => {
            const global = PIPELINE.findIndex(([stage]) => stage === id);
            const stateClass = global < index ? 'done' : global === index ? 'active' : '';
            return `<button type="button" class="${stateClass}" data-jump="${id}" ${global > index ? '' : ''}><i>${pos + 1}</i>${esc(label)}</button>`;
          }).join('')}</div>
          ${advanceMarkup(item)}
          <div class="design-next"><small>Próxima ação</small><strong>${esc(item.next_action)}</strong>${item.waiting_reason ? `<em>${esc(item.waiting_reason)}</em>` : ''}</div>
        </section>
        ${item.suggestions?.length ? `<section class="design-hints">${item.suggestions.map(text => `<p>${esc(text)}</p>`).join('')}</section>` : ''}
        <details class="design-block" open>
          <summary>Equipa e funções <span>${(item.assignees || []).length}</span></summary>
          <div class="design-chips">${(item.assignees || []).map(person => `<span>${esc(person.name)} · ${esc(ROLE_NAMES[person.role] || person.role)} <button type="button" class="btn icon danger" data-icon="delete" data-remove-assignee="${person.id}" aria-label="Remover pessoa" title="Remover pessoa"></button></span>`).join('') || '<em>Sem equipa estruturada.</em>'}
          </div>
          <div class="design-add">
            <select data-assignee-user><option value="">Adicionar pessoa…</option>${team.map(user => `<option value="${user.id}">${esc(user.name)}</option>`).join('')}</select>
            <select data-assignee-role>${Object.entries(ROLE_NAMES).map(([id, label]) => `<option value="${id}">${esc(label)}</option>`).join('')}</select>
            <button type="button" class="btn small" data-add-assignee>Adicionar</button>
          </div>
        </details>
        <details class="design-block" open>
          <summary>Pendências paralelas <span>${(item.tasks || []).length}</span></summary>
          <p class="muted">Malhas, tinturaria, bordados e acessórios podem avançar em simultâneo a partir da ficha técnica.</p>
          ${(item.tasks || []).map(task => `<div class="design-task ${task.status === 'done' ? 'is-done' : ''}">
            <div><b>${esc(TASK_KINDS[task.kind] || task.kind)}</b><small>${esc(task.note || 'Sem nota')}${task.responsible_name ? ` · ${esc(task.responsible_name)}` : ''}</small></div>
            <select data-task-status="${task.id}">${Object.entries(TASK_STATUSES).map(([id, label]) => `<option value="${id}" ${task.status === id ? 'selected' : ''}>${esc(label)}</option>`).join('')}</select>
            <button type="button" class="btn icon danger" data-icon="delete" data-remove-task="${task.id}" aria-label="Remover tarefa" title="Remover tarefa"></button>
          </div>`).join('') || '<p class="muted">Sem pendências paralelas.</p>'}
          <div class="design-add">
            <select data-task-kind>${Object.entries(TASK_KINDS).map(([id, label]) => `<option value="${id}">${esc(label)}</option>`).join('')}</select>
            <input data-task-note placeholder="Nota ou bloqueio…">
            <select data-task-owner><option value="">Sem responsável</option>${team.map(user => `<option value="${user.id}">${esc(user.name)}</option>`).join('')}</select>
            <button type="button" class="btn small" data-add-task>Adicionar</button>
          </div>
        </details>
        <section class="design-block">
          <h3>Notas</h3>
          <textarea data-notes rows="3" placeholder="Medidas, materiais, decisões do cliente…">${esc(item.description || '')}</textarea>
          <button type="button" class="btn small" data-save-notes>Guardar notas</button>
        </section>
        <section class="design-block">
          <h3>Percurso do modelo</h3>
          <div class="design-history">${(item.stage_history || []).map(event => `<article>
            <b>${esc(STAGE_LABELS[event.stage] || event.stage)}</b>
            <span>${esc(humanize(event.status))} · ${event.days} d${event.responsible_name ? ` · ${esc(event.responsible_name)}` : ''}</span>
            <input data-stage-note="${event.stage}" value="${esc(event.note || '')}" placeholder="O que foi feito nesta fase">
          </article>`).join('') || '<p class="muted">Ainda sem histórico.</p>'}</div>
        </section>
        <details class="design-block">
          <summary>Comentários <span>${(item.comments || []).length}</span></summary>
          <div class="design-add">
            <textarea data-comment rows="2" placeholder="Escrever um comentário…"></textarea>
            <button type="button" class="btn small" data-add-comment>Comentar</button>
          </div>
          ${(item.comments || []).map(row => `<div class="design-comment"><b>${esc(row.author)}</b><span>${esc(row.body)}</span><small>${datetime(row.created_at)}</small></div>`).join('')}
        </details>
        ${item.style ? `<p class="muted">Ficha técnica: <a href="#/styles">${esc(item.style.reference)}</a>${item.production ? ` · OF ${esc(item.production.order_no)}` : ''}</p>` : ''}
      </div>
      <aside class="design-drawer-side">
        <h3>Ações rápidas</h3>
        <button class="btn" data-wait="waiting_supplier">Aguardar fornecedor</button>
        <button class="btn" data-wait="waiting_client">Aguardar cliente</button>
        <button class="btn" data-block>Registar bloqueio</button>
        ${['waiting_supplier', 'waiting_client', 'blocked'].includes(item.status) ? '<button class="btn" data-resume>Retomar</button>' : ''}
        <button class="btn danger" data-delete-dev>Eliminar desenvolvimento</button>
        <p class="muted">O botão grande avança de fase. Estas ações registam esperas e bloqueios.</p>
      </aside>
    </div>`;
}

function bind(item) {
  const root = overlay;
  const changed = async () => { onChanged?.(); await renderDetail(item.id); };
  const fail = error => toast(error.message, 'error');
  root.querySelector('[data-close-dev]').addEventListener('click', closeDevelopment);
  root.querySelectorAll('[data-move]').forEach(button => button.addEventListener('click', async () => {
    try { await designApi.move(item.id, {to_stage: button.dataset.move, note: button.dataset.note || null}); toast('Fase atualizada.'); await changed(); }
    catch (error) { fail(error); }
  }));
  root.querySelectorAll('[data-jump]').forEach(button => button.addEventListener('click', async () => {
    if (button.dataset.jump === item.current_stage) return;
    try { await designApi.move(item.id, {to_stage: button.dataset.jump}); toast('Fase atualizada.'); await changed(); }
    catch (error) { fail(error); }
  }));
  root.querySelector('[data-retouch]')?.addEventListener('click', async () => {
    const note = window.prompt('Que retificações pediu o cliente?') || 'Cliente pediu retificações.';
    try { await designApi.move(item.id, {to_stage: 'retificacoes', note}); await changed(); } catch (error) { fail(error); }
  });
  root.querySelector('[data-reject]')?.addEventListener('click', async () => {
    const reason = window.prompt('Motivo da reprovação (opcional):') || null;
    try { await designApi.patch(item.id, {status: 'rejected', waiting_reason: reason}); toast('Amostra arquivada como reprovada.'); closeDevelopment(); onChanged?.(); }
    catch (error) { fail(error); }
  });
  root.querySelector('[data-production]')?.addEventListener('click', async () => {
    const quantity = Number(window.prompt('Quantidade da produção:', String(item.production_quantity || item.requested_quantity || 1000)));
    if (!Number.isFinite(quantity) || quantity <= 0) return;
    try {
      const result = await designApi.production(item.id, {quantity});
      toast(result.already_released ? 'Esta produção já existia.' : `Ordem ${result.order_no} criada.`);
      await changed();
    } catch (error) { fail(error); }
  });
  root.querySelector('[data-add-assignee]')?.addEventListener('click', async () => {
    const userId = root.querySelector('[data-assignee-user]').value;
    if (!userId) return;
    try { await designApi.addAssignee(item.id, {user_id: Number(userId), role: root.querySelector('[data-assignee-role]').value}); await changed(); }
    catch (error) { fail(error); }
  });
  root.querySelectorAll('[data-remove-assignee]').forEach(button => button.addEventListener('click', async () => {
    try { await designApi.removeAssignee(item.id, button.dataset.removeAssignee); await changed(); } catch (error) { fail(error); }
  }));
  root.querySelector('[data-add-task]')?.addEventListener('click', async () => {
    try {
      await designApi.addTask(item.id, {
        kind: root.querySelector('[data-task-kind]').value,
        note: root.querySelector('[data-task-note]').value || null,
        responsible_user_id: root.querySelector('[data-task-owner]').value || null,
      });
      await changed();
    } catch (error) { fail(error); }
  });
  root.querySelectorAll('[data-task-status]').forEach(select => select.addEventListener('change', async () => {
    try { await designApi.updateTask(item.id, select.dataset.taskStatus, {status: select.value}); await changed(); } catch (error) { fail(error); }
  }));
  root.querySelectorAll('[data-remove-task]').forEach(button => button.addEventListener('click', async () => {
    try { await designApi.removeTask(item.id, button.dataset.removeTask); await changed(); } catch (error) { fail(error); }
  }));
  root.querySelector('[data-save-notes]')?.addEventListener('click', async () => {
    try { await designApi.patch(item.id, {description: root.querySelector('[data-notes]').value || null}); toast('Notas guardadas.'); await changed(); }
    catch (error) { fail(error); }
  });
  root.querySelectorAll('[data-stage-note]').forEach(input => input.addEventListener('change', async () => {
    try { await designApi.stageNote(item.id, {stage: input.dataset.stageNote, note: input.value || null}); toast('Nota da fase guardada.'); }
    catch (error) { fail(error); }
  }));
  root.querySelector('[data-add-comment]')?.addEventListener('click', async () => {
    const body = root.querySelector('[data-comment]').value.trim();
    if (!body) return;
    try { await designApi.addComment(item.id, {body}); await changed(); } catch (error) { fail(error); }
  });
  root.querySelectorAll('[data-wait]').forEach(button => button.addEventListener('click', async () => {
    const reason = window.prompt('Motivo / informação:', item.waiting_reason || '') || undefined;
    try { await designApi.patch(item.id, {status: button.dataset.wait, waiting_reason: reason || null}); await changed(); }
    catch (error) { fail(error); }
  }));
  root.querySelector('[data-block]')?.addEventListener('click', async () => {
    const reason = window.prompt('Qual é o bloqueio?') || undefined;
    try { await designApi.patch(item.id, {status: 'blocked', waiting_reason: reason || null}); await changed(); }
    catch (error) { fail(error); }
  });
  root.querySelector('[data-resume]')?.addEventListener('click', async () => {
    try { await designApi.patch(item.id, {status: 'active', waiting_reason: null}); await changed(); } catch (error) { fail(error); }
  });
  root.querySelector('[data-delete-dev]')?.addEventListener('click', async () => {
    if (!window.confirm(`Eliminar definitivamente ${item.code}?`)) return;
    try { await designApi.remove(item.id); toast('Desenvolvimento eliminado.'); closeDevelopment(); onChanged?.(); }
    catch (error) { fail(error); }
  });
}
