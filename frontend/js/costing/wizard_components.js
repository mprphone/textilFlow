import { esc, money, number } from '../format.js?v=20260819-6';

export const steps = [
  ['piece', 'Peça e cliente'], ['fabric', 'Malhas'], ['accessories', 'Acessórios'],
  ['production', 'Produção'], ['summary', 'Resumo'],
];

export function stepper(current) {
  return `<div class="wizard-stepper">${steps.map(([key, label], index) => `<div class="${index === current ? 'active' : index < current ? 'done' : ''}"><span>${index < current ? '✓' : index + 1}</span><b>${esc(label)}</b></div>`).join('')}</div>`;
}

export function articleTypeCards(rows, selected) {
  const symbols = {top:'T', dress:'V', trousers:'C', outerwear:'J', accessory:'A'};
  return `<div class="choice-grid piece-choices">${rows.map(row => `<button type="button" class="choice-card ${row.id === selected ? 'selected' : ''}" data-article-type="${row.id}"><span>${symbols[row.category] || row.name.charAt(0)}</span><b>${esc(row.name)}</b><small>${esc(row.category || 'peça')}</small><i>✓</i></button>`).join('')}</div>`;
}

export function selectedComponentRows(items, kind) {
  return items.length ? items.map((item, index) => `<tr data-component-row="${index}">
    <td><div class="selected-material"><span>${item.image_url ? `<img src="${esc(item.image_url)}" alt="">` : esc(item.description.charAt(0))}</span><b>${esc(item.description)}</b></div></td>
    <td><input data-component="quantity" type="number" min="0" step="any" value="${item.quantity}"></td>
    <td><input data-component="unit" value="${esc(item.unit)}"></td>
    <td><input data-component="waste_pct" type="number" min="0" max="100" step="any" value="${item.waste_pct || 0}"></td>
    <td><input data-component="unit_cost" type="number" min="0" step="any" value="${item.unit_cost}"></td>
    <td data-component-total>${money(item.quantity * (1 + (item.waste_pct || 0) / 100) * item.unit_cost)}</td>
    <td><input data-component="color" value="${esc(item.color || '')}" placeholder="Cor"></td>
    <td><button type="button" class="btn small danger" data-remove-${kind}="${index}">×</button></td>
  </tr>`).join('') : `<tr><td colspan="8"><div class="empty"><strong>Nenhum componente selecionado</strong>Clique em + na tabela da esquerda.</div></td></tr>`;
}

export function componentEditor(items, kind, title) {
  return `<div class="selected-components"><div class="section-title"><h3>${esc(title)}</h3><span>${items.length} selecionados</span></div><div class="table-wrap"><table class="data-table wizard-input-table"><thead><tr><th>Componente</th><th>Consumo/peça</th><th>Un.</th><th>Desperdício</th><th>Preço real</th><th>Custo/peça</th><th>Cor</th><th></th></tr></thead><tbody data-${kind}-rows>${selectedComponentRows(items, kind)}</tbody></table></div></div>`;
}

export function productionRows(items) {
  return items.length ? items.map((item, index) => `<tr data-operation-row="${index}"><td><b>${esc(item.description)}</b></td><td><input data-operation-field="quantity" type="number" min="0" step="any" value="${item.quantity}"></td><td><input data-operation-field="unit_cost" type="number" min="0" step="any" value="${item.unit_cost}"></td><td data-operation-total>${money(item.quantity * item.unit_cost)}</td><td><button type="button" class="btn small danger" data-remove-operation="${index}">×</button></td></tr>`).join('') : '<tr><td colspan="5"><div class="empty"><strong>Sem operações</strong>Escolha as operações necessárias.</div></td></tr>';
}

export function subcontractRows(items) {
  return items.length ? items.map((item, index) => `<tr data-service-row="${index}">
    <td><b>${esc(item.description)}</b><small class="table-subline">${esc(item.supplier_name || '')}</small></td>
    <td><input data-service-field="quantity" type="number" min="0" step="any" value="${item.quantity}"></td>
    <td><input data-service-field="unit" value="${esc(item.unit)}"></td>
    <td><input data-service-field="unit_cost" type="number" min="0" step="any" value="${item.unit_cost}"></td>
    <td>${number(item.lead_time_days || 0)} dias</td>
    <td data-service-total>${money(item.quantity * item.unit_cost)}</td>
    <td><button type="button" class="btn small danger" data-remove-service="${index}">×</button></td>
  </tr>`).join('') : '<tr><td colspan="7"><div class="empty"><strong>Sem subcontratos</strong>Escolha um serviço da tabela acima.</div></td></tr>';
}

export function customCostRows(items, kind) {
  return items.length ? items.map((item, index) => `<tr data-custom-row="${index}"><td><input data-custom="description" value="${esc(item.description)}" placeholder="Descrição"></td><td><input data-custom="quantity" type="number" min="0" step="any" value="${item.quantity}"></td><td><input data-custom="unit" value="${esc(item.unit)}"></td><td><input data-custom="unit_cost" type="number" min="0" step="any" value="${item.unit_cost}"></td><td data-custom-total>${money(item.quantity * item.unit_cost)}</td><td><button type="button" class="btn small danger" data-remove-${kind}="${index}">×</button></td></tr>`).join('') : '<tr><td colspan="6"><div class="empty"><strong>Sem custos adicionais</strong>Adicione apenas se forem aplicáveis.</div></td></tr>';
}

export function totals(state) {
  const calculate = items => items.reduce((sum, item) => sum + Number(item.quantity || 0) * (1 + Number(item.waste_pct || 0) / 100) * Number(item.unit_cost || 0), 0);
  const material = calculate([...state.materials, ...state.accessories]);
  const labor = calculate(state.operations);
  const services = calculate(state.services);
  const overhead = calculate(state.overheads);
  const unit = material + labor + services + overhead;
  const sale = Number(state.selling_price || 0);
  return {material, labor, services, overhead, unit, total:unit * state.quantity, saleTotal:sale * state.quantity, margin:sale ? (sale-unit)/sale*100 : 0};
}
