import { get, post } from '../api.js';
import { badge, esc, money, number, progress } from '../format.js?v=20260826-3';
import { state } from '../state.js';
import { closeModal, openModal, pageHeader, toast } from '../ui.js?v=20260826-3';
import { categoryLabel, categoryOptions, statusText, todayIso } from './shared.js?v=20260826-3';
import { renderProposalDetail } from './proposals.js?v=20260826-4';

function variance(value) {
  const numberValue = Number(value || 0);
  return `<span class="variance ${numberValue > 0 ? 'bad' : numberValue < 0 ? 'good' : ''}">${numberValue > 0 ? '+' : ''}${money(numberValue)}</span>`;
}

function editableProposal(order, proposals) {
  return proposals
    .filter(row => Number(row.style_id) === Number(order.style_id) && ['draft','rejected','obsolete'].includes(row.status))
    .sort((left, right) => Number(right.version || 0) - Number(left.version || 0))[0] || null;
}

function controlRows(rows, proposals) {
  return rows.length ? rows.map(({order, baseline, metrics}) => {
    const proposal = baseline ? null : editableProposal(order, proposals);
    return `
    <tr>
      <td><button class="link-button" data-control="${order.id}">${esc(order.order_no)}</button></td>
      <td><b>${esc(order.style_reference)}</b><small class="cost-subline">${esc(order.style_description)}</small></td>
      <td>${number(order.quantity)}</td>
      <td>${progress(metrics.progress_pct || 0, (metrics.deviation_pct || 0) > 5 ? 'red' : 'green')}</td>
      <td>${baseline ? `${esc(baseline.quote_no)} · V${baseline.version}` : proposal ? `<button class="link-button" data-edit-proposal="${proposal.id}" data-proposal-status="${esc(proposal.status)}">${esc(proposal.quote_no)} · ${['rejected','obsolete'].includes(proposal.status) ? 'Recusada — rever' : 'Em edição'}</button>` : '<span class="badge red">Sem proposta aprovada</span>'}</td>
      <td>${money(metrics.earned_budget || 0)}</td>
      <td>${money(metrics.actual_total || 0)}</td>
      <td>${baseline ? variance(metrics.deviation) : '—'}</td>
      <td>${baseline ? badge(statusText(metrics.status)) : badge('Por configurar')}</td>
      <td><div class="row-actions">${proposal ? `<button class="btn small" data-edit-proposal="${proposal.id}" data-proposal-status="${esc(proposal.status)}"><span data-icon="edit" aria-hidden="true"></span> Editar proposta</button>` : ''}<button class="btn small" data-control="${order.id}">Analisar</button></div></td>
    </tr>`;
  }).join('') : `<tr><td colspan="10"><div class="empty"><strong>Sem ordens de fabrico</strong>Quando existir produção, o controlo aparecerá aqui.</div></td></tr>`;
}

function openActualCost(container, orderId) {
  openModal('Registar custo real', `
    <form id="actual-cost-form" class="form-grid">
      <div class="form-section">Documento / custo ocorrido</div>
      <div class="field"><label>Tipo *<select name="category" required>${categoryOptions('subcontract')}</select></label></div>
      <div class="field"><label>Data *<input name="occurred_on" type="date" value="${todayIso()}" required></label></div>
      <div class="field"><label>Referência<input name="reference" placeholder="Fatura, recibo, documento…"></label></div>
      <div class="field full"><label>Descrição *<input name="description" placeholder="Ex.: Bordado – Fatura FT 2026/123" required></label></div>
      <div class="field"><label>Quantidade *<input name="quantity" type="number" min="0" step="any" value="1" required></label></div>
      <div class="field"><label>Unidade *<input name="unit" value="un" required></label></div>
      <div class="field"><label>Custo unitário *<input name="unit_cost" type="number" min="0" step="any" value="0" required></label></div>
      <div class="field full"><label>Notas<textarea name="notes"></textarea></label></div>
      <div class="form-footer"><button type="button" class="btn" data-close-modal>Cancelar</button><button class="btn primary" type="submit">Registar custo</button></div>
    </form>`, 'Materiais de stock, tempos de funcionários, máquinas e corte entram automaticamente. Use isto para faturas e custos externos.');
  document.querySelector('[data-close-modal]').addEventListener('click', closeModal);
  document.getElementById('actual-cost-form').addEventListener('submit', async event => {
    event.preventDefault();
    const form = event.currentTarget;
    try {
      await post(`/costing/orders/${orderId}/actual-costs`, {
        category: form.category.value,
        description: form.description.value,
        quantity: Number(form.quantity.value),
        unit: form.unit.value,
        unit_cost: Number(form.unit_cost.value),
        occurred_on: form.occurred_on.value,
        reference: form.reference.value || null,
        notes: form.notes.value || null,
      });
      closeModal(); toast('Custo real registado.'); await renderControlDetail(container, orderId);
    } catch (error) { toast(error.message, 'error'); }
  });
}

export async function renderControlDetail(container, orderId) {
  const data = await get(`/costing/orders/${orderId}/control`);
  const {order, baseline, metrics, comparison, actual, material_comparison = []} = data;
  container.innerHTML = pageHeader(`Controlo ${order.order_no}`, `${order.style_reference} · ${order.style_description}`, `
    <button class="btn" data-back-control>← Todas as ordens</button>
    <button class="btn primary" data-add-actual>+ Registar custo real</button>`) + (baseline ? `
    <div class="cost-status-strip ${metrics.status === 'risk' ? 'risk' : metrics.status === 'warning' ? 'warning' : 'approved'}">
      <div>${badge(statusText(metrics.status))}</div>
      <div><b>${esc(baseline.quote_no)} · V${baseline.version}</b><span>Orçamento-base aprovado</span></div>
      <div><b>${number(metrics.progress_pct)}%</b><span>Produção concluída</span></div>
      <p>Comparamos o custo real já incorrido com o orçamento correspondente às ${number(metrics.completed_quantity)} peças concluídas.</p>
    </div>
    ${metrics.fx_missing ? `<p class="muted cost-bad">⚠ A proposta-base foi cotada em ${esc(metrics.baseline_currency)} e não há taxa de câmbio configurada — os valores abaixo estão em ${esc(metrics.baseline_currency)}, não convertidos. Configure a taxa em Tabelas → Câmbio.</p>` : ''}
    <div class="metric-grid cost-metrics">
      <div class="metric"><span class="label">Orçamento por peça</span><strong>${money(metrics.budget_unit)}</strong><span class="trend">proposta aprovada</span></div>
      <div class="metric"><span class="label">Orçamento até hoje</span><strong>${money(metrics.earned_budget)}</strong><span class="trend">para o já produzido</span></div>
      <div class="metric"><span class="label">Custo real até hoje</span><strong>${money(metrics.actual_total)}</strong><span class="trend ${metrics.deviation > 0 ? 'bad' : ''}">${number(metrics.completed_quantity)} peças</span></div>
      <div class="metric"><span class="label">Custo real por peça</span><strong>${money(metrics.actual_unit)}</strong><span class="trend">ao progresso atual</span></div>
      <div class="metric"><span class="label">Desvio</span><strong class="${metrics.deviation > 0 ? 'cost-bad' : 'cost-good'}">${metrics.deviation > 0 ? '+' : ''}${money(metrics.deviation)}</strong><span class="trend ${metrics.deviation > 0 ? 'bad' : ''}">${number(metrics.deviation_pct)}%</span></div>
      <div class="metric"><span class="label">Previsão final</span><strong>${money(metrics.forecast_total)}</strong><span class="trend">orçamento total ${money(metrics.budget_total)}</span></div>
    </div>
    <div class="grid-2 cost-control-grid">
      <div class="card"><div class="card-header"><h2>Orçamentado vs. real por tipo</h2><span>Atualização automática</span></div>
        <div class="table-wrap"><table class="data-table"><thead><tr><th>Tipo</th><th>Orçamento/peça</th><th>Permitido até hoje</th><th>Real</th><th>Desvio</th><th>%</th></tr></thead><tbody>${comparison.map(row => `<tr><td><b>${esc(categoryLabel(row.category))}</b></td><td>${money(row.budget_unit)}</td><td>${money(row.budget_to_date)}</td><td>${money(row.actual)}</td><td>${variance(row.deviation)}</td><td class="${row.deviation_pct > 0 ? 'cost-bad' : 'cost-good'}">${number(row.deviation_pct)}%</td></tr>`).join('')}</tbody></table></div>
      </div>
      <div class="card"><div class="card-header"><h2>De onde vêm os valores reais</h2><span>${actual.details.length} registos</span></div>
        <div class="actual-source-list">${actual.details.length ? actual.details.map(row => `<div><span class="badge">${esc(categoryLabel(row.category))}</span><p><b>${esc(row.description)}</b><small>${esc(row.source)}${row.reference ? ` · ${esc(row.reference)}` : ''}</small></p><strong>${money(row.amount)}</strong></div>`).join('') : '<div class="empty"><strong>Ainda sem custos reais</strong>Registe produção, consumos ou documentos.</div>'}</div>
      </div>
    </div>
    ${material_comparison.length ? `<div class="card material-variance-card"><div class="card-header"><div><h2>Consumo de materiais: previsto vs. saída real</h2><span>Calculado pelos movimentos de stock ligados a esta ordem</span></div></div><div class="table-wrap"><table class="data-table"><thead><tr><th>Material</th><th>Previsto</th><th>Consumido</th><th>Desvio consumo</th><th>Custo previsto</th><th>Custo real</th><th>Desvio custo</th></tr></thead><tbody>${material_comparison.map(row=>`<tr><td><b>${esc(row.description)}</b></td><td>${number(row.planned_quantity)} ${esc(row.unit)}</td><td>${number(row.actual_quantity)} ${esc(row.unit)}</td><td class="${row.quantity_deviation>0?'cost-bad':'cost-good'}">${row.quantity_deviation>0?'+':''}${number(row.quantity_deviation)} ${esc(row.unit)}</td><td>${money(row.planned_cost)}</td><td>${money(row.actual_cost)}</td><td>${row.cost_deviation>0?'+':''}${money(row.cost_deviation)}</td></tr>`).join('')}</tbody></table></div></div>` : ''}` : `
    <div class="card missing-baseline"><h2>Falta uma proposta aprovada para este artigo</h2><p>Os custos reais já podem ser registados, mas a comparação só começa depois de aprovar uma proposta no separador “Propostas”.</p><strong>Custo real registado: ${money(metrics.actual_total)}</strong></div>`);
  container.querySelector('[data-back-control]').addEventListener('click', () => renderControls(container));
  container.querySelector('[data-add-actual]').addEventListener('click', () => openActualCost(container, order.id));
}

export async function renderControls(container) {
  const [rows, proposals] = await Promise.all([
    get(`/costing/${state.companyId}/controls`),
    get(`/costing/${state.companyId}/sheets`),
  ]);
  const over = rows.filter(row => row.baseline && (row.metrics.deviation || 0) > 0).length;
  const without = rows.filter(row => !row.baseline).length;
  container.innerHTML = pageHeader('Controlo do custo real', 'A produção alimenta o custo automaticamente; faturas externas podem ser acrescentadas manualmente.') + `
    <div class="cost-control-summary"><div><strong>${rows.length}</strong><span>Ordens acompanhadas</span></div><div class="warning"><strong>${over}</strong><span>Acima do custo permitido</span></div><div class="danger"><strong>${without}</strong><span>Sem proposta aprovada</span></div></div>
    <div class="table-wrap"><table class="data-table"><thead><tr><th>OF</th><th>Artigo</th><th>Quantidade</th><th>Progresso</th><th>Orçamento-base</th><th>Permitido até hoje</th><th>Custo real</th><th>Desvio</th><th>Estado</th><th>Ações</th></tr></thead><tbody>${controlRows(rows, proposals)}</tbody></table></div>`;
  container.onclick = async event => {
    const edit = event.target.closest('[data-edit-proposal]');
    if (edit) {
      const sheetId = Number(edit.dataset.editProposal);
      if (['rejected','obsolete'].includes(edit.dataset.proposalStatus)) {
        try {
          await post(`/costing/sheets/${sheetId}/reopen`, {});
          toast('Proposta reaberta para edição.');
        } catch (error) { toast(error.message, 'error'); return; }
      }
      await renderProposalDetail(container, sheetId);
      return;
    }
    const button = event.target.closest('[data-control]');
    if (button) renderControlDetail(container, Number(button.dataset.control));
  };
}
