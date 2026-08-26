import { post } from '../api.js';
import { badge, esc, number, progress } from '../format.js?v=20260826-3';
import { recordModal } from '../quick_create.js';
import { state } from '../state.js';
import { pageHeader, toast } from '../ui.js?v=20260826-3';
import { get } from '../api.js';

let startedAt = null;
let timerHandle = null;
let activeId = null;

export async function render(container) {
  const data = await get(`/production/${state.companyId}/live`);
  const assignments = data.assignments || [];
  if (!activeId || !assignments.some(row => row.id === activeId)) activeId = assignments[0]?.id || null;
  container.innerHTML = pageHeader('Terminal de produção', 'Toque na tarefa e aponte quantidades. O cronómetro preenche os minutos.') + `
    <div class="floor-terminal">
      <div class="terminal-head"><div><h1>Posto de trabalho</h1><span class="muted">Escolha a tarefa activa e confirme a produção.</span></div>${badge('online')}</div>
      <div class="floor-task-grid">${assignments.length ? assignments.map(row => `
        <button type="button" class="floor-task-card ${row.id === activeId ? 'is-active' : ''}" data-floor-task="${row.id}">
          <b>${esc(row.order_no)}</b>
          <span>${esc(row.operation)}</span>
          <small>${esc(row.employee)} · ${esc(row.machine)}</small>
        </button>`).join('') : '<div class="empty">Não existem tarefas atribuídas.</div>'}</div>
      <div id="floor-task"></div>
    </div>`;
  container.querySelectorAll('[data-floor-task]').forEach(button => button.addEventListener('click', () => {
    const next = Number(button.dataset.floorTask);
    if (next === activeId) return;
    stopTimer(container.querySelector('#floor-task'));
    activeId = next;
    render(container);
  }));
  drawTask(container, assignments.find(row => row.id === activeId));
}

function drawTask(container, task) {
  const target = document.getElementById('floor-task');
  if (!target) return;
  if (!task) { target.innerHTML = '<div class="empty">Toque numa tarefa para apontar produção.</div>'; return; }
  target.innerHTML = `<div class="terminal-grid">
    <div class="card"><div class="card-header"><h2>${esc(task.operation)}</h2>${badge(task.status)}</div>
      <p><b>${esc(task.order_no)}</b> · REF. ${esc(task.reference)}</p>
      <p class="muted">${esc(task.employee)} · ${esc(task.machine)}</p>
      ${progress(task.progress)}
      <div class="counter-grid">
        <div class="counter"><b>${number(task.planned_quantity)}</b><small>planeadas</small></div>
        <div class="counter"><b>${number(task.completed_quantity)}</b><small>boas</small></div>
        <div class="counter"><b>${number(task.rejected_quantity)}</b><small>rejeitadas</small></div>
      </div>
    </div>
    <div class="card"><div class="card-header"><h2>Novo registo</h2><span id="timer-value">00:00:00</span></div>
      <div class="floor-actions">
        <button class="btn success floor-hit" data-start>Iniciar</button>
        <button class="btn floor-hit" data-stop>Parar</button>
        <button class="btn danger floor-hit" data-downtime>Paragem</button>
      </div>
      <div class="form-grid">
        <div class="field"><label>Peças boas<input id="floor-good" type="number" min="0" inputmode="numeric" value="1"></label></div>
        <div class="field"><label>Rejeitadas<input id="floor-rejected" type="number" min="0" inputmode="numeric" value="0"></label></div>
        <div class="field"><label>Minutos<input id="floor-minutes" type="number" min="0" step="0.01" value="0"></label></div>
        <div class="field full"><label>Observações<textarea id="floor-notes"></textarea></label></div>
        <div class="form-footer"><button class="btn primary floor-hit" data-submit-output>Confirmar produção</button></div>
      </div>
    </div>
  </div>`;
  target.querySelector('[data-start]').addEventListener('click', () => startTimer(target));
  target.querySelector('[data-stop]').addEventListener('click', () => stopTimer(target));
  target.querySelector('[data-submit-output]').addEventListener('click', () => submitOutput(container, task));
  target.querySelector('[data-downtime]').addEventListener('click', () => downtimeModal(task, () => render(container)));
}

function startTimer(target) {
  if (startedAt) return;
  startedAt = Date.now();
  timerHandle = setInterval(() => {
    const timer = target.querySelector('#timer-value');
    if (!timer) { clearInterval(timerHandle); timerHandle = null; startedAt = null; return; }
    const seconds = Math.floor((Date.now() - startedAt) / 1000);
    const h = String(Math.floor(seconds / 3600)).padStart(2, '0');
    const m = String(Math.floor(seconds % 3600 / 60)).padStart(2, '0');
    const s = String(seconds % 60).padStart(2, '0');
    timer.textContent = `${h}:${m}:${s}`;
  }, 1000);
}

function stopTimer(target) {
  if (!startedAt) {
    if (timerHandle) { clearInterval(timerHandle); timerHandle = null; }
    return;
  }
  const minutes = (Date.now() - startedAt) / 60000;
  clearInterval(timerHandle); timerHandle = null; startedAt = null;
  const input = target?.querySelector?.('#floor-minutes');
  if (input) input.value = minutes.toFixed(2);
}

async function submitOutput(container, task) {
  try {
    if (startedAt) stopTimer(document.getElementById('floor-task'));
    await post('/production/events', {
      assignment_id: task.id,
      quantity_good: Number(document.getElementById('floor-good').value || 0),
      quantity_rejected: Number(document.getElementById('floor-rejected').value || 0),
      duration_minutes: Number(document.getElementById('floor-minutes').value || 0),
      event_type: 'output',
      notes: document.getElementById('floor-notes').value,
      source: 'terminal',
    });
    toast('Produção registada e indicadores atualizados.');
    await render(container);
  } catch (error) { toast(error.message, 'error'); }
}

function downtimeModal(task, onSaved) {
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
  recordModal({
    title: 'Registar paragem', resource: 'downtimes',
    values: { machine_id: task.machine_id, employee_id: task.employee_id, line_id: task.line_id, production_order_id: task.production_order_id, started_at: local },
    fields: [
      { key: 'reason_code', label: 'Código', type: 'select', required: true, options: ['MATERIAL', 'AVARIA', 'AFINACAO', 'QUALIDADE', 'PAUSA', 'OUTRO'] },
      { key: 'reason', label: 'Motivo', required: true },
      { key: 'started_at', label: 'Início', type: 'datetime-local', required: true },
      { key: 'ended_at', label: 'Fim', type: 'datetime-local' },
      { key: 'duration_minutes', label: 'Duração (min)', type: 'number', default: 0 },
      { key: 'notes', label: 'Notas', type: 'textarea', full: true },
      { key: 'machine_id', type: 'hidden' }, { key: 'employee_id', type: 'hidden' },
      { key: 'line_id', type: 'hidden' }, { key: 'production_order_id', type: 'hidden' },
    ],
    onSaved,
  });
}
