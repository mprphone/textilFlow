import { post, get } from '../api.js';
import { esc, number } from '../format.js?v=20260822-1';
import { state } from '../state.js';
import { closeModal, openModal, setHeading, toast } from '../ui.js?v=20260822-1';

let board = null;
let extraHours = false;
let selectedId = null;
let dragging = null;
let weekOffset = 0;
let view = 'week';
let query = '';
let draftShares = null;
let kind = 'sewing';

function isCut() {
  return kind === 'cutting';
}

function api(path = '') {
  if (isCut()) return `/process/${state.companyId}/cutting/map${path}`;
  return `/confection/${state.companyId}/production-map${path}`;
}

const statusLabel = {
  in_progress: 'A produzir', planned: 'No plano', released: 'Libertada',
  paused: 'Em pausa', backlog: 'Por planear',
};

function lines() {
  return board.lines || [];
}

function contractors() {
  return board.contractors || [];
}

function lineLabel(key) {
  return lines().find(row => row.key === key)?.name || key || '—';
}

function matches(row) {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  return `${row.code} ${row.article} ${row.client} ${row.supplier_name || ''}`.toLowerCase().includes(q);
}

function pending() {
  return (board.backlog || []).concat(board.scheduled || []).filter(row => row.allocation_type !== 'external' && (!row.work_days || !row.work_days.length)).filter(matches);
}

function onLine() {
  return (board.scheduled || []).filter(row => row.allocation_type !== 'external' && (row.work_days || []).length).filter(matches);
}

function outside() {
  return [...(board.scheduled || []), ...(board.backlog || [])].filter(row => row.allocation_type === 'external').filter(matches);
}

function visibleDays() {
  const all = board.workdays || [];
  const today = all.findIndex(row => row.is_today);
  const monday = today < 0 ? 0 : today - (today % 5);
  const start = Math.max(0, monday + weekOffset * 5);
  return all.slice(start, start + (view === 'month' ? 20 : 5));
}

function covers(row, dateStr) {
  return (row.work_days || []).includes(dateStr);
}

function fmt(dateStr) {
  if (!dateStr) return '—';
  const parts = String(dateStr).split('-');
  return `${parts[2]}/${parts[1]}`;
}

function dueDays(row) {
  if (row.due_in_days != null && row.due_in_days !== '') return Number(row.due_in_days);
  const raw = row.promised_date;
  if (!raw) return null;
  const end = new Date(`${String(raw).slice(0, 10)}T12:00:00`);
  const today = new Date();
  today.setHours(12, 0, 0, 0);
  return Math.round((end - today) / 86400000);
}

function dueTone(row) {
  const days = dueDays(row);
  if (days == null) return 'none';
  if (days <= 7) return 'near';
  if (days <= 21) return 'mid';
  return 'far';
}

function dueLabel(row) {
  const days = dueDays(row);
  if (!row.promised_date) return 'Sem data de entrega';
  if (days == null) return `Entrega ${fmt(row.promised_date)}`;
  if (days < 0) return `Entrega ${fmt(row.promised_date)} · atrasada ${Math.abs(days)} d`;
  if (days === 0) return `Entrega hoje · ${fmt(row.promised_date)}`;
  return `Entrega ${fmt(row.promised_date)} · ${days} d`;
}

function orderPaint(row) {
  const palettes = [
    ['#e8f1ff', '#70a2e8', '#173d70', '#2f6fc2'],
    ['#e7f7ee', '#71c092', '#1c4c32', '#24915b'],
    ['#f2ebff', '#a98be3', '#422a6d', '#7650bc'],
    ['#fff0e6', '#ea9a66', '#63331b', '#cf6b2f'],
    ['#e5f7f7', '#63bdbb', '#174a49', '#168b88'],
    ['#fdebf2', '#e58eae', '#64263f', '#c04b76'],
    ['#fff6d9', '#ddb84f', '#57430f', '#b68400'],
    ['#eaeefe', '#8291da', '#2d376b', '#5265ba'],
    ['#eef7dc', '#9dbd56', '#3c5118', '#71952a'],
    ['#e8f6fd', '#6eb9db', '#17475d', '#2689b1'],
    ['#f9e9fd', '#d086dd', '#5a2865', '#aa4fba'],
    ['#fce9e6', '#df8378', '#642821', '#b94a3e'],
  ];
  const orderKey = item => String(item.order_id ?? item.production_order_id ?? item.code ?? item.id ?? '');
  const keys = [...new Set([...(board?.backlog || []), ...(board?.scheduled || [])].map(orderKey))]
    .sort((left, right) => left.localeCompare(right, 'pt', { numeric: true }));
  const index = Math.max(0, keys.indexOf(orderKey(row)));
  const [bg, bd, fg, accent] = palettes[index % palettes.length];
  return `--order-accent:${accent};background:${bg};border-color:${bd};color:${fg}`;
}

function waitingStockHint() {
  const rows = [...pending(), ...onLine()].filter(row => row.order_id && row.fabric_ready === false);
  if (!rows.length) return 'Cada cor identifica uma OF e mantém-se igual em todos os dias.';
  return `${rows.length} OF${rows.length > 1 ? 's' : ''} no plano sem malha em stock. Cada cor identifica uma OF.`;
}

function kindLabel(row) {
  if (row.allocation_type === 'external') return isCut() ? 'Corte fora' : 'Mandada para fora';
  if (!isCut() && row.source_type === 'third_party') return 'Feitio';
  if (row.fabric_ready === false) return isCut() ? 'Corte · sem malha' : 'Confeção · sem malha';
  return isCut() ? 'Corte interno' : 'Nossa produção';
}

function sharesOf(row) {
  if (draftShares && selectedId === row.id) return { ...draftShares };
  const days = [...(row.work_days || [])].sort();
  const stored = row.day_share || {};
  if (days.some(day => Number(stored[day]) > 0)) {
    return Object.fromEntries(days.map(day => [day, Number(stored[day] || 0)]));
  }
  const hours = Number(row.hours) || 0;
  const cap = Number(row.hours_day) || 8;
  const chunk = hours ? Math.min(100, cap / hours * 100) : 0;
  const shares = {};
  let left = 100;
  days.forEach(day => {
    const take = Math.min(chunk, left);
    shares[day] = Math.round(take * 10) / 10;
    left = Math.round((left - take) * 10) / 10;
  });
  return shares;
}

function lineLoad(lineKey, dateStr) {
  const line = lines().find(row => row.key === lineKey);
  const cap = Number(line?.hours_day) || 8;
  const hours = onLine().filter(row => row.line_key === lineKey && covers(row, dateStr)).reduce((sum, row) => {
    const pct = Number(sharesOf(row)[dateStr] || 0);
    return sum + (Number(row.hours) || 0) * pct / 100;
  }, 0);
  return cap ? hours / cap * 100 : 0;
}

function weekdayName(dateStr) {
  return (board.workdays || []).find(row => row.date === dateStr)?.weekday || '';
}

function findOrder(id) {
  return [...pending(), ...onLine(), ...outside()].find(item => item.id === id);
}

function askFabricQty(row, {force = false} = {}) {
  return new Promise(resolve => {
    if (!isCut()) {
      resolve(null);
      return;
    }
    if (!force && (row?.work_days || []).length) {
      resolve(null);
      return;
    }
    const unit = row?.fabric_unit || 'kg';
    const ready = row?.fabric_ready !== false || !row?.order_id;
    const missing = Number(row?.fabric_missing || 0);
    const covered = Number(row?.fabric_covered || 0);
    const needed = Number(row?.fabric_needed || 0);
    const issued = Number(row?.fabric_issued || 0);
    const alerts = [];
    if (row?.order_id && missing > 0.001) {
      alerts.push('Sem stock: a OF vai para o plano na mesma. Quando a malha der entrada, aparece o alerta para a saída.');
    }
    if (row?.order_id && needed > 0 && covered + 1e-6 < needed) {
      alerts.push(`A OF precisa de ${number(needed)} ${unit} e só há ${number(covered)} ${unit} em armazém.`);
    }
    if (!row?.order_id) {
      alerts.push('Esta OF de corte não está ligada a uma encomenda. A saída de malha só se cria com OF de produção.');
    }
    if (issued > 0) {
      alerts.push(`Já saíram ${number(issued)} ${unit} para corte. Esta quantidade gera um novo documento de saída.`);
    }
    const alertHtml = alerts.length
      ? `<div class="field full">${alerts.map(text => `<p class="dossier-alert ${missing > 0.001 ? 'warn' : ''}">${esc(text)}</p>`).join('')}</div>`
      : `<p class="field full muted">Com stock cria-se o documento interno de saída (SAI). Sem stock a OF fica planeada à mesma.</p>`;
    openModal(
      ready ? 'Saída de malha para o corte' : 'Planear corte sem malha em stock',
      `<form class="form-grid" data-fabric-form>
        ${alertHtml}
        <p class="field full">${esc(row?.fabric_label || 'Quantidade prevista para o corte.')}</p>
        <label class="field"><span>Quantidade ${ready ? 'desta saída' : 'prevista'} (${esc(unit)})</span>
          <input name="qty" type="number" min="0" step="0.01" value="${needed || ''}" ${ready ? 'required' : ''}>
        </label>
        <div class="form-footer"><button type="button" class="btn" data-close-modal>Cancelar</button>
        <button class="btn primary" type="submit">${ready ? 'Criar saída e planear' : 'Planear à mesma'}</button></div>
      </form>`,
      ready ? 'O documento SAI fica no TextileFlow (interno).' : 'A malha em falta fica visível no plano. O alerta sai na entrada de stock.',
    );
    document.querySelector('[data-close-modal]')?.addEventListener('click', () => { closeModal(); resolve(false); });
    document.querySelector('[data-fabric-form]')?.addEventListener('submit', event => {
      event.preventDefault();
      const qty = Number(new FormData(event.target).get('qty') || 0);
      closeModal();
      resolve(qty);
    });
  });
}

function focusOrder(container, id) {
  selectedId = id;
  draftShares = null;
  const row = findOrder(id);
  const first = (row?.work_days || [])[0];
  const all = board.workdays || [];
  if (first && all.length) {
    const today = all.findIndex(item => item.is_today);
    const monday = today < 0 ? 0 : today - (today % 5);
    const index = all.findIndex(item => item.date === first);
    if (index >= 0) {
      weekOffset = Math.floor((index - monday) / 5);
      if (view === 'month') weekOffset = Math.floor(weekOffset / 4) * 4;
    }
  }
  draw(container);
  if (row) openAdjustBox(container, row);
}

function timeLabel(row) {
  const hours = number(row.hours);
  const need = row.days_needed || 1;
  const done = (row.work_days || []).length;
  const planned = Object.values(sharesOf(row)).reduce((sum, value) => sum + Number(value || 0), 0);
  return `${number(row.quantity)} pcs · ${hours} h · ${Math.round(planned)}% planeada · ${done}/${need} dias`;
}

export async function renderProductionMap(container, nextKind = 'sewing') {
  kind = nextKind === 'cutting' ? 'cutting' : 'sewing';
  extraHours = false;
  selectedId = null;
  draftShares = null;
  weekOffset = 0;
  view = 'week';
  query = '';
  setHeading(isCut() ? 'Plano do corte' : 'Plano da confeção', isCut() ? 'Peças, tempo e mesa' : 'Peças, tempo e onde se faz');
  container.innerHTML = '<div class="loading">A carregar o plano…</div>';
  await reload(container);
}

async function reload(container, nextBoard = null) {
  board = nextBoard || await get(`${api()}?extra_hours=${extraHours}&weeks=12`);
  extraHours = Boolean(board.extra_hours);
  if (board.audit_message) toast(board.audit_message);
  draw(container);
}

function draw(container) {
  const days = visibleDays();
  const selected = [...pending(), ...onLine(), ...outside()].find(row => row.id === selectedId);
  const range = days[0] && days.at(-1) ? `${fmt(days[0].date)} – ${fmt(days.at(-1).date)}` : '';
  container.innerHTML = `
    <div class="pmap-shell pmap-simple">
      <div class="pmap-crumb">
        <div>
          <h1>${isCut() ? 'Plano do corte' : 'Plano da confeção'}</h1>
          <small>${isCut() ? 'Nas mesas: corte interno. Em baixo: o que mandamos cortar fora.' : 'Nas linhas: produção nossa ou feitio para um cliente. Para baixo: só o que mandamos costurar fora.'}</small>
        </div>
        <div class="pmap-weeknav">
          <button class="btn small" data-step="-1">←</button>
          <strong>${view === 'month' ? 'Mês' : 'Semana'} ${days[0]?.iso_week || ''} · ${range}</strong>
          <button class="btn small" data-step="1">→</button>
        </div>
      </div>
      <div class="pmap-toolbar">
        <div class="pmap-views">
          <button data-view="week" class="${view==='week'?'active':''}">Semana</button>
          <button data-view="month" class="${view==='month'?'active':''}">Mês</button>
        </div>
        <input class="pmap-search" data-query placeholder="Procurar OF, cliente ou artigo…" value="${esc(query)}">
        <span class="pmap-color-key" title="A mesma OF mantém a mesma cor em todo o mapa"><i></i><i></i><i></i>Cada cor = uma OF</span>
        <button class="btn" data-add>+ Nova OF</button>
        <a class="btn primary" href="${isCut() ? '#/cutting' : '#/confection-diary'}">${isCut() ? '＋ Estendimentos' : '＋ Produção do dia'}</a>
        ${!isCut() ? '<button class="btn small" data-kanban-toggle>Kanban corte→costura</button>' : ''}
      </div>
      ${!isCut() ? '<div class="kanban-panel" data-kanban-panel></div>' : ''}
      <div class="pmap-simple-grid">
        ${pendingCol()}
        <div class="pmap-main">
          ${weekBoard(days)}
          ${outsideCol()}
        </div>
      </div>
      ${selected ? `<p class="pmap-hintline">${esc(selected.code)} · ${esc(dueLabel(selected))} · clique outra vez se fechou a caixa.</p>` : `<p class="pmap-hintline">${waitingStockHint()} Clique numa OF para abrir a caixa e arrastar os dias.</p>`}
    </div>`;
  bind(container);
}

function pendingCol() {
  const rows = pending();
  return `<aside class="pmap-col">
    <header class="pmap-col-head"><h2>Por planear</h2><span>${rows.length}</span></header>
    <p class="pmap-help">${isCut() ? 'Pode largar no plano mesmo sem malha: a OF fica marcada. O alerta sai quando der entrada de stock.' : 'Pode planear a confeção à mesma. A falta de malha fica visível no cartão.'}</p>
    <div class="pmap-backlog-list">${rows.map(cardMarkup).join('') || '<div class="empty"><strong>Tudo no plano</strong></div>'}</div>
  </aside>`;
}

function cardMarkup(row) {
  return `<article class="pmap-card due-${dueTone(row)} ${row.id===selectedId?'selected':''} ${row.fabric_ready===false?'no-stock':''}" draggable="true" data-backlog="${row.id}" style="${orderPaint(row)}">
    <b>${esc(row.code)}</b>
    <small class="pmap-kind">${esc(kindLabel(row))}</small>
    <small>${esc(row.client)}</small>
    <small>${esc(row.article)}</small>
    <small class="pmap-due">${esc(dueLabel(row))}</small>
    ${row.fabric_label ? `<small class="pmap-due">${esc(row.fabric_label)}</small>` : ''}
    <small class="pmap-time">${timeLabel(row)}</small>
    <button class="pmap-fit" data-fit="${row.id}">Preencher dias livres</button>
  </article>`;
}

function weekBoard(days) {
  const weeks = [];
  for (let i = 0; i < days.length; i += 5) weeks.push(days.slice(i, i + 5));
  return `<section class="pmap-col pmap-center">
    ${weeks.map((chunk, index) => `<div class="pmap-board" style="--days:${Math.max(chunk.length,1)}">
      <div class="pmap-board-head"><span>${index === 0 ? (isCut() ? 'Mesas' : 'Casa') : ''}</span>${chunk.map(day => `<span class="${day.is_today?'today':''}">${day.is_today?'<i>hoje</i>':''}<b>${esc(day.weekday)}</b>${esc(day.day)}</span>`).join('')}</div>
      ${lines().map(line => lineRow(line, chunk)).join('') || `<div class="empty"><strong>${isCut() ? 'Sem mesas' : 'Sem linhas'}</strong>${isCut() ? 'Cadastre máquinas de corte ou linhas do departamento Corte.' : ''}</div>`}
    </div>`).join('')}
  </section>`;
}

function lineRow(line, days) {
  return `<div class="pmap-board-row">
    <div class="pmap-line ${line.color}"><b>${esc(line.name)}</b></div>
    ${days.map(day => {
      const ops = onLine().filter(row => row.line_key === line.key && covers(row, day.date));
      return `<div class="pmap-slot ${day.is_today?'today':''}" data-line="${esc(line.key)}" data-date="${day.date}">
        ${ops.map(row => chipMarkup(row, day.date)).join('') || '<span class="pmap-slot-empty">Largar dia</span>'}
      </div>`;
    }).join('')}
  </div>`;
}

function chipMarkup(row, day) {
  const left = row.days_left || 0;
  const ofPct = Number(sharesOf(row)[day] || 0);
  const load = lineLoad(row.line_key, day);
  return `<button class="pmap-chip due-${dueTone(row)} ${row.id===selectedId?'selected':''} ${selectedId && row.id!==selectedId?'ghost':''} ${left?'wait':''} ${row.fabric_ready===false?'no-stock':''}" draggable="true" data-block="${row.id}" data-from="${day}" style="${orderPaint(row)}">
    <b>${esc(row.code)}</b>
    <span>${esc(row.client)}</span>
    <em>${esc(dueLabel(row))}</em>
    <em>${number(ofPct)}% desta OF · ${isCut() ? 'mesa' : 'linha'} ${number(load)}%</em>
    <i data-icon="delete" data-remove-day="${row.id}" data-day="${day}" role="button" aria-label="Retirar deste dia" title="Retirar deste dia"></i>
  </button>`;
}

function outsideCol() {
  const rows = outside();
  const partners = contractors();
  return `<section class="pmap-col pmap-out">
    <header class="pmap-col-head"><h2>${isCut() ? 'Mandar cortar fora' : 'Mandar costurar fora'}</h2><span>${rows.length}</span></header>
    <p class="pmap-help">${isCut() ? 'Aqui só o corte que a fábrica envia a um subcontratado. O corte interno fica nas mesas de cima.' : 'Isto não é feitio. Feitio fica nas linhas de cima. Aqui só o serviço que a nossa fábrica envia a um confeçionador.'}</p>
    <div class="pmap-partners">${partners.map(partner => {
      const here = rows.filter(row => row.supplier_id === partner.id);
      return `<div class="pmap-partner" data-supplier="${partner.id}">
        <b>${esc(partner.name)}</b>
        <small>${number(partner.weekly_capacity)} pcs/semana · ${number(partner.piece_cost)} €/peça · ${number(partner.lead_time_days)} dias</small>
        ${here.map(row => `<button class="pmap-chip due-${dueTone(row)} ${row.id===selectedId?'selected':''}" data-block="${row.id}" style="${orderPaint(row)}"><b>${esc(row.code)}</b><span>${esc(dueLabel(row))}</span></button>`).join('') || '<span class="pmap-slot-empty">Largar aqui para subcontratar</span>'}
      </div>`;
    }).join('') || `<div class="empty"><strong>${isCut() ? 'Sem cortadores externos' : 'Sem confeçionadores'}</strong>${isCut() ? 'Cadastre um fornecedor de corte para largar OFs aqui.' : 'Crie-os em Configurar a fábrica.'}</div>`}</div>
  </section>`;
}

function boxDays(row) {
  const all = board.workdays || [];
  const planned = [...(row.work_days || [])].sort();
  const first = planned[0] || all.find(item => item.is_today)?.date;
  const last = planned.at(-1);
  const startIdx = Math.max(0, all.findIndex(item => item.date === first));
  const monday = Math.max(0, startIdx - (startIdx % 5));
  let count = 15;
  if (last) {
    const endIdx = all.findIndex(item => item.date === last);
    if (endIdx >= monday) count = Math.max(15, Math.ceil((endIdx - monday + 1) / 5) * 5);
  }
  return all.slice(monday, monday + count);
}

function openAdjustBox(container, row) {
  const external = row.allocation_type === 'external';
  const shares = sharesOf(row);
  const total = Object.values(shares).reduce((sum, value) => sum + Number(value || 0), 0);
  const days = boxDays(row);
  openModal(
    row.code,
    `<div class="pmap-box" data-adjust-box>
      <p><b>${esc(row.client)}</b> · ${esc(row.article)} · ${esc(kindLabel(row))}<br>${esc(dueLabel(row))}<br>${esc(timeLabel(row))}</p>
      ${external ? '<p class="muted">Esta OF está fora. Volte a por planear para a meter numa linha.</p>' : `
      <p class="muted">Arraste um dia para outro quadrado da ${esc(lineLabel(row.line_key))}. O % é a parte desta encomenda nesse dia.</p>
      ${(() => {
        const weeks = [];
        for (let i = 0; i < days.length; i += 5) weeks.push(days.slice(i, i + 5));
        return weeks.map(chunk => `<div class="pmap-box-week">
          <div class="pmap-box-head" style="--days:${chunk.length}">${chunk.map(day => `<span class="${day.is_today?'today':''}"><b>${esc(day.weekday)}</b>${esc(day.day)}</span>`).join('')}</div>
          <div class="pmap-box-row" style="--days:${chunk.length}">${chunk.map(day => {
            const pct = Number(shares[day.date] || 0);
            const load = lineLoad(row.line_key, day.date);
            return `<div class="pmap-box-slot ${day.is_today?'today':''}" data-box-date="${day.date}">
              ${pct ? `<button type="button" class="pmap-chip" draggable="true" data-plan-day="${day.date}" style="${orderPaint(row)}"><b>${number(pct)}%</b><span>${number(row.hours * pct / 100)} h</span><em>${isCut() ? 'mesa' : 'linha'} ${number(load)}%</em></button>` : `<span class="pmap-slot-empty">Largar aqui</span>`}
            </div>`;
          }).join('')}</div>
        </div>`).join('');
      })()}
      <div class="form-footer">
        <strong class="${Math.abs(total-100)<0.6?'ok':'warn'}">${number(total)}% da encomenda</strong>
        <button type="button" class="btn" data-close-modal>Fechar</button>
        <button type="button" class="btn" data-box-equal>Repartir igual</button>
        <button type="button" class="btn primary" data-box-save>Guardar</button>
      </div>`}
    </div>`,
    dueLabel(row),
  );
  document.querySelector('[data-close-modal]')?.addEventListener('click', closeModal);
  if (external) return;
  let moving = null;
  document.querySelectorAll('[data-plan-day]').forEach(chip => {
    chip.addEventListener('dragstart', event => {
      moving = chip.dataset.planDay;
      event.dataTransfer.effectAllowed = 'move';
      event.dataTransfer.setData('text/plain', moving);
    });
  });
  document.querySelectorAll('[data-box-date]').forEach(slot => {
    slot.addEventListener('dragover', event => { event.preventDefault(); slot.classList.add('drop'); });
    slot.addEventListener('dragleave', () => slot.classList.remove('drop'));
    slot.addEventListener('drop', event => {
      event.preventDefault();
      slot.classList.remove('drop');
      const from = moving || event.dataTransfer.getData('text/plain');
      const to = slot.dataset.boxDate;
      moving = null;
      if (!from || from === to) return;
      const current = sharesOf(row);
      const amount = Number(current[from] || 0);
      if (!amount) return;
      current[to] = Number(current[to] || 0) + amount;
      delete current[from];
      draftShares = current;
      selectedId = row.id;
      openAdjustBox(container, { ...row, work_days: Object.keys(current), day_share: current });
    });
  });
  document.querySelector('[data-box-equal]')?.addEventListener('click', () => {
    const keys = Object.keys(sharesOf(row)).filter(day => Number(sharesOf(row)[day]) > 0);
    if (!keys.length) return;
    const each = Math.round(1000 / keys.length) / 10;
    draftShares = Object.fromEntries(keys.map((day, index) => [day, index === keys.length - 1 ? Math.round((100 - each * (keys.length - 1)) * 10) / 10 : each]));
    openAdjustBox(container, { ...row, work_days: keys, day_share: draftShares });
  });
  document.querySelector('[data-box-save]')?.addEventListener('click', async () => {
    const shares = draftShares || sharesOf(row);
    try {
      closeModal();
      await reload(container, await post(api('/move'), {
        plan_id: row.id, line_key: row.line_key, action: 'shares', extra_hours: extraHours, day_shares: shares,
      }));
      draftShares = null;
    } catch (error) { toast(error.message, 'error'); }
  });
}

function bind(container) {
  container.querySelectorAll('[data-view]').forEach(button => button.addEventListener('click', () => { view = button.dataset.view; weekOffset = 0; draw(container); }));
  container.querySelectorAll('[data-step]').forEach(button => button.addEventListener('click', () => {
    weekOffset += Number(button.dataset.step) * (view === 'month' ? 4 : 1);
    draw(container);
  }));
  const search = container.querySelector('[data-query]');
  search?.addEventListener('keydown', event => { if (event.key === 'Enter') { query = event.target.value; draw(container); } });
  search?.addEventListener('change', event => { query = event.target.value; draw(container); });
  container.querySelector('[data-add]')?.addEventListener('click', () => addModal(container));
  container.querySelectorAll('[data-fit]').forEach(button => button.addEventListener('click', async event => {
    event.stopPropagation();
    const row = findOrder(Number(button.dataset.fit));
    const qty = await askFabricQty(row, {force: true});
    if (qty === false) return;
    try { await reload(container, await post(api('/one-click'), {plan_id: Number(button.dataset.fit), extra_hours: extraHours, fabric_quantity: qty})); }
    catch (error) { toast(error.message, 'error'); }
  }));
  container.querySelectorAll('[data-block]').forEach(button => {
    button.addEventListener('click', event => {
      if (event.target.closest('[data-remove-day]')) return;
      focusOrder(container, Number(button.dataset.block));
    });
    button.addEventListener('dragstart', event => startDrag(event, {id: Number(button.dataset.block), from: button.dataset.from || null}));
  });
  container.querySelectorAll('[data-backlog]').forEach(card => {
    card.addEventListener('click', () => focusOrder(container, Number(card.dataset.backlog)));
    card.addEventListener('dragstart', event => startDrag(event, {id: Number(card.dataset.backlog), from: null}));
  });
  container.querySelectorAll('[data-remove-day]').forEach(button => button.addEventListener('click', async event => {
    event.preventDefault();
    event.stopPropagation();
    try {
      await reload(container, await post(api('/move'), {
        plan_id: Number(button.dataset.removeDay), start_date: button.dataset.day, action: 'remove', extra_hours: extraHours,
      }));
    } catch (error) { toast(error.message, 'error'); }
  }));
  container.querySelectorAll('[data-date]').forEach(cell => {
    cell.addEventListener('dragover', event => { event.preventDefault(); cell.classList.add('drop'); });
    cell.addEventListener('dragleave', () => cell.classList.remove('drop'));
    cell.addEventListener('drop', event => onDrop(event, cell, container));
  });
  container.querySelectorAll('[data-supplier]').forEach(cell => {
    cell.addEventListener('dragover', event => { event.preventDefault(); cell.classList.add('drop'); });
    cell.addEventListener('dragleave', () => cell.classList.remove('drop'));
    cell.addEventListener('drop', async event => {
      event.preventDefault();
      cell.classList.remove('drop');
      const payload = dragging || JSON.parse(event.dataTransfer.getData('text/plain') || '{}');
      dragging = null;
      if (!payload?.id) return;
      const row = findOrder(payload.id);
      const qty = await askFabricQty(row, {force: true});
      if (qty === false) return;
      try {
        selectedId = payload.id;
        await reload(container, await post(api('/move'), {
          plan_id: payload.id, supplier_id: Number(cell.dataset.supplier), extra_hours: extraHours, fabric_quantity: qty,
        }));
      } catch (error) { toast(error.message, 'error'); }
    });
  });
  if (!isCut()) loadKanbanPanel(container);
}

async function loadKanbanPanel(container) {
  const panel = container.querySelector('[data-kanban-panel]');
  if (!panel) return;
  panel.style.display = panel.dataset.open === 'true' ? 'block' : 'none';
  container.querySelector('[data-kanban-toggle]')?.addEventListener('click', () => {
    panel.dataset.open = panel.dataset.open === 'true' ? 'false' : 'true';
    panel.style.display = panel.dataset.open === 'true' ? 'block' : 'none';
    if (panel.dataset.open === 'true') loadKanbanPanel(container);
  });
  if (panel.dataset.open !== 'true') return;
  try {
    const board = await get(`/production/${state.companyId}/kanban`);
    const columns = (board.lines || []).map(line => `
      <div class="kanban-col ${line.can_pull ? '' : 'full'}">
        <header><b>${esc(line.line_name)}</b><small>WIP ${line.wip}/${line.wip_limit || '∞'}</small></header>
        <div class="kanban-pulled">
          ${line.pulled.map(row => `<div class="kanban-card ${esc(row.status)}"><b>${esc(row.batch_no)}</b><span>${number(row.quantity)} un. · ${esc(row.status)}${row.status === 'pulled' ? ` <button class="btn xsmall" data-kanban-release="${row.id}" data-line-id="${line.line_id}">Liberar</button>` : ''}</span></div>`).join('') || '<span class="muted">Vazio</span>'}
        </div>
        <div class="kanban-waiting">
          ${line.waiting.slice(0, 3).map(row => `<div class="kanban-card waiting"><b>${esc(row.batch_no)}</b><span>${number(row.quantity)} un.</span></div>`).join('') || '<span class="muted">Sem lotes à espera</span>'}
        </div>
        <button class="btn small ${line.can_pull ? '' : 'disabled'}" data-kanban-pull="${line.line_id}">${line.can_pull ? 'Puxar próximo lote' : 'WIP limit atingido'}</button>
      </div>
    `).join('');
    panel.innerHTML = `
      <div class="kanban-board">
        <div class="kanban-cols">${columns}</div>
        <div class="kanban-pool">
          <h4>Pool de lotes cortados</h4>
          ${(board.waiting_pool || []).slice(0, 10).map(row => `<div class="kanban-card"><b>${esc(row.batch_no)}</b><span>${number(row.quantity)} un. · OF ${row.order_id}</span></div>`).join('') || '<span class="muted">Sem lotes no pool</span>'}
        </div>
      </div>`;
    panel.querySelectorAll('[data-kanban-pull]').forEach(button => button.addEventListener('click', async event => {
      try {
        await post(`/production/${state.companyId}/kanban/pull/${button.dataset.kanbanPull}`, {});
        toast('Lote puxado para a linha');
        loadKanbanPanel(container);
      } catch (error) { toast(error.message, 'error'); }
    }));
    panel.querySelectorAll('[data-kanban-release]').forEach(button => button.addEventListener('click', async event => {
      event.stopPropagation();
      try {
        await post(`/production/${state.companyId}/kanban/release/${button.dataset.kanbanRelease}`, { line_id: Number(button.dataset.lineId) });
        toast('Lote libertado para costura · atribuições criadas');
        loadKanbanPanel(container);
      } catch (error) { toast(error.message, 'error'); }
    }));
  } catch (error) { panel.innerHTML = `<p class="muted">Kanban indisponível: ${esc(error.message)}</p>`; }
}

function startDrag(event, payload) {
  dragging = payload;
  event.dataTransfer.effectAllowed = 'move';
  event.dataTransfer.setData('text/plain', JSON.stringify(payload));
}

async function onDrop(event, cell, container) {
  event.preventDefault();
  cell.classList.remove('drop');
  const payload = dragging || JSON.parse(event.dataTransfer.getData('text/plain') || '{}');
  dragging = null;
  if (!payload?.id) return;
  const row = findOrder(payload.id);
  const qty = await askFabricQty(row, {force: !payload.from});
  if (qty === false) return;
  try {
    selectedId = payload.id;
    await reload(container, await post(api('/move'), {
      plan_id: payload.id,
      line_key: cell.dataset.line,
      start_date: cell.dataset.date,
      from_date: payload.from || null,
      action: payload.from ? 'move' : 'add',
      extra_hours: extraHours,
      fabric_quantity: qty,
    }));
  } catch (error) { toast(error.message, 'error'); }
}

function addModal(container) {
  const source = isCut() ? '' : `<label class="field full"><span>Que trabalho é este?</span>
      <select name="source_type">
        <option value="confirmed">Produção nossa (artigo da casa)</option>
        <option value="third_party">Trabalho a feitio (cliente traz o serviço; confeção aqui)</option>
      </select>
    </label>`;
  openModal('Nova OF para planear', `<form class="form-grid" data-map-form>
    ${source}
    <label class="field"><span>Cliente</span><input name="client" value="ZARA PORTUGAL" required></label>
    <label class="field"><span>Artigo</span><input name="article" value="T-Shirt" required></label>
    <label class="field"><span>Quantidade</span><input name="quantity" type="number" min="1" value="1200" required></label>
    <label class="field"><span>Minutos por peça</span><input name="sam_minutes" type="number" step="0.1" min="0.1" value="${isCut() ? '2.5' : '14.5'}" required></label>
    <label class="field"><span>Data de entrega</span><input name="promised_date" type="date"></label>
    <p class="field full muted">O tempo total = quantidade × minutos por peça. A cor no mapa segue a entrega: laranja perto, amarelo a meio, verde com folga.</p>
    <div class="form-footer"><button type="button" class="btn" data-close-modal>Cancelar</button><button class="btn primary" type="submit">Guardar em por planear</button></div>
  </form>`, isCut() ? 'O corte interno fica nas mesas. Só manda para fora o que não se corta aqui.' : 'Feitio e produção nossa ficam nas linhas. Só manda para o confeçionador o que não se costura aqui.');
  const form = document.querySelector('[data-map-form]');
  document.querySelector('[data-close-modal]')?.addEventListener('click', closeModal);
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(form).entries());
    try {
      closeModal();
      await reload(container, await post(api('/backlog'), {
        ...data, quantity: Number(data.quantity), sam_minutes: Number(data.sam_minutes), extra_hours: extraHours,
      }));
    } catch (error) { toast(error.message, 'error'); }
  });
}
