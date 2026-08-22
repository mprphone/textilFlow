import { crudList, get, post } from '../api.js';
import { esc, money, number } from '../format.js?v=20260821-22';
import { state } from '../state.js';
import { pageHeader, toast } from '../ui.js?v=20260820-5';

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

function requestedOrderId() {
  const query = location.hash.split('?')[1] || '';
  return new URLSearchParams(query).get('order') || '';
}

export async function renderDailyProduction(container) {
  const date = container.querySelector('[name="work_date"]')?.value || todayIso();
  const preselect = requestedOrderId();
  const [data, orders, employees, lines] = await Promise.all([
    get(`/confection/${state.companyId}/daily-output?work_date=${date}`),
    crudList('production-orders', state.companyId, 'limit=500&sort=updated_at&direction=desc'),
    crudList('employees', state.companyId, 'limit=500'),
    crudList('production-lines', state.companyId, 'limit=200'),
  ]);
  const activeOrders = orders.filter(row => !['completed', 'cancelled'].includes(row.status));
  const people = employees.filter(row => row.active !== false);
  container.innerHTML = pageHeader(
    'Produção do dia',
    'Escolha a OF, a costureira e as peças. Sem este registo o sistema não sabe o que foi produzido.',
    `<a class="btn" href="#/people">Vencimentos</a><a class="btn" href="#/confection-costs">Custo por OF</a>`,
  ) + `
    ${data.missing_salary?.length ? `<div class="diary-warn">Falta vencimento em: ${data.missing_salary.map(row => esc(row.name)).join(', ')}. Sem vencimento o custo real não é calculado.</div>` : ''}
    <section class="card diary-card">
      <form class="diary-form" data-diary>
        <label>Dia<input name="work_date" type="date" value="${esc(data.date)}" required></label>
        <label>Ordem de fabrico<select name="production_order_id" required>
          <option value="">Escolher OF…</option>
          ${activeOrders.map(row => `<option value="${row.id}" ${String(row.id)===String(preselect)?'selected':''}>${esc(row.order_no)} · ${number(row.quantity)} pcs</option>`).join('')}
        </select></label>
        <label>Costureira<select name="employee_id" required>
          <option value="">Escolher pessoa…</option>
          ${people.map(row => `<option value="${row.id}" data-line="${row.line_id || ''}" data-rate="${row.hourly_cost || 0}">${esc(row.name)}${row.hourly_cost ? ` · ${money(row.hourly_cost)}/h` : ' · sem vencimento'}</option>`).join('')}
        </select></label>
        <label>Linha<select name="line_id">
          <option value="">Da costureira / OF</option>
          ${lines.map(row => `<option value="${row.id}">${esc(row.name)}</option>`).join('')}
        </select></label>
        <label>Peças boas<input name="quantity_good" type="number" min="1" step="1" required></label>
        <label>Rejeitadas<input name="quantity_rejected" type="number" min="0" step="1" value="0"></label>
        <label>Horas trabalhadas<input name="hours" type="number" min="0.25" step="0.25" value="8" required></label>
        <div class="diary-preview muted" data-preview>Custo estimado: —</div>
        <div class="form-footer"><button class="btn primary" type="submit">＋ Inserir produção</button></div>
      </form>
    </section>
    <section class="card">
      <div class="card-header"><h2>Registos de ${esc(data.date)}</h2><span>${number(data.totals.quantity_good)} pcs · ${number(data.totals.hours)} h · ${money(data.totals.labor_cost)}</span></div>
      <div class="table-wrap"><table class="data-table"><thead><tr><th>OF</th><th>Artigo</th><th>Costureira</th><th>Linha</th><th>Peças</th><th>Horas</th><th>€/h</th><th>Custo real</th></tr></thead>
      <tbody>${data.items.length ? data.items.map(row => `<tr>
        <td><b>${esc(row.order_no)}</b></td><td>${esc(row.article || '—')}</td><td>${esc(row.employee)}</td><td>${esc(row.line)}</td>
        <td>${number(row.quantity_good)}${row.quantity_rejected ? ` <small>(${number(row.quantity_rejected)} rej.)</small>` : ''}</td>
        <td>${number(row.hours)}</td><td>${money(row.hourly_cost)}</td><td><b>${money(row.labor_cost)}</b></td>
      </tr>`).join('') : '<tr><td colspan="8"><div class="empty"><strong>Ainda não há produção neste dia</strong>Preencha o formulário acima.</div></td></tr>'}</tbody></table></div>
    </section>`;
  const form = container.querySelector('[data-diary]');
  const preview = container.querySelector('[data-preview]');
  const refreshPreview = () => {
    const select = form.employee_id;
    const option = select.selectedOptions[0];
    const rate = Number(option?.dataset.rate || 0);
    const hours = Number(form.hours.value || 0);
    preview.textContent = rate ? `Custo estimado: ${hours} h × ${money(rate)} = ${money(hours * rate)}` : 'Custo estimado: indique o vencimento desta pessoa em Pessoas.';
    if (option?.dataset.line && !form.line_id.value) form.line_id.value = option.dataset.line;
  };
  form.employee_id.addEventListener('change', refreshPreview);
  form.hours.addEventListener('input', refreshPreview);
  form.work_date.addEventListener('change', () => renderDailyProduction(container));
  refreshPreview();
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const body = Object.fromEntries(new FormData(form).entries());
    try {
      const result = await post(`/confection/${state.companyId}/daily-output`, {
        work_date: body.work_date,
        production_order_id: Number(body.production_order_id),
        employee_id: Number(body.employee_id),
        line_id: body.line_id ? Number(body.line_id) : null,
        quantity_good: Number(body.quantity_good || 0),
        quantity_rejected: Number(body.quantity_rejected || 0),
        hours: Number(body.hours || 8),
      });
      toast(`Produção gravada. Custo real ${money(result.labor_cost)}.`);
      await renderDailyProduction(container);
    } catch (error) { toast(error.message, 'error'); }
  });
}
