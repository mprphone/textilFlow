import { crudList, get, post, put } from '../api.js';
import { date, esc, finiteNumber, money, number, preciseMoney } from '../format.js?v=20260819-8';
import { state } from '../state.js';
import { closeModal, openModal, pageHeader, setHeading, toast } from '../ui.js?v=20260820-5';
import { renderReleaseOrder } from './release_order.js?v=20260824-41';
import { numericValue, statusText, todayIso, valueOf } from './shared.js?v=20260825-53';
import { renderProposalWizard } from './wizard.js?v=20260825-55';

const COST_GROUPS = [
  {key:'fabric', label:'Malhas / tecidos', short:'Malhas', icon:'▧', tone:'mint', category:'material', source:'manual_fabric'},
  {key:'accessory', label:'Acessórios', short:'Acessórios', icon:'◇', tone:'sky', category:'material', source:'manual_accessory'},
  {key:'labor', label:'Mão de obra', short:'Mão de obra', icon:'⌁', tone:'blue', category:'labor', source:'manual_labor'},
  {key:'machine', label:'Máquinas / energia', short:'Máquinas', icon:'⚙', tone:'lilac', category:'machine', source:'manual_machine'},
  {key:'dyeing', label:'Tinturaria', short:'Tinturaria', icon:'◉', tone:'violet', category:'subcontract', source:'manual_dyeing'},
  {key:'printing', label:'Estamparia', short:'Estamparia', icon:'✦', tone:'peach', category:'subcontract', source:'manual_printing'},
  {key:'subcontract', label:'Outros subcontratos', short:'Subcontratos', icon:'⇄', tone:'rose', category:'subcontract', source:'manual_subcontract'},
  {key:'overhead', label:'Indiretos / outros', short:'Indiretos', icon:'＋', tone:'amber', category:'overhead', source:'manual_overhead'},
];
const GROUP_BY_KEY = Object.fromEntries(COST_GROUPS.map(group => [group.key, group]));
const containerBindings = new WeakMap();

function activeRole() {
  return state.companies.find(company => Number(company.id) === Number(state.companyId))?.role || 'viewer';
}

function canEditCosts() { return ['admin', 'manager', 'commercial', 'planner'].includes(activeRole()); }
function canAcceptCosts() { return ['admin', 'manager', 'commercial'].includes(activeRole()); }
function productionStatus(value) {
  return ({planned:'Planeada', released:'Libertada', in_progress:'Em curso', paused:'Em pausa', completed:'Concluída', cancelled:'Cancelada'})[value] || statusText(value);
}

function bindContainer(container, handler) {
  containerBindings.get(container)?.abort();
  const controller = new AbortController();
  containerBindings.set(container, controller);
  container.addEventListener('click', handler, {signal:controller.signal});
}

function safeAmount(line) {
  const explicit = finiteNumber(line.amount, NaN);
  return Number.isFinite(explicit) ? explicit : finiteNumber(line.quantity) * finiteNumber(line.unit_cost);
}

function requirementValues(row = {}) {
  const required = finiteNumber(row.required_quantity ?? row.required ?? row.quantity_required ?? row.needed_quantity);
  const available = finiteNumber(row.available_quantity ?? row.available ?? row.stock_available);
  const reserved = finiteNumber(row.reserved_quantity ?? row.reserved);
  const shortage = Math.max(0, finiteNumber(row.shortage_quantity ?? row.shortage, Math.max(0, required - available)));
  const realUnitCost = finiteNumber(row.real_unit_cost ?? row.average_unit_cost ?? row.stock_valuation_unit_cost ?? row.unit_cost);
  return {required, available, reserved, shortage, realUnitCost};
}

function requirementFor(line, requirements) {
  return requirements.find(row => Number(row.cost_line_id) === Number(line.id)) || null;
}

function lineGroupKey(line, requirement = null) {
  if (GROUP_BY_KEY[line.cost_group]) return line.cost_group;
  if (line.cost_group === 'accessories') return 'accessory';
  if (line.cost_group === 'subcontract_other') return 'subcontract';
  if (line.cost_group === 'other') return 'overhead';
  const source = String(line.source_type || '').toLowerCase();
  const description = String(line.description || '').toLocaleLowerCase('pt');
  if (line.category === 'material') {
    const materialCategory = String(requirement?.material_category || '').toLowerCase();
    if (materialCategory === 'fabric' || source.includes('material') || source.includes('fabric')) return 'fabric';
    if (source.includes('accessory') || ['thread','trim','label','packaging','chemical'].includes(materialCategory)) return 'accessory';
    return /malha|tecido|fleece|rib|jersey|pique|piqué/.test(description) ? 'fabric' : 'accessory';
  }
  if (line.category === 'labor') return 'labor';
  if (line.category === 'machine') return 'machine';
  if (line.category === 'subcontract') {
    if (/tintur|tingimento|dye/.test(description) || source.includes('dye')) return 'dyeing';
    if (/estamp|serigraf|sublima|print/.test(description) || source.includes('print')) return 'printing';
    return 'subcontract';
  }
  return 'overhead';
}

function stageOf(row) {
  if (row.status === 'production' || row.production_order_id) return 'production';
  if (row.status === 'approved') return 'approved';
  if (['rejected', 'obsolete'].includes(row.status)) return 'rejected';
  return 'draft';
}

function stageIndex(row) {
  if (['partially_shipped', 'shipped', 'finished'].includes(row.sales_order_status)) return 3;
  const stage = stageOf(row);
  if (stage === 'production') return 2;
  if (stage === 'approved') return 1;
  return 0;
}

function stockSummaryFrom(sheet, requirements = []) {
  const provided = sheet.stock_summary || {};
  if (Object.keys(provided).length) return provided;
  const shortageItems = requirements.filter(row => requirementValues(row).shortage > 0).length;
  const readyItems = requirements.length - shortageItems;
  return {
    total_items:requirements.length,
    ready_items:readyItems,
    shortage_items:shortageItems,
    coverage_pct:requirements.length ? readyItems / requirements.length * 100 : 0,
  };
}

function proposalFlow(row, compact = true) {
  const stage = stageOf(row);
  const complete = row.completeness?.can_accept === true;
  if (stage === 'rejected') return `<div class="proposal-rejected-flow ${compact ? 'compact' : ''}" aria-label="Proposta recusada, ainda recuperável">
    <span><i>!</i> Recusada</span>
    <button type="button" data-open-sheet="${row.id}">Ver</button>
    ${canEditCosts() ? `<button type="button" class="edit" data-reopen-proposal="${row.id}">Editar proposta</button>` : ''}
    ${canAcceptCosts() ? (complete ? `<button type="button" class="accept" data-accept-proposal="${row.id}">Aceitar agora</button>` : `<button type="button" class="edit" data-open-sheet="${row.id}">Completar ficha</button>`) : ''}
  </div>`;
  const index = stageIndex(row);
  const stepClass = position => position < index ? 'done' : position === index ? 'current' : 'next';
  const acceptAction = stage === 'draft' && canAcceptCosts() && complete ? `data-accept-proposal="${row.id}"` : `data-open-sheet="${row.id}"`;
  const productionAction = stage === 'approved' && canAcceptCosts()
    ? `data-release-proposal="${row.id}"`
    : (stage === 'production' || row.sales_order_id) ? `data-open-production="${row.production_order_id || ''}"` : 'disabled';
  const shippedAction = row.sales_order_id ? `data-open-order="${row.sales_order_id}"` : 'disabled';
  return `<div class="proposal-click-flow ${compact ? 'compact' : ''}" aria-label="Estado da proposta">
    <button type="button" class="${stepClass(0)}" data-open-sheet="${row.id}" title="Abrir ficha de custo"><i>${index > 0 ? '✓' : '1'}</i><span>Ficha</span></button>
    <b>›</b>
    <button type="button" class="${stepClass(1)}" ${acceptAction} title="${stage === 'draft' && canAcceptCosts() ? (complete ? 'Aceitar proposta' : 'Completar a ficha antes do aceite') : 'Abrir proposta'}"><i>${index > 1 ? '✓' : (complete ? '2' : '!')}</i><span>${complete || stage !== 'draft' ? 'Aceite' : 'Incompleta'}</span></button>
    <b>›</b>
    <button type="button" class="${stepClass(2)}" ${productionAction} title="${stage === 'approved' && canAcceptCosts() ? 'Lançar em produção' : 'Produção'}"><i>${index > 2 ? '✓' : '3'}</i><span>Produção</span></button>
    <b>›</b>
    <button type="button" class="${stepClass(3)}" ${shippedAction} title="Ver em Expedição"><i>${index > 3 ? '✓' : '4'}</i><span>Expedido</span></button>
  </div>`;
}

function stockBadge(row) {
  if (['draft','rejected','obsolete'].includes(row.status) && row.completeness && !row.completeness.can_accept) return `<span class="stock-state missing"><i>!</i> Ficha ${number(row.completeness.progress_pct)}%</span>`;
  const summary = row.stock_summary || {};
  if (!finiteNumber(summary.total_items)) return '<span class="stock-state neutral"><i>•</i> Por analisar</span>';
  const missing = finiteNumber(summary.shortage_items);
  return missing
    ? `<span class="stock-state missing"><i>!</i> ${number(missing)} em falta</span>`
    : '<span class="stock-state ready"><i>✓</i> Stock coberto</span>';
}

function proposalRows(rows) {
  return rows.length ? rows.map(row => `
    <tr data-proposal-row data-stage="${stageOf(row)}">
      <td><button class="link-button" data-open-sheet="${row.id}">${esc(row.quote_no)}</button><small class="cost-subline">V${row.version} · ${date(row.updated_at)}</small></td>
      <td><b>${esc(row.style_reference)}</b><small class="cost-subline">${esc(row.style_description)}</small></td>
      <td>${esc(row.customer_name === '—' ? 'Sem cliente' : row.customer_name)}</td>
      <td><b>${number(row.quantity_basis)}</b><small class="cost-subline">peças</small></td>
      <td><b>${preciseMoney(row.total_cost)}</b><small class="cost-subline">Venda ${preciseMoney(row.selling_price)}</small></td>
      <td><span class="margin-pill ${finiteNumber(row.margin_pct) < 20 ? 'risk' : ''}">${number(row.margin_pct)}%</span></td>
      <td>${stockBadge(row)}</td>
      <td>${proposalFlow(row)}</td>
    </tr>`).join('') : `<tr><td colspan="8"><div class="empty"><strong>Sem propostas</strong>Crie a primeira ficha de custo industrial.</div></td></tr>`;
}

function proposalTable(rows) {
  return `<section class="listing-panel"><div class="table-wrap listing-table proposal-table-wrap"><table class="data-table proposal-table"><thead><tr><th>Proposta</th><th>Artigo</th><th>Cliente</th><th>Quantidade</th><th>Custo / venda</th><th>Margem</th><th>Materiais</th><th>Fluxo rápido</th></tr></thead><tbody>${proposalRows(rows)}</tbody></table></div></section>`;
}

function weightedMargin(rows) {
  const sales = rows.reduce((sum, row) => sum + finiteNumber(row.sales_total), 0);
  const margin = rows.reduce((sum, row) => sum + finiteNumber(row.margin_value), 0);
  return sales ? margin / sales * 100 : 0;
}

function overviewAlerts(rows, controls) {
  const alerts = [];
  rows.forEach(row => {
    const summary = row.stock_summary || {};
    if (finiteNumber(summary.shortage_items) > 0) alerts.push({tone:'rose', icon:'!', title:`${row.quote_no}: faltam materiais`, detail:`${number(summary.shortage_items)} referências sem cobertura total`, id:row.id});
    if (finiteNumber(row.selling_price) > 0 && finiteNumber(row.margin_pct) < 20) alerts.push({tone:'amber', icon:'%', title:`${row.quote_no}: margem baixa`, detail:`Margem prevista de ${number(row.margin_pct)}%`, id:row.id});
    if (finiteNumber(row.selling_price) <= 0) alerts.push({tone:'amber', icon:'€', title:`${row.quote_no}: sem preço de venda`, detail:'Defina o preço antes de aceitar a proposta.', id:row.id});
    if (!row.customer_id) alerts.push({tone:'sky', icon:'i', title:`${row.quote_no}: sem cliente`, detail:'Ficha interna; associe um cliente antes de enviar.', id:row.id});
  });
  controls.filter(row => finiteNumber(row.metrics?.deviation_pct) > 5).forEach(row => alerts.push({tone:'rose', icon:'↗', title:`${row.order?.order_no}: custo acima do previsto`, detail:`Desvio de ${number(row.metrics.deviation_pct)}%`, order:true}));
  return alerts.slice(0, 5);
}

export async function renderCostOverview(container) {
  const [rows, controls] = await Promise.all([
    get(`/costing/${state.companyId}/sheets`),
    get(`/costing/${state.companyId}/controls`).catch(() => []),
  ]);
  const stages = {draft:0, approved:0, rejected:0, production:0};
  rows.forEach(row => { stages[stageOf(row)]++; });
  const salesValue = rows.reduce((sum, row) => sum + finiteNumber(row.sales_total), 0);
  const shortages = rows.reduce((sum, row) => sum + finiteNumber(row.stock_summary?.shortage_items), 0);
  const risks = controls.filter(row => finiteNumber(row.metrics?.deviation_pct) > 5).length;
  const alerts = overviewAlerts(rows, controls);
  const newAction = canEditCosts() ? '<button class="btn primary" data-new-proposal>+ Nova ficha de custo</button>' : '';
  container.innerHTML = pageHeader('Fichas de custo industrial', 'Custos, stock, propostas e passagem à produção no mesmo fluxo.', newAction) + `
    <section class="cost-overview-hero">
      <div class="cost-overview-copy"><span>ORÇAMENTAÇÃO INDUSTRIAL EM TEMPO REAL</span><h2>Do custo confirmado à produção, sem voltar a introduzir dados.</h2><p>Materiais, acessórios, mão de obra e subcontratos ficam ligados ao stock e ao custo real da ordem.</p></div>
      <div class="cost-overview-kpis">
        <article class="mint"><span>Valor em proposta</span><strong>${money(salesValue)}</strong><small>${number(rows.length)} fichas</small></article>
        <article class="blue"><span>Margem ponderada</span><strong>${number(weightedMargin(rows))}%</strong><small>sobre valor de venda</small></article>
        <article class="peach"><span>Materiais em falta</span><strong>${number(shortages)}</strong><small>referências por resolver</small></article>
        <article class="rose"><span>Produções em risco</span><strong>${number(risks)}</strong><small>acima do orçamento</small></article>
      </div>
    </section>
    <div class="cost-pipeline" aria-label="Filtrar por fase">
      <button data-overview-filter="all"><i>${rows.length}</i><span>Todas</span><small>Visão completa</small></button>
      <b>›</b><button data-overview-filter="draft"><i>${stages.draft}</i><span>Rascunhos</span><small>A calcular</small></button>
      <b>›</b><button data-overview-filter="rejected"><i>${stages.rejected}</i><span>Recusadas</span><small>Podem ser revistas</small></button>
      <b>›</b><button data-overview-filter="approved"><i>${stages.approved}</i><span>Aceites</span><small>Prontas para lançar</small></button>
      <b>›</b><button data-overview-filter="production"><i>${stages.production}</i><span>Em produção</span><small>Com consumos gerados</small></button>
    </div>
    <div class="cost-overview-grid">
      <section class="card cost-recent"><div class="card-header"><div><h2>Propostas recentes</h2><span>Clique diretamente no próximo estado.</span></div><button class="btn small" data-view-all>Ver todas</button></div>${proposalTable(rows.slice(0, 5))}</section>
      <aside class="card cost-attention"><div class="card-header"><div><h2>Atenção necessária</h2><span>O que pode bloquear margem ou produção.</span></div></div>
        <div class="cost-alert-list">${alerts.length ? alerts.map(alert => `<button class="${alert.tone}" ${alert.id ? `data-open-sheet="${alert.id}"` : 'data-open-production'}><i>${alert.icon}</i><span><b>${esc(alert.title)}</b><small>${esc(alert.detail)}</small></span><em>→</em></button>`).join('') : '<div class="all-clear"><span>✓</span><div><b>Tudo controlado</b><p>Não há alertas críticos neste momento.</p></div></div>'}</div>
      </aside>
    </div>`;
  bindListActions(container, () => renderCostOverview(container));
}

async function newProposal(container) {
  const [styles, customers] = await Promise.all([
    crudList('styles', state.companyId),
    crudList('customers', state.companyId),
  ]);
  const defaultValidity = new Date();
  defaultValidity.setDate(defaultValidity.getDate() + 30);
  openModal('Ficha para artigo existente', `
    <form id="new-proposal-form" class="form-grid">
      <div class="form-section">Cliente e artigo</div>
      <div class="field full"><label>Artigo existente *<select name="style_id" required><option value="">Selecionar…</option>${styles.map(row => `<option value="${row.id}" data-customer-id="${row.customer_id || ''}">${esc(row.reference)} · ${esc(row.description)}</option>`).join('')}</select></label></div>
      <div class="field"><label>Cliente<select name="customer_id"><option value="">Ficha interna / sem cliente</option>${customers.map(row => `<option value="${row.id}">${esc(row.name)}</option>`).join('')}</select></label></div>
      <div class="field"><label>N.º da proposta<input name="quote_no" placeholder="Gerado automaticamente"></label></div>
      <div class="form-section">Cálculo</div>
      <div class="field"><label>Quantidade prevista *<input name="quantity" type="number" min="1" step="1" value="500" required></label></div>
      <div class="field"><label>Preço de venda por peça<input name="selling_price" type="number" min="0" step="0.0001" value="0"></label></div>
      <div class="field"><label>Válida até<input name="valid_until" type="date" value="${defaultValidity.toISOString().slice(0,10)}"></label></div>
      <div class="field full"><label class="cost-check"><input name="import_technical_costs" type="checkbox" checked> Importar BOM, operações e preços atuais do artigo</label><small class="muted">A ligação ao stock é preservada para calcular disponibilidade e custo real.</small></div>
      <div class="field full"><label>Notas<textarea name="notes" placeholder="Condições, transporte, prazos, observações…"></textarea></label></div>
      <div class="form-footer"><button type="button" class="btn" data-close-modal>Cancelar</button><button class="btn primary" type="submit">Criar e calcular</button></div>
    </form>`, 'Não cria um artigo duplicado; usa a ficha técnica já existente.');
  document.querySelector('[data-close-modal]').addEventListener('click', closeModal);
  const proposalForm = document.getElementById('new-proposal-form');
  proposalForm.style_id.addEventListener('change', () => {
    const customerId = proposalForm.style_id.selectedOptions[0]?.dataset.customerId;
    if (customerId && !proposalForm.customer_id.value) proposalForm.customer_id.value = customerId;
  });
  proposalForm.addEventListener('submit', async event => {
    event.preventDefault();
    const form = event.currentTarget;
    const submit = form.querySelector('[type="submit"]');
    submit.disabled = true;
    submit.textContent = 'A criar e calcular…';
    try {
      const result = await post('/costing/sheets', {
        company_id:state.companyId,
        style_id:Number(form.style_id.value),
        customer_id:form.customer_id.value ? Number(form.customer_id.value) : null,
        quote_no:form.quote_no.value || null,
        quantity:Number(form.quantity.value),
        selling_price:Number(form.selling_price.value || 0),
        valid_until:form.valid_until.value || null,
        notes:form.notes.value || null,
        import_technical_costs:form.import_technical_costs.checked,
      });
      closeModal(); toast('Ficha criada com a estrutura e o stock do artigo.');
      await renderProposalDetail(container, result.sheet.id);
    } catch (error) {
      submit.disabled = false;
      submit.textContent = 'Criar e calcular';
      toast(error.message, 'error');
    }
  });
}

function chooseProposalType(container) {
  openModal('Criar ficha de custo', `
    <div class="cost-create-choices">
      <button type="button" data-existing-article><i>▤</i><span><b>Artigo existente</b><small>Usar BOM, operações e stock já registados sem duplicar a ficha.</small></span><em>→</em></button>
      <button type="button" data-new-development><i>✦</i><span><b>Novo desenvolvimento</b><small>Criar artigo, malhas, acessórios, produção e proposta no assistente guiado.</small></span><em>→</em></button>
    </div>`, 'Escolha o ponto de partida.');
  document.querySelector('[data-existing-article]').addEventListener('click', async () => { closeModal(); await newProposal(container); });
  document.querySelector('[data-new-development]').addEventListener('click', () => {
    closeModal();
    renderProposalWizard(container, result => renderProposalDetail(container, result.sheet.id), () => renderProposals(container));
  });
}

function groupOptions(selected) {
  return COST_GROUPS.map(group => `<option value="${group.key}" ${group.key === selected ? 'selected' : ''}>${esc(group.label)}</option>`).join('');
}

function editorLine(line = {}, locked = false, requirement = null) {
  const groupKey = lineGroupKey(line, requirement);
  const source = line.source_type || '';
  const sourceId = line.source_id ?? '';
  const stock = requirement ? requirementValues(requirement) : null;
  const clientSupplied = source.startsWith('client_supplied');
  const origin = locked
    ? `<span class="line-origin ${stock && !clientSupplied ? 'stock' : ''}"><i></i>${esc(clientSupplied ? 'Fornecido pelo cliente' : (line.source_label || (stock ? (stock.shortage > 0 ? `Falta ${number(stock.shortage)}` : 'Stock confirmado') : (source ? 'Ficha técnica' : 'Manual'))))}</span>`
    : `<label class="line-client-supplied" title="O cliente fornece este componente; o preço pode ficar a zero"><input type="checkbox" data-line="client_supplied" ${clientSupplied ? 'checked' : ''}> Cliente</label>`;
  return `<tr class="${line.validation_status === 'incomplete' ? 'cost-line-incomplete' : ''}" data-cost-line data-cost-line-id="${line.id || ''}" data-original-group="${groupKey}" data-source-type="${esc(source)}" data-source-id="${sourceId}">
    <td><select data-line="group" ${locked ? 'disabled' : ''}>${groupOptions(groupKey)}</select></td>
    <td><input data-line="description" value="${esc(line.description || '')}" placeholder="Descrição do custo" ${locked ? 'disabled' : ''}></td>
    <td><input data-line="quantity" type="number" min="0" step="any" value="${finiteNumber(line.quantity, 1)}" ${locked ? 'disabled' : ''}></td>
    <td><input data-line="unit" value="${esc(line.unit || 'un')}" ${locked ? 'disabled' : ''}></td>
    <td><input data-line="unit_cost" type="number" min="0" step="any" value="${finiteNumber(line.unit_cost)}" ${locked ? 'disabled' : ''}></td>
    <td data-line-total>${preciseMoney(safeAmount(line))}</td>
    <td>${origin}</td>
    ${locked ? '<td></td>' : '<td><button class="btn icon danger" type="button" data-icon="delete" data-remove-line aria-label="Remover custo" title="Remover custo"></button></td>'}
  </tr>`;
}

function validNumber(root, selector, label, {positive = false} = {}) {
  const input = root.querySelector(selector);
  const value = Number(input?.value);
  if (!Number.isFinite(value) || (positive ? value <= 0 : value < 0)) throw new Error(`${label}: introduza um valor válido${positive ? ' superior a zero' : ''}.`);
  return value;
}

function readLines(root) {
  return [...root.querySelectorAll('[data-cost-line]')].map(row => {
    const groupKey = valueOf(row, '[data-line="group"]');
    const group = GROUP_BY_KEY[groupKey] || GROUP_BY_KEY.overhead;
    const preserveSource = groupKey === row.dataset.originalGroup;
    const description = valueOf(row, '[data-line="description"]').trim();
    if (!description) return null;
    const result = {
      category:group.category,
      description,
      quantity:validNumber(row, '[data-line="quantity"]', `Consumo de ${description}`),
      unit:valueOf(row, '[data-line="unit"]').trim() || 'un',
      unit_cost:validNumber(row, '[data-line="unit_cost"]', `Custo de ${description}`),
      source_type:preserveSource ? (row.dataset.sourceType || group.source) : group.source,
      source_id:preserveSource && row.dataset.sourceId ? Number(row.dataset.sourceId) : null,
    };
    if (row.querySelector('[data-line="client_supplied"]')?.checked) result.source_type = 'client_supplied';
    return result;
  }).filter(Boolean);
}

function setAllText(root, selector, value) {
  root.querySelectorAll(selector).forEach(node => { node.textContent = value; });
}

function refreshEditorAlerts(root, {cost, sale, margin, qty} = {}) {
  const bar = root.querySelector('[data-proposal-alerts]') || root.closest('.proposal-board')?.querySelector('[data-proposal-alerts]');
  if (!bar) return;
  const alerts = [];
  if (!Number.isFinite(sale) || sale <= 0) alerts.push({tone:'amber', text:'Sem preço de venda definido.'});
  else if (margin < 20) alerts.push({tone:'amber', text:`Margem ${number(margin)}% abaixo de 20%.`});
  const shortage = finiteNumber(root.dataset.shortageItems);
  if (shortage > 0) alerts.push({tone:'sky', text:`${number(shortage)} ${shortage === 1 ? 'material' : 'materiais'} sem cobertura de stock.`, action:'stock'});
  const missingPrice = [...root.querySelectorAll('[data-cost-line]')].some(row => {
    const description = valueOf(row, '[data-line="description"]').trim();
    return description && numericValue(row, '[data-line="unit_cost"]') <= 0 && !row.querySelector('[data-line="client_supplied"]')?.checked;
  });
  if (missingPrice) alerts.push({tone:'amber', text:'Há linhas de custo sem preço unitário.'});
  if (!qty) alerts.push({tone:'sky', text:'Indique a quantidade prevista.'});
  bar.innerHTML = alerts.map(alert => `<button type="button" class="proposal-alert-btn ${alert.tone}" data-alert-action="${alert.action || ''}">${esc(alert.text)}</button>`).join('');
}

function refreshEditorTotals(root) {
  let cost = 0;
  const groups = Object.fromEntries(COST_GROUPS.map(group => [group.key, 0]));
  root.querySelectorAll('[data-cost-line]').forEach(row => {
    const total = numericValue(row, '[data-line="quantity"]') * numericValue(row, '[data-line="unit_cost"]');
    row.querySelector('[data-line-total]').textContent = preciseMoney(total);
    const key = valueOf(row, '[data-line="group"]');
    groups[key] = finiteNumber(groups[key]) + total;
    cost += total;
    const clientSupplied = row.querySelector('[data-line="client_supplied"]')?.checked;
    row.classList.toggle('cost-line-incomplete', numericValue(row, '[data-line="quantity"]') <= 0 || (numericValue(row, '[data-line="unit_cost"]') <= 0 && !clientSupplied));
  });
  const qty = numericValue(root, '[name="quantity"]');
  const sale = numericValue(root, '[name="selling_price"]');
  const vatPct = Math.max(0, numericValue(root, '[name="vat_pct"]') || 23);
  const financialPct = Math.max(0, numericValue(root, '[name="financial_cost_pct"]'));
  const markupPct = Math.max(0, numericValue(root, '[name="markup_pct"]'));
  const commissionPct = Math.max(0, numericValue(root, '[name="commission_pct"]'));
  const suggested = recommendedPrice(cost, financialPct, markupPct, commissionPct);
  const margin = sale ? (sale - cost) / sale * 100 : 0;
  const saleTotal = sale * qty;
  const vatAmount = saleTotal * vatPct / 100;
  const scope = root.closest('[data-cost-panel]') || root.parentElement || root;
  setAllText(scope, '[data-total-unit]', preciseMoney(cost));
  setAllText(scope, '[data-sale-unit]', preciseMoney(sale));
  setAllText(scope, '[data-total-proposal]', money(cost * qty));
  setAllText(scope, '[data-total-sale]', money(saleTotal));
  setAllText(scope, '[data-vat-pct]', `${number(vatPct)}%`);
  setAllText(scope, '[data-vat-amount]', money(vatAmount));
  setAllText(scope, '[data-total-sale-vat]', money(saleTotal + vatAmount));
  setAllText(scope, '[data-profit-total]', money((sale - cost) * qty));
  setAllText(scope, '[data-suggested-price]', preciseMoney(suggested));
  setAllText(scope, '[data-suggested-inline]', preciseMoney(suggested));
  root.dataset.suggestedPrice = String(suggested);
  setAllText(scope, '[data-total-margin]', `${number(margin)}%`);
  COST_GROUPS.forEach(group => setAllText(scope, `[data-group-total="${group.key}"]`, preciseMoney(groups[group.key])));
  scope.querySelectorAll('[data-margin-value]').forEach(node => node.classList.toggle('risk', margin < 20));
  refreshEditorAlerts(root, {cost, sale, margin, qty});
}

async function saveProposal(root, sheetId) {
  const payload = {
    customer_id:valueOf(root, '[name="customer_id"]') ? Number(valueOf(root, '[name="customer_id"]')) : null,
    quote_no:valueOf(root, '[name="quote_no"]'),
    quantity:validNumber(root, '[name="quantity"]', 'Quantidade', {positive:true}),
    selling_price:validNumber(root, '[name="selling_price"]', 'Preço de venda'),
    valid_until:valueOf(root, '[name="valid_until"]') || null,
    notes:valueOf(root, '[name="notes"]') || null,
    vat_pct:validNumber(root, '[name="vat_pct"]', 'IVA'),
    currency:valueOf(root, '[name="currency"]') || null,
    payment_terms:valueOf(root, '[name="payment_terms"]') || '30 dias',
    client_notes:valueOf(root, '[name="client_notes"]') || null,
    financial_cost_pct:validNumber(root, '[name="financial_cost_pct"]', 'Encargos financeiros'),
    markup_pct:validNumber(root, '[name="markup_pct"]', 'Acréscimo / margem alvo'),
    commission_pct:validNumber(root, '[name="commission_pct"]', 'Comissão'),
    lines:readLines(root),
  };
  if (!payload.lines.length) throw new Error('Adicione pelo menos uma linha de custo.');
  return put(`/costing/sheets/${sheetId}`, payload);
}

function familyFilters() {
  return `<div class="cost-family-filters">
    <button type="button" class="active" data-cost-group="all">Todas</button>
    ${COST_GROUPS.map(group => `<button type="button" data-cost-group="${group.key}">${esc(group.short)}</button>`).join('')}
  </div>`;
}

function recommendedPrice(cost, financialPct, markupPct, commissionPct) {
  const divisor = 1 - Math.min(99, Math.max(0, commissionPct)) / 100;
  return divisor > 0 ? cost * (1 + Math.max(0, financialPct) / 100 + Math.max(0, markupPct) / 100) / divisor : 0;
}

function completenessPanel(completeness = {}, locked = false) {
  const checks = completeness.checks || [];
  const blockers = completeness.blockers || checks.filter(check => !check.complete);
  const ready = completeness.can_accept === true;
  const progress = finiteNumber(completeness.progress_pct);
  return `<section class="cost-completeness ${ready ? 'ready' : 'incomplete'}">
    <div class="cost-completeness-summary">
      <span class="cost-completeness-icon">${ready ? '✓' : '!'}</span>
      <div><b>${ready ? 'Ficha completa para aceitar' : 'Ficha incompleta'}</b><small>${ready ? 'Todos os custos essenciais estão confirmados.' : `${blockers.length} pontos por confirmar antes do aceite.`}</small></div>
      <strong>${number(progress)}%</strong>
      ${locked || ready ? '' : '<button class="btn small" type="button" data-autofill-sheet>Atualizar da ficha técnica</button>'}
    </div>
    <div class="cost-completeness-bar"><i style="width:${Math.max(0, Math.min(100, progress))}%"></i></div>
    <div class="cost-checklist">${checks.map(check => `<button type="button" class="${check.complete ? 'done' : 'missing'}" data-check-group="${esc(check.group || '')}" title="${esc(check.detail || '')}"><i>${check.complete ? '✓' : '!'}</i><span>${esc(check.label)}</span></button>`).join('')}</div>
  </section>`;
}

function stockPanel(requirements, summary, {editable = false, variance = null} = {}) {
  if (!requirements.length) return `<div class="cost-stock-empty"><i>▦</i><div><b>Sem materiais ligados ao stock</b><p>Associe as linhas à BOM do artigo para calcular necessidades, disponibilidade e custo real por lote.</p></div></div>`;
  const coverage = Math.max(0, Math.min(100, finiteNumber(summary.coverage_pct)));
  return `<section class="cost-stock-panel">
    <header><div><span>STOCK & MRP</span><h3>Disponibilidade para ${number(summary.quantity || 0)} peças</h3></div><div class="stock-coverage ${finiteNumber(summary.shortage_items) ? 'warning' : ''}"><b>${number(coverage)}%</b><small>cobertura</small></div></header>
    <div class="stock-coverage-bar"><i style="width:${coverage}%"></i></div>
    ${variance ? `<div class="stock-cost-variance"><span>Materiais na ficha <b>${preciseMoney(variance.planned_material_unit_cost)}</b></span><span>Custo real dos lotes <b>${preciseMoney(variance.stock_material_unit_cost)}</b></span><em class="${finiteNumber(variance.unit_variance) > 0 ? 'risk' : 'good'}">${finiteNumber(variance.unit_variance) > 0 ? '+' : ''}${preciseMoney(variance.unit_variance)} / peça</em></div>` : ''}
    <div class="stock-requirements">${requirements.map(row => {
      const values = requirementValues(row);
      const quotedCost = finiteNumber(
        row.planned_unit_cost ?? row.sheet_unit_cost ?? row.quoted_unit_cost,
        values.realUnitCost,
      );
      const realDiff = Math.abs(values.realUnitCost - quotedCost) > 0.0001;
      return `<article class="${values.shortage > 0 ? 'missing' : 'ready'}">
        <span class="stock-material-icon">${values.shortage > 0 ? '!' : '✓'}</span>
        <div><b>${esc(row.description || row.material_name || 'Material')}</b><small>Nec. ${number(values.required)} ${esc(row.unit || '')} · Livre ${number(values.available)} ${esc(row.unit || '')}${values.reserved ? ` · Reservado ${number(values.reserved)}` : ''}</small></div>
        <div class="stock-real-cost"><small>Custo real</small><b>${preciseMoney(values.realUnitCost)}</b></div>
        ${values.shortage > 0 ? `<em>Falta ${number(values.shortage)} ${esc(row.unit || '')}</em>` : '<em>Disponível</em>'}
        ${editable && realDiff && row.cost_line_id ? `<button type="button" data-use-stock-cost="${row.cost_line_id}" data-stock-cost="${values.realUnitCost}">Usar custo real</button>` : ''}
      </article>`;
    }).join('')}</div>
  </section>`;
}

function detailHero(sheet, actions = '') {
  const stage = stageOf(sheet);
  const initials = esc((sheet.style_reference || 'C').slice(0, 2).toUpperCase());
  return `<section class="industrial-cost-hero proposal-hero">
    <div class="industrial-cost-title">
      <button class="btn small" type="button" data-back>←</button>
      <span class="cost-style-thumb">${sheet.style_image_url ? `<img src="${esc(sheet.style_image_url)}" alt="">` : initials}</span>
      <div>
        <small>${esc(sheet.quote_no)} · ficha de custo</small>
        <h2>${esc(sheet.style_description || sheet.style_reference)}</h2>
        <p>${esc(sheet.customer_name === '—' ? 'Ficha interna' : sheet.customer_name)} · ${number(sheet.quantity_basis)} pcs · v${sheet.version}</p>
      </div>
      <span class="cost-state ${stage}">${statusText(stage)}</span>
      <div class="cost-detail-flow">${proposalFlow(sheet, false)}</div>
      <div class="proposal-hero-actions">${actions}</div>
    </div>
  </section>`;
}

function acceptModal(container, sheet, beforeAccept, afterAccept) {
  openModal('Aceitar proposta', `<div class="cost-transition-confirm"><span>✓</span><h3>${esc(sheet.quote_no)} fica pronta para produção</h3><p>O custo é congelado. A seguir cria a OF, as necessidades e, se faltar malha, a encomenda de malha.</p><div><b>${preciseMoney(sheet.total_cost)} / peça</b><b>${number(sheet.margin_pct)}% margem</b></div><footer><button class="btn" type="button" data-close-transition>Cancelar</button><button class="btn success" type="button" data-confirm-accept>Aceitar proposta →</button></footer></div>`, 'Transição comercial com rastreabilidade.');
  document.querySelector('[data-close-transition]').addEventListener('click', closeModal);
  document.querySelector('[data-confirm-accept]').addEventListener('click', async event => {
    const button = event.currentTarget;
    button.disabled = true; button.textContent = 'A aceitar…';
    try {
      if (beforeAccept) await beforeAccept();
      await post(`/costing/sheets/${sheet.id}/approve`, {});
      closeModal(); toast('Proposta aceite. Defina agora as quantidades por cor e tamanho.');
      await afterAccept();
    } catch (error) { button.disabled = false; button.textContent = 'Aceitar proposta →'; toast(error.message, 'error'); }
  });
}

function rejectModal(container, sheet, afterReject) {
  openModal('Registar recusa do cliente', `
    <form class="proposal-reject-form" data-reject-form>
      <div class="cost-transition-confirm rejected"><span>!</span><h3>${esc(sheet.quote_no)} fica marcada como recusada</h3><p>A proposta não é eliminada. Pode ser reaberta, editada e aceite mais tarde se o cliente mudar de decisão.</p></div>
      <label>Motivo ou observação<textarea name="reason" rows="3" placeholder="Opcional — preço, prazo, condições comerciais…"></textarea></label>
      <footer class="form-footer"><button class="btn" type="button" data-close-transition>Cancelar</button><button class="btn danger" type="submit">Marcar como recusada</button></footer>
    </form>`, 'A decisão fica guardada no histórico comercial.');
  document.querySelector('[data-close-transition]').addEventListener('click', closeModal);
  document.querySelector('[data-reject-form]').addEventListener('submit', async event => {
    event.preventDefault();
    const button = event.currentTarget.querySelector('[type="submit"]');
    button.disabled = true;
    try {
      await post(`/costing/sheets/${sheet.id}/reject`, {reason:event.currentTarget.reason.value || null});
      closeModal();
      toast('Proposta marcada como recusada. Continua disponível para edição ou aceitação.');
      await afterReject();
    } catch (error) { button.disabled = false; toast(error.message, 'error'); }
  });
}

async function reopenProposal(container, sheetId, afterReopen = null) {
  try {
    await post(`/costing/sheets/${sheetId}/reopen`, {});
    toast('Proposta reaberta. Já pode alterar os valores e condições.');
    if (afterReopen) await afterReopen();
    else await renderProposalDetail(container, sheetId);
  } catch (error) { toast(error.message, 'error'); }
}

export function releaseRequirements(preview, lines, quantity, hasCustomer = false) {
  const requirements = preview.requirements || preview.consumptions || [];
  const summary = preview.stock_summary || stockSummaryFrom({stock_summary:{}}, requirements);
  summary.quantity = quantity;
  const laborMinutes = finiteNumber(preview.labor_minutes, lines.filter(line => line.category === 'labor').reduce((sum, line) => sum + finiteNumber(line.quantity), 0) * quantity);
  const subcontractLines = preview.subcontracts || lines.filter(line => line.category === 'subcontract').map(line => ({description:line.description, amount:safeAmount(line) * quantity}));
  const blockers = (preview.blockers || []).filter(message => !(hasCustomer && String(message).toLocaleLowerCase('pt').includes('cliente')));
  return `${blockers.length ? `<div class="cost-preview-error"><b>Antes de lançar:</b><span>${blockers.map(esc).join(' · ')}</span></div>` : ''}<div class="release-preview-summary">
      <div><span>Materiais</span><b>${number(requirements.length)}</b><small>${number(finiteNumber(summary.shortage_items))} com falta</small></div>
      <div><span>Tempo de produção</span><b>${number(laborMinutes / 60)} h</b><small>${number(laborMinutes)} minutos</small></div>
      <div><span>Subcontratos</span><b>${number(subcontractLines.length)}</b><small>${money(subcontractLines.reduce((sum, row) => sum + finiteNumber(row.amount), 0))}</small></div>
    </div>${stockPanel(requirements, summary, {variance:preview.cost_variance})}`;
}

async function openProductionOrder(orderId) {
  if (!orderId) { location.hash = '#/orders'; return; }
  try {
    const data = await get(`/production/orders/${orderId}/trace`);
    const order = data.order || {};
    const requirements = data.material_requirements || [];
    const summary = stockSummaryFrom({}, requirements);
    summary.quantity = order.quantity;
    openModal(`Ordem ${order.order_no || `#${orderId}`}`, `
      <div class="release-preview-summary production-order-summary">
        <div><span>Quantidade</span><b>${number(order.quantity)}</b><small>${esc(order.reference || '')}</small></div>
        <div><span>Planeamento</span><b>${date(order.planned_start)}</b><small>Entrega ${date(order.planned_end)}</small></div>
        <div><span>Estado</span><b>${esc(productionStatus(order.status))}</b><small>${esc(order.current_stage || 'Planeamento')}</small></div>
      </div>
      ${stockPanel(requirements, summary)}
      <div class="form-footer"><button class="btn" type="button" data-close-production-order>Fechar</button><button class="btn primary" type="button" data-go-production-module>Abrir módulo Produção →</button></div>
    `, 'OF criada a partir da proposta aceite, com necessidades e reservas rastreáveis.');
    document.querySelector('[data-close-production-order]').addEventListener('click', closeModal);
    document.querySelector('[data-go-production-module]').addEventListener('click', () => { closeModal(); location.hash = '#/orders'; });
  } catch (error) { toast(error.message, 'error'); }
}

function printProposal(sheet, editor) {
  const qty = numericValue(editor, '[name="quantity"]') || finiteNumber(sheet.quantity_basis, 1);
  const sale = numericValue(editor, '[name="selling_price"]');
  const vatPct = Math.max(0, numericValue(editor, '[name="vat_pct"]') || finiteNumber(sheet.vat_pct, 23));
  const saleTotal = sale * qty;
  const vatAmount = saleTotal * vatPct / 100;
  const terms = valueOf(editor, '[name="payment_terms"]') || sheet.payment_terms || '30 dias';
  const quote = valueOf(editor, '[name="quote_no"]') || sheet.quote_no;
  const clientNotes = valueOf(editor, '[name="client_notes"]') || sheet.client_notes || '';
  const customerName = editor.querySelector('[name="customer_id"] option:checked')?.textContent?.trim() || sheet.customer_name;
  const company = state.companies.find(row => Number(row.id) === Number(state.companyId));
  const issuerName = company?.legal_name || company?.name || 'TextileFlow';
  const issuerNif = company?.tax_id || '';
  const issuerAddr = [company?.address, company?.postal_code, company?.city].filter(Boolean).join(' · ');
  const validUntil = valueOf(editor, '[name="valid_until"]') || sheet.valid_until || 'a combinar';
  const logo = company?.logo;
  if (!valueOf(editor, '[name="customer_id"]') && (!sheet.customer_id)) {
    toast('Associe um cliente antes de emitir o documento ao exterior.', 'error');
    return;
  }
  const win = window.open('', 'tf-proposal-print', 'noopener,noreferrer,width=900,height=1100');
  if (!win) { toast('Permita janelas pop-up para imprimir a proposta.', 'error'); return; }
  win.document.write(`<!doctype html><html lang="pt-PT"><head><meta charset="utf-8"><title>Proposta ${esc(quote)}</title>
    <style>
      body{font:13px/1.5 "Segoe UI",sans-serif;color:#1a2433;margin:28px;background:#fff}
      header{display:flex;justify-content:space-between;gap:24px;border-bottom:2px solid #1a3f73;padding-bottom:16px;align-items:flex-start}
      .brand{display:flex;gap:12px;align-items:center}
      .brand img{max-height:48px;max-width:120px;object-fit:contain}
      .brand b{display:block;font-size:20px} .brand small{display:block;color:#5b6b80;font-size:11px}
      .doc{text-align:right} .doc b{display:block;font-size:20px} .doc span{color:#5b6b80;font-size:12px}
      .parties{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin:20px 0}
      .parties div{padding:12px 14px;border:1px solid #dbe3ee;border-radius:12px;background:#f8fafc}
      .parties span{display:block;font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:#6b7c90;margin-bottom:4px}
      table{width:100%;border-collapse:collapse;margin-top:8px} th,td{padding:10px 8px;border-bottom:1px solid #e6edf5}
      th{font-size:10px;color:#5f7388;text-transform:uppercase;text-align:left} td.num,th.num{text-align:right}
      .totals{margin-left:auto;width:280px;margin-top:16px} .totals div{display:flex;justify-content:space-between;padding:7px 0;border-bottom:1px solid #edf2f8}
      .totals div.grand{border:0;font-size:16px;font-weight:800;padding-top:10px}
      .terms{margin-top:28px;font-size:12px;color:#334155} footer{margin-top:36px;color:#6b7c90;font-size:11px}
    </style></head><body>
    <header>
      <div class="brand">${logo ? `<img src="${esc(logo)}" alt="">` : ''}<div><b>${esc(issuerName)}</b>${issuerNif ? `<small>NIF ${esc(issuerNif)}</small>` : ''}${issuerAddr ? `<small>${esc(issuerAddr)}</small>` : ''}<small>Proposta comercial</small></div></div>
      <div class="doc"><b>${esc(quote)}</b><span>Válida até ${esc(validUntil)}</span><span>${esc(todayIso())}</span></div>
    </header>
    <div class="parties">
      <div><span>Cliente</span><b>${esc(customerName === 'Ficha interna' || customerName === '—' ? '—' : customerName)}</b></div>
      <div><span>Artigo</span><b>${esc(sheet.style_reference)}</b><div>${esc(sheet.style_description)}</div></div>
    </div>
    <table><thead><tr><th>Descrição</th><th class="num">Qtd.</th><th class="num">Preço un. s/ IVA</th><th class="num">IVA</th><th class="num">Total s/ IVA</th></tr></thead>
    <tbody><tr>
      <td>${esc(sheet.style_reference)} · ${esc(sheet.style_description)}</td>
      <td class="num">${number(qty)} pcs</td>
      <td class="num">${preciseMoney(sale)}</td>
      <td class="num">${number(vatPct)}%</td>
      <td class="num">${money(saleTotal)}</td>
    </tr></tbody></table>
    <div class="totals">
      <div><span>Subtotal s/ IVA</span><b>${money(saleTotal)}</b></div>
      <div><span>IVA ${number(vatPct)}%</span><b>${money(vatAmount)}</b></div>
      <div class="grand"><span>Total c/ IVA</span><b>${money(saleTotal + vatAmount)}</b></div>
    </div>
    <div class="terms">
      <p><b>Condições de pagamento:</b> ${esc(terms)}</p>
      ${clientNotes ? `<p>${esc(clientNotes)}</p>` : ''}
    </div>
    <footer>Documento para o cliente. Custos internos e margem não são incluídos. ${esc(issuerName)}${issuerNif ? ` · NIF ${esc(issuerNif)}` : ''}.</footer>
    <script>window.onload=function(){window.focus();window.print();}</script>
  </body></html>`);
  win.document.close();
}

export async function renderProposalDetail(container, sheetId) {
  containerBindings.get(container)?.abort();
  const [detail, customers] = await Promise.all([
    get(`/costing/sheets/${sheetId}`),
    crudList('customers', state.companyId),
  ]);
  const {sheet, lines} = detail;
  const completeness = detail.completeness || sheet.completeness || {};
  const pricing = detail.pricing || sheet.pricing || {};
  const requirements = detail.requirements || sheet.requirements || [];
  const stockSummary = detail.stock_summary || sheet.stock_summary || stockSummaryFrom(sheet, requirements);
  stockSummary.quantity = sheet.quantity_basis;
  const locked = sheet.status !== 'draft' || !canEditCosts();
  setHeading(`${sheet.quote_no} · ${sheet.style_reference}`, 'Custo, stock e passagem à produção.');
  const heroActions = `
    <button class="btn small" data-print>PDF cliente</button>
    ${sheet.customer_email ? '<button class="btn small" data-email>Email</button>' : ''}
    ${canEditCosts() ? '<button class="btn small" data-duplicate>Duplicar</button>' : ''}`;
  container.innerHTML = `
    <div class="proposal-board">
    ${detailHero(sheet, heroActions)}
    <form data-proposal-editor class="industrial-cost-editor">
      <section class="card cost-essentials-card cost-meta-bar">
        <div class="cost-meta-compact">
          <label>N.º proposta<input name="quote_no" value="${esc(sheet.quote_no)}" ${locked ? 'disabled' : ''}></label>
          <label>Quantidade<input name="quantity" type="number" min="1" step="1" value="${finiteNumber(sheet.quantity_basis, 1)}" ${locked ? 'disabled' : ''}></label>
          <label>Cliente<select name="customer_id" ${locked ? 'disabled' : ''}><option value="">Ficha interna</option>${customers.map(row => `<option value="${row.id}" data-payment="${esc(row.payment_terms || '')}" ${String(row.id) === String(sheet.customer_id) ? 'selected' : ''}>${esc(row.name)}</option>`).join('')}</select></label>
          <label class="cost-price-field">Venda / peça s/ IVA<input name="selling_price" type="number" min="0" step="any" value="${finiteNumber(sheet.selling_price)}" ${locked ? 'disabled' : ''}>${locked ? '' : `<button type="button" data-use-suggested-price>Usar sugerido · <span data-suggested-inline>${preciseMoney(pricing.recommended_selling_price)}</span></button>`}</label>
          <label>Moeda<select name="currency" ${locked ? 'disabled' : ''}>${['EUR','USD','GBP','CHF'].map(code => `<option value="${code}" ${(sheet.currency || 'EUR') === code ? 'selected' : ''}>${code}</option>`).join('')}</select></label>
          <label>Válida até<input name="valid_until" type="date" value="${esc(sheet.valid_until || '')}" ${locked ? 'disabled' : ''}></label>
          <label>Notas internas<input name="notes" value="${esc(sheet.notes || '')}" placeholder="Só para a fábrica" ${locked ? 'disabled' : ''}></label>
          <label>Encargos financeiros %<input name="financial_cost_pct" type="number" min="0" max="100" step="0.1" value="${finiteNumber(pricing.financial_cost_pct, 2)}" ${locked ? 'disabled' : ''}></label>
          <label>Acréscimo / margem alvo %<input name="markup_pct" type="number" min="0" max="500" step="0.1" value="${finiteNumber(pricing.markup_pct, 35)}" ${locked ? 'disabled' : ''}></label>
          <label>Comissão %<input name="commission_pct" type="number" min="0" max="99" step="0.1" value="${finiteNumber(pricing.commission_pct)}" ${locked ? 'disabled' : ''}></label>
        </div>
        ${sheet.currency && sheet.currency !== sheet.base_currency ? `<p class="muted section-note">${sheet.fx_missing ? `⚠ Sem taxa de câmbio ${esc(sheet.currency)} → ${esc(sheet.base_currency)} configurada em Tabelas → Câmbio — os totais em ${esc(sheet.base_currency)} não são mostrados.` : `≈ ${money(sheet.sales_total_base)} ${esc(sheet.base_currency)} à taxa de ${finiteNumber(sheet.fx_rate).toFixed(4)} (venda) · margem ≈ ${money(sheet.margin_value_base)} ${esc(sheet.base_currency)}`}</p>` : ''}
      </section>
      ${completenessPanel(completeness, locked)}
      <div class="proposal-alerts" data-proposal-alerts></div>
      <section class="card cost-composition-card">
        <div class="card-header composition-head">
          <h2>Composição do custo</h2>
          ${familyFilters()}
          <div class="composition-tools">
            ${locked ? '' : '<button class="btn small primary" type="button" data-add-line>+ Custo</button>'}
          </div>
        </div>
        <div class="table-wrap cost-lines-scroll"><table class="data-table cost-input-table industrial"><thead><tr><th>Família</th><th>Descrição</th><th>Consumo</th><th>Un.</th><th>Preço un.</th><th>Custo/peça</th><th>Origem</th><th></th></tr></thead><tbody data-lines>${lines.map(line => editorLine(line, locked, requirementFor(line, requirements))).join('')}</tbody></table></div>
        <details class="proposal-fold" ${finiteNumber(stockSummary.shortage_items) > 0 ? 'open' : ''}>
          <summary>Stock e cobertura${finiteNumber(stockSummary.shortage_items) > 0 ? ` · ${number(stockSummary.shortage_items)} em falta` : ''}</summary>
          <div data-detail-stock>${stockPanel(requirements, stockSummary, {editable:!locked, variance:detail.cost_variance || sheet.cost_variance})}</div>
        </details>
      </section>
      <details class="card proposal-client-doc proposal-fold">
        <summary>
          <div><b>Documento ao cliente</b><small>IVA, pagamento e texto do PDF</small></div>
        </summary>
        <div class="cost-meta-compact client-doc-fields">
          <label>IVA %<input name="vat_pct" type="number" min="0" max="100" step="0.01" value="${finiteNumber(sheet.vat_pct, 23)}" ${locked ? 'disabled' : ''}></label>
          <label>Condições de pagamento<input name="payment_terms" value="${esc(sheet.payment_terms || '30 dias')}" placeholder="30 dias" ${locked ? 'disabled' : ''}></label>
          <label class="full">Texto para o cliente<textarea name="client_notes" rows="2" placeholder="Prazos, embalagem, observações comerciais…" ${locked ? 'disabled' : ''}>${esc(sheet.client_notes || '')}</textarea></label>
        </div>
        <div class="client-doc-preview">
          <div><span>Venda s/ IVA</span><strong data-total-sale>${money(sheet.sales_total)}</strong></div>
          <div><span>IVA (<em data-vat-pct>${number(finiteNumber(sheet.vat_pct, 23))}%</em>)</span><strong data-vat-amount>${money(sheet.vat_amount)}</strong></div>
          <div><span>Total a faturar c/ IVA</span><strong data-total-sale-vat>${money(sheet.sales_total_vat)}</strong></div>
        </div>
        <div class="composition-tools" style="padding:0 12px 10px"><button class="btn small" type="button" data-print>Pré-visualizar PDF</button></div>
      </details>
      <div class="cost-action-dock">
        <div><span>Custo / peça</span><strong data-total-unit>${preciseMoney(sheet.total_cost)}</strong></div>
        <div><span>Custo encomenda</span><strong data-total-proposal>${money(sheet.proposal_total)}</strong></div>
        <div><span>Venda s/ IVA</span><strong data-sale-unit>${preciseMoney(sheet.selling_price)}</strong></div>
        <div><span>Lucro previsto</span><strong data-profit-total>${money(sheet.margin_value)}</strong></div>
        <div><span>Margem</span><strong data-total-margin data-margin-value class="${finiteNumber(sheet.margin_pct) < 20 ? 'risk' : ''}">${number(sheet.margin_pct)}%</strong></div>
        <div class="suggested-price"><span>Preço recomendado</span><strong data-suggested-price>${preciseMoney(pricing.recommended_selling_price)}</strong></div>
        <div class="cost-dock-actions">
          ${sheet.status === 'draft' && canEditCosts() ? '<button class="btn" type="submit">Guardar</button>' : ''}
          ${['rejected','obsolete'].includes(sheet.status) && canEditCosts() ? '<button class="btn" type="button" data-reopen-detail><span data-icon="edit" aria-hidden="true"></span> Editar proposta</button>' : ''}
          ${['draft','approved'].includes(sheet.status) && canAcceptCosts() && !sheet.production_order_id ? '<button class="btn danger" type="button" data-reject-detail>Cliente recusou</button>' : ''}
          ${sheet.status === 'draft' && canAcceptCosts() ? `<button class="btn success" type="button" data-accept-detail ${completeness.can_accept ? '' : 'disabled title="Complete os pontos assinalados antes de aceitar"'}>${completeness.can_accept ? '✓ Aceitar proposta' : 'Ficha incompleta'}</button>` : ''}
          ${['rejected','obsolete'].includes(sheet.status) && canAcceptCosts() ? `<button class="btn success" type="button" data-accept-detail ${completeness.can_accept ? '' : 'disabled title="Complete a ficha antes de aceitar"'}>${completeness.can_accept ? '✓ Aceitar agora' : 'Ficha incompleta'}</button>` : ''}
          ${sheet.status === 'approved' && canAcceptCosts() ? '<button class="btn primary" type="button" data-release-detail>⚡ Lançar em produção</button>' : ''}
          ${sheet.status === 'production' || sheet.production_order_id ? `<button class="btn primary" type="button" data-open-production="${sheet.production_order_id || ''}">Ver ordem de produção →</button>` : ''}
        </div>
      </div>
    </form>
    </div>`;
  const editor = container.querySelector('[data-proposal-editor]');
  const detailStockRoot = container.querySelector('[data-detail-stock]');
  editor.dataset.shortageItems = String(finiteNumber(stockSummary.shortage_items));
  container.querySelector('[data-back]').addEventListener('click', () => renderProposals(container));
  container.querySelectorAll('[data-print]').forEach(button => button.addEventListener('click', () => printProposal(sheet, editor)));
  container.querySelector('[data-email]')?.addEventListener('click', () => {
    if (!valueOf(editor, '[name="customer_id"]')) { toast('Associe um cliente antes de enviar para o exterior.', 'error'); return; }
    const vatPct = numericValue(editor, '[name="vat_pct"]') || finiteNumber(sheet.vat_pct, 23);
    const sale = numericValue(editor, '[name="selling_price"]');
    const qty = numericValue(editor, '[name="quantity"]') || finiteNumber(sheet.quantity_basis, 1);
    const terms = valueOf(editor, '[name="payment_terms"]') || sheet.payment_terms || '30 dias';
    const extra = valueOf(editor, '[name="client_notes"]') || '';
    const subject = encodeURIComponent(`Proposta ${sheet.quote_no} · ${sheet.style_description}`);
    const body = encodeURIComponent(`Olá,\n\nSegue a proposta ${sheet.quote_no} para ${sheet.style_description}.\nQuantidade: ${qty}\nPreço unitário s/ IVA: ${preciseMoney(sale)}\nIVA ${number(vatPct)}%: ${money(sale * qty * vatPct / 100)}\nTotal c/ IVA: ${money(sale * qty * (1 + vatPct / 100))}\nPagamento: ${terms}${extra ? `\n\n${extra}` : ''}\n\nCumprimentos`);
    location.href = `mailto:${sheet.customer_email}?subject=${subject}&body=${body}`;
  });
  editor.querySelector('[name="customer_id"]')?.addEventListener('change', event => {
    const payment = event.target.selectedOptions[0]?.dataset.payment;
    const field = editor.querySelector('[name="payment_terms"]');
    if (payment && field) field.value = payment;
  });
  container.querySelector('[data-duplicate]')?.addEventListener('click', async () => {
    try { const result = await post(`/costing/sheets/${sheet.id}/duplicate`, {}); toast('Nova revisão criada.'); await renderProposalDetail(container, result.sheet.id); }
    catch (error) { toast(error.message, 'error'); }
  });
  container.querySelector('[data-reopen-detail]')?.addEventListener('click', () => reopenProposal(container, sheet.id));
  container.querySelector('[data-reopen-proposal]')?.addEventListener('click', () => reopenProposal(container, sheet.id));
  container.querySelector('[data-reject-detail]')?.addEventListener('click', () => rejectModal(container, sheet, () => renderProposalDetail(container, sheet.id)));
  container.querySelectorAll('[data-cost-group]').forEach(button => button.addEventListener('click', () => {
    const selected = button.dataset.costGroup;
    container.querySelectorAll('[data-cost-group]').forEach(item => item.classList.toggle('active', item === button));
    editor.querySelectorAll('[data-cost-line]').forEach(row => { row.hidden = selected !== 'all' && valueOf(row, '[data-line="group"]') !== selected; });
  }));
  container.querySelectorAll('[data-check-group]').forEach(button => button.addEventListener('click', () => {
    const group = button.dataset.checkGroup;
    const filter = container.querySelector(`[data-cost-group="${group}"]`);
    if (filter) { filter.click(); container.querySelector('.cost-composition-card')?.scrollIntoView({block:'nearest'}); }
  }));
  container.querySelector('[data-proposal-alerts]')?.addEventListener('click', event => {
    if (!event.target.closest('[data-alert-action="stock"]')) return;
    const fold = container.querySelector('.cost-composition-card .proposal-fold');
    if (fold) { fold.open = true; fold.scrollIntoView({ block: 'nearest' }); }
  });
  container.querySelectorAll('[data-open-production]').forEach(button => button.addEventListener('click', () => openProductionOrder(Number(button.dataset.openProduction))));
  if (!locked) {
    editor.addEventListener('input', () => refreshEditorTotals(editor));
    container.querySelector('[data-use-suggested-price]')?.addEventListener('click', () => {
      const field = editor.querySelector('[name="selling_price"]');
      field.value = Number(editor.dataset.suggestedPrice || 0).toFixed(4).replace(/0+$/, '').replace(/\.$/, '');
      refreshEditorTotals(editor);
    });
    container.querySelector('[data-autofill-sheet]')?.addEventListener('click', async event => {
      const button = event.currentTarget;
      button.disabled = true;
      button.textContent = 'A atualizar…';
      try {
        await post(`/costing/sheets/${sheet.id}/autofill`, {});
        toast('Ficha atualizada com BOM, operações, preços e estrutura obrigatória.');
        await renderProposalDetail(container, sheet.id);
      } catch (error) {
        button.disabled = false;
        button.textContent = 'Atualizar da ficha técnica';
        toast(error.message, 'error');
      }
    });
    let stockTimer;
    let stockSequence = 0;
    editor.querySelector('[name="quantity"]').addEventListener('input', () => {
      const sequence = ++stockSequence;
      clearTimeout(stockTimer);
      stockTimer = setTimeout(async () => {
        const quantity = Math.max(1, numericValue(editor, '[name="quantity"]'));
        try {
          const preview = await get(`/costing/sheets/${sheet.id}/production-preview?quantity=${encodeURIComponent(quantity)}`);
          if (sequence !== stockSequence) return;
          const summary = preview.stock_summary || stockSummaryFrom({}, preview.requirements || []);
          summary.quantity = quantity;
          detailStockRoot.innerHTML = stockPanel(preview.requirements || [], summary, {editable:true, variance:preview.cost_variance});
          editor.dataset.shortageItems = String(finiteNumber(summary.shortage_items));
          refreshEditorTotals(editor);
        } catch (error) {
          if (sequence !== stockSequence) return;
          detailStockRoot.innerHTML = `<div class="cost-preview-error"><b>Stock temporariamente indisponível.</b><span>${esc(error.message)}</span></div>`;
        }
      }, 300);
    });
    editor.querySelector('[data-lines]').addEventListener('click', event => {
      const remove = event.target.closest('[data-remove-line]');
      if (remove) { remove.closest('[data-cost-line]').remove(); refreshEditorTotals(editor); }
    });
    detailStockRoot.addEventListener('click', event => {
      const use = event.target.closest('[data-use-stock-cost]');
      if (!use) return;
      const row = editor.querySelector(`[data-cost-line-id="${use.dataset.useStockCost}"]`);
      if (row) { row.querySelector('[data-line="unit_cost"]').value = use.dataset.stockCost; refreshEditorTotals(editor); toast('Custo médio real do stock aplicado à linha.'); }
    });
    editor.querySelector('[data-add-line]').addEventListener('click', () => {
      editor.querySelector('[data-lines]').insertAdjacentHTML('beforeend', editorLine());
      refreshEditorTotals(editor);
    });
    editor.addEventListener('submit', async event => {
      event.preventDefault();
      try { await saveProposal(editor, sheet.id); toast('Ficha guardada com os custos confirmados.'); await renderProposalDetail(container, sheet.id); }
      catch (error) { toast(error.message, 'error'); }
    });
  }
  const openAccept = () => acceptModal(
    container,
    sheet,
    sheet.status === 'draft' ? () => saveProposal(editor, sheet.id) : null,
    () => renderReleaseOrder(container, sheet.id, () => renderProposalDetail(container, sheet.id)),
  );
  container.querySelector('[data-accept-detail]')?.addEventListener('click', openAccept);
  container.querySelector('[data-accept-proposal]')?.addEventListener('click', openAccept);
  const openRelease = async () => {
    try { await renderReleaseOrder(container, sheet.id, () => renderProposalDetail(container, sheet.id)); }
    catch (error) { toast(error.message, 'error'); }
  };
  container.querySelector('[data-release-detail]')?.addEventListener('click', openRelease);
  container.querySelector('[data-release-proposal]')?.addEventListener('click', openRelease);
  refreshEditorTotals(editor);
}

function bindListActions(container, refresh) {
  bindContainer(container, async event => {
    const open = event.target.closest('[data-open-sheet]');
    if (open) { await renderProposalDetail(container, Number(open.dataset.openSheet)); return; }
    if (event.target.closest('[data-new-proposal]')) { chooseProposalType(container); return; }
    if (event.target.closest('[data-view-all]')) { await renderProposals(container); return; }
    const filter = event.target.closest('[data-overview-filter]');
    if (filter) { await renderProposals(container, filter.dataset.overviewFilter); return; }
    const reopen = event.target.closest('[data-reopen-proposal]');
    if (reopen) {
      await reopenProposal(container, Number(reopen.dataset.reopenProposal));
      return;
    }
    const accept = event.target.closest('[data-accept-proposal]');
    if (accept) {
      const sheetId = Number(accept.dataset.acceptProposal);
      const detail = await get(`/costing/sheets/${sheetId}`);
      acceptModal(container, detail.sheet, null, () => renderReleaseOrder(container, sheetId, refresh));
      return;
    }
    const release = event.target.closest('[data-release-proposal]');
    if (release) {
      try {
        await renderReleaseOrder(container, Number(release.dataset.releaseProposal), refresh);
      } catch (error) { toast(error.message, 'error'); }
      return;
    }
    const production = event.target.closest('[data-open-production]');
    if (production) { await openProductionOrder(Number(production.dataset.openProduction)); return; }
    const openOrder = event.target.closest('[data-open-order]');
    if (openOrder) { location.hash = '#/shipping'; return; }
  });
}

export async function renderProposals(container, initialFilter = 'all') {
  const rows = await get(`/costing/${state.companyId}/sheets`);
  const counts = {all:rows.length, draft:0, rejected:0, approved:0, production:0};
  rows.forEach(row => { const stage = stageOf(row); if (stage in counts) counts[stage]++; });
  const newAction = canEditCosts() ? '<button class="btn primary" data-new-proposal>+ Nova ficha de custo</button>' : '';
  container.innerHTML = pageHeader('Propostas e fichas de custo', 'Uma lista compacta com custo, margem, materiais e próximo passo.', newAction) + `
    <div class="proposal-list-toolbar">
      <div class="proposal-stage-filters">
        <button data-proposal-filter="all" class="${initialFilter === 'all' ? 'active' : ''}">Todas <b>${counts.all}</b></button>
        <button data-proposal-filter="draft" class="${initialFilter === 'draft' ? 'active' : ''}">Rascunhos <b>${counts.draft}</b></button>
        <button data-proposal-filter="rejected" class="${initialFilter === 'rejected' ? 'active' : ''}">Recusadas <b>${counts.rejected}</b></button>
        <button data-proposal-filter="approved" class="${initialFilter === 'approved' ? 'active' : ''}">Aceites <b>${counts.approved}</b></button>
        <button data-proposal-filter="production" class="${initialFilter === 'production' ? 'active' : ''}">Em produção <b>${counts.production}</b></button>
      </div>
      <p><i></i> O botão colorido indica o próximo passo disponível.</p>
    </div>
    ${proposalTable(rows)}
    <div class="proposal-filter-empty hidden" data-filter-empty><strong>Sem propostas nesta fase</strong><span>Escolha outro estado ou crie uma nova ficha.</span></div>`;
  const applyFilter = value => {
    let visible = 0;
    container.querySelectorAll('[data-proposal-row]').forEach(row => { row.hidden = value !== 'all' && row.dataset.stage !== value; if (!row.hidden) visible++; });
    container.querySelector('[data-filter-empty]').classList.toggle('hidden', visible > 0 || rows.length === 0);
    container.querySelectorAll('[data-proposal-filter]').forEach(button => button.classList.toggle('active', button.dataset.proposalFilter === value));
  };
  applyFilter(initialFilter);
  bindListActions(container, () => renderProposals(container, initialFilter));
  container.querySelectorAll('[data-proposal-filter]').forEach(button => button.addEventListener('click', () => applyFilter(button.dataset.proposalFilter)));
}
