import { crudList, get, put } from '../api.js';
import { esc, money } from '../format.js?v=20260821-22';
import { recordModal } from '../quick_create.js?v=20260821-19';
import { state } from '../state.js';
import { empty, pageHeader, toast } from '../ui.js?v=20260821-19';

const GROUPS = [
  ['fabric', 'Malha / tecido'],
  ['accessory', 'Acessório'],
  ['labor', 'Mão de obra'],
  ['machine', 'Máquina'],
  ['dyeing', 'Tinturaria'],
  ['printing', 'Estamparia'],
  ['subcontract', 'Outro subcontrato'],
  ['overhead', 'Custo indireto'],
];

const GROUP_LABELS = Object.fromEntries(GROUPS);
const GROUP_ICONS = {
  fabric:'layers', accessory:'box', labor:'user', machine:'settings', dyeing:'droplet',
  printing:'layers', subcontract:'truck', overhead:'euro',
};

let host;
let model = { types:[], materials:[], operations:[], services:[], templates:{}, selectedId:null, template:null, rows:[] };

function numeric(value, fallback = 0) {
  const parsed = Number(String(value ?? '').replace(',', '.'));
  return Number.isFinite(parsed) ? parsed : fallback;
}

function activeRows(rows) { return (rows || []).filter(row => row.active !== false); }

function typeFields() {
  return [
    {key:'code', label:'Código', required:true, placeholder:'POLO'},
    {key:'name', label:'Nome do tipo de peça', required:true, placeholder:'Polo'},
    {key:'category', label:'Família / categoria', placeholder:'Top, calças, vestido…'},
    {key:'default_unit', label:'Unidade de produção', default:'un', required:true},
    {key:'active', label:'Disponível para novas propostas', type:'checkbox', default:true, full:true},
  ];
}

function openTypeModal(row = null) {
  recordModal({
    title: row ? 'Editar tipo de peça' : 'Novo tipo de peça',
    subtitle:'O modelo de custos é configurado a seguir, sem voltar a introduzir tudo em cada proposta.',
    resource:'article-types', recordId:row?.id || null, values:row || {active:true, default_unit:'un'}, fields:typeFields(),
    transform:payload=>({
      ...payload,
      code:String(payload.code || '').trim().toUpperCase(),
      name:String(payload.name || '').trim(),
      category:String(payload.category || '').trim() || null,
    }),
    onSaved:async saved=>{
      await loadData(saved?.id || row?.id || null);
      renderPage();
    },
  });
}

async function loadTemplate(articleTypeId) {
  model.template = await get(`/costing/article-types/${articleTypeId}/cost-template`);
  model.templates[String(articleTypeId)] = model.template;
  model.rows = (model.template.lines || []).map(row=>({...row}));
}

async function loadData(preferredId = null) {
  const [types, catalog] = await Promise.all([
    crudList('article-types', state.companyId, 'limit=2000'),
    get(`/costing/${state.companyId}/wizard-catalog`).catch(()=>null),
  ]);
  model.types = types.sort((a,b)=>Number(b.active)-Number(a.active) || String(a.name).localeCompare(String(b.name), 'pt'));
  if (catalog) {
    model.materials = catalog.materials || [];
    model.operations = catalog.operations || [];
    model.services = catalog.subcontract_services || [];
    model.templates = {...(catalog.article_type_templates || {})};
  } else {
    [model.materials, model.operations, model.services] = await Promise.all([
      crudList('materials', state.companyId, 'limit=2000'),
      crudList('operations', state.companyId, 'limit=2000'),
      crudList('subcontract-services', state.companyId, 'limit=2000'),
    ]);
    model.templates = {};
  }
  const missingTypes = model.types.filter(row=>!model.templates[String(row.id)]);
  const templateEntries = await Promise.all(missingTypes.map(async row=>[
    String(row.id), await get(`/costing/article-types/${row.id}/cost-template`).catch(()=>null),
  ]));
  Object.assign(model.templates, Object.fromEntries(templateEntries.filter(([,value])=>value)));
  const wanted = Number(preferredId || model.selectedId);
  model.selectedId = model.types.some(row=>Number(row.id)===wanted) ? wanted : model.types[0]?.id || null;
  if (model.selectedId) {
    model.template = model.templates[String(model.selectedId)] || await get(`/costing/article-types/${model.selectedId}/cost-template`);
    model.rows = (model.template.lines || []).map(row=>({...row}));
  }
  else { model.template = null; model.rows = []; }
}

function referenceKind(group) {
  if (['fabric','accessory'].includes(group)) return 'material';
  if (['labor','machine'].includes(group)) return 'operation';
  if (['dyeing','printing','subcontract'].includes(group)) return 'service';
  return null;
}

function referenceRows(group) {
  const kind = referenceKind(group);
  if (kind === 'material') {
    return model.materials.filter(row=>row.active !== false && (group !== 'fabric' || ['fabric','raw_material','semi_finished'].includes(row.category) || row.tf_type === 'raw_material'));
  }
  if (kind === 'operation') return model.operations.filter(row=>row.active !== false);
  if (kind === 'service') {
    const rows = model.services.filter(row=>row.active !== false);
    return rows;
  }
  return [];
}

function selectedReference(row) {
  if (row.material_id) return `material:${row.material_id}`;
  if (row.operation_id) return `operation:${row.operation_id}`;
  if (row.subcontract_service_id) return `service:${row.subcontract_service_id}`;
  return '';
}

function referenceOptions(row) {
  const kind = referenceKind(row.cost_group);
  if (!kind) return '<option value="">Valor manual</option>';
  const rows = referenceRows(row.cost_group);
  const selected = selectedReference(row);
  const inactive = selected && !rows.some(item=>`${kind}:${item.id}`===selected)
    ? `<option value="${selected}" selected>${esc(row.reference_label || 'Referência inativa')} · inativa</option>` : '';
  return `<option value="">Escolher na proposta / custo manual</option>${inactive}${rows.map(item=>{
    const code = item.code ? `${item.code} · ` : '';
    return `<option value="${kind}:${item.id}" ${selected===`${kind}:${item.id}`?'selected':''}>${esc(code+item.name)}</option>`;
  }).join('')}`;
}

function groupOptions(selected) {
  return GROUPS.map(([value,label])=>`<option value="${value}" ${value===selected?'selected':''}>${label}</option>`).join('');
}

function rowCost(row) {
  const unitCost = row.use_live_price ? numeric(row.effective_unit_cost, row.unit_cost) : numeric(row.unit_cost);
  return numeric(row.quantity) * (1 + numeric(row.waste_pct) / 100) * unitCost;
}

function costRow(row, index) {
  const priceHint = row.use_live_price ? (row.price_origin === 'stock_weighted_average' ? 'Média do stock' : 'Preço atual') : 'Preço fixo';
  const displayPrice = row.use_live_price ? numeric(row.effective_unit_cost, row.unit_cost) : numeric(row.unit_cost);
  return `<tr data-cost-row="${index}">
    <td class="atc-kind"><span class="atc-kind-icon" data-icon="${GROUP_ICONS[row.cost_group] || 'box'}"></span><select data-field="cost_group" aria-label="Família de custo">${groupOptions(row.cost_group)}</select></td>
    <td><select data-field="reference" aria-label="Artigo, operação ou serviço">${referenceOptions(row)}</select></td>
    <td><input data-field="description" value="${esc(row.description || '')}" aria-label="Descrição do custo" placeholder="Descrição"></td>
    <td><div class="atc-quantity"><input data-field="quantity" type="number" min="0" step="0.0001" value="${numeric(row.quantity)}" aria-label="Consumo"><input data-field="unit" value="${esc(row.unit || 'un')}" aria-label="Unidade"></div></td>
    <td><input data-field="waste_pct" type="number" min="0" max="100" step="0.1" value="${numeric(row.waste_pct)}" aria-label="Desperdício"></td>
    <td><div class="atc-price"><input data-field="unit_cost" type="number" min="0" step="0.0001" value="${displayPrice}" aria-label="Preço unitário"><small>${esc(priceHint)}</small></div></td>
    <td class="atc-center"><label class="switch-compact" title="Atualizar com o preço atual do stock ou cadastro"><input data-field="use_live_price" type="checkbox" ${row.use_live_price?'checked':''}><span></span></label></td>
    <td class="atc-center"><label class="switch-compact" title="Impede aceitar uma proposta quando este custo estiver por preencher"><input data-field="required" type="checkbox" ${row.required?'checked':''}><span></span></label></td>
    <td class="atc-total">${money(rowCost(row))}</td>
    <td><button class="btn icon danger subtle" type="button" data-remove-cost="${index}" data-icon="delete" aria-label="Remover custo" title="Remover custo"></button></td>
  </tr>`;
}

function typeList() {
  if (!model.types.length) return empty('Ainda não existem tipos de peças', 'Crie o primeiro tipo e defina os custos que devem aparecer automaticamente.');
  return model.types.map(row=>{const template=model.templates[String(row.id)]||{};const costCount=(template.lines||[]).length;return `<button class="piece-type-item ${Number(row.id)===Number(model.selectedId)?'active':''}" type="button" data-select-type="${row.id}">
    <span class="piece-type-monogram">${esc((row.name || '?').slice(0,1).toUpperCase())}</span>
    <span class="piece-type-copy"><strong>${esc(row.name)}</strong><small>${esc(row.code)}${row.category ? ` · ${esc(row.category)}` : ''}</small></span>
    ${row.active === false ? '<span class="piece-type-off">Inativo</span>' : `<span class="piece-type-meta ${template.configured?'ready':''}" title="${template.configured?'Modelo configurado':'Modelo base sugerido'}">${costCount}<i data-icon="${template.configured?'check':'layers'}"></i></span>`}
  </button>`;}).join('');
}

function templateSummary() {
  const rows = activeRows(model.rows);
  const required = rows.filter(row=>row.required).length;
  const total = rows.reduce((sum,row)=>sum+rowCost(row),0);
  return `<div class="atc-summary">
    <div><small>Custos previstos</small><strong>${rows.length}</strong></div>
    <div><small>Obrigatórios</small><strong>${required}</strong></div>
    <div><small>Base por peça</small><strong>${money(total)}</strong></div>
  </div>`;
}

function renderEditor() {
  const slot = host.querySelector('[data-type-editor]');
  const type = model.types.find(row=>Number(row.id)===Number(model.selectedId));
  if (!type) {
    slot.innerHTML = `<div class="piece-type-welcome"><span data-icon="layers"></span><h2>Crie um tipo de peça</h2><p>Depois poderá indicar todos os custos que uma proposta desse tipo deve ter.</p><button class="btn primary" data-new-type type="button"><span data-icon="add"></span>Novo tipo de peça</button></div>`;
    bindEditor();
    return;
  }
  const configured = model.template?.configured;
  slot.innerHTML = `<section class="piece-type-editor">
    <header class="piece-type-editor-head">
      <div><div class="eyebrow">${esc(type.code)} · ${esc(type.category || 'Sem categoria')}</div><h2>${esc(type.name)}</h2><p>Estes custos entram automaticamente quando este tipo é escolhido numa proposta.</p></div>
      <div class="actions"><button class="btn" type="button" data-edit-type><span data-icon="edit"></span>Editar tipo</button><button class="btn primary" type="button" data-save-template><span data-icon="save"></span>Guardar modelo</button></div>
    </header>
    <div class="atc-state ${configured?'configured':'suggested'}"><span data-icon="${configured?'check':'layers'}"></span><div><strong>${configured?'Modelo configurado':'Modelo base sugerido'}</strong><small>${configured?'As novas propostas usam estas linhas e os preços atuais assinalados.':'Revise os consumos e guarde. Até lá, o programa usa esta base segura e marca o que ficar por preencher.'}</small></div>${configured?'<button class="btn link" type="button" data-reset-template>Repor modelo base</button>':''}</div>
    ${templateSummary()}
    <div class="atc-table-wrap"><table class="atc-table"><thead><tr><th>Tipo de custo</th><th>Artigo / operação / serviço</th><th>Descrição</th><th>Consumo</th><th>Quebra %</th><th>Preço un.</th><th title="Usar preço atual">Atual</th><th title="Obrigatório na proposta">Obrig.</th><th>Custo/peça</th><th></th></tr></thead><tbody>${model.rows.map(costRow).join('')}</tbody></table></div>
    <footer class="atc-footer"><button class="btn dashed" type="button" data-add-cost><span data-icon="add"></span>Adicionar tipo de custo</button><div><span>Os preços com “Atual” são recalculados pelo stock, operação ou fornecedor.</span><button class="btn primary" type="button" data-save-template><span data-icon="save"></span>Guardar modelo</button></div></footer>
  </section>`;
  bindEditor();
}

function collectRows() {
  host.querySelectorAll('[data-cost-row]').forEach(tr=>{
    const row = model.rows[Number(tr.dataset.costRow)];
    if (!row) return;
    const field = name=>tr.querySelector(`[data-field="${name}"]`);
    row.cost_group = field('cost_group').value;
    row.description = field('description').value.trim();
    row.quantity = numeric(field('quantity').value);
    row.unit = field('unit').value.trim() || 'un';
    row.waste_pct = numeric(field('waste_pct').value);
    row.unit_cost = numeric(field('unit_cost').value);
    row.use_live_price = field('use_live_price').checked;
    if (!selectedReference(row) || !row.use_live_price) row.effective_unit_cost = row.unit_cost;
    row.required = field('required').checked;
    row.active = true;
  });
}

function setReference(row, value) {
  row.material_id = null; row.operation_id = null; row.subcontract_service_id = null;
  if (!value) return;
  const [kind, rawId] = value.split(':');
  const id = Number(rawId);
  let reference;
  if (kind === 'material') { row.material_id = id; reference = model.materials.find(item=>item.id===id); }
  if (kind === 'operation') { row.operation_id = id; reference = model.operations.find(item=>item.id===id); }
  if (kind === 'service') { row.subcontract_service_id = id; reference = model.services.find(item=>item.id===id); }
  if (!reference) return;
  row.description = reference.name || row.description;
  if (kind === 'material') { row.unit = reference.unit || row.unit; row.unit_cost = numeric(reference.effective_unit_cost ?? reference.last_cost ?? reference.unit_cost); }
  if (kind === 'operation') { row.unit = 'min'; row.quantity = numeric(reference.standard_time_min, row.quantity); row.unit_cost = numeric(row.cost_group === 'machine' ? reference.machine_cost_per_minute : reference.cost_per_minute); }
  if (kind === 'service') { row.unit = reference.unit || row.unit; row.unit_cost = numeric(reference.unit_cost); }
  row.effective_unit_cost = row.unit_cost;
}

function newCost() {
  return {cost_group:'accessory', role_key:null, material_id:null, operation_id:null, subcontract_service_id:null, description:'Novo custo', quantity:1, unit:'un', waste_pct:0, unit_cost:0, effective_unit_cost:0, use_live_price:true, required:true, sequence:(model.rows.length+1)*10, active:true};
}

async function saveTemplate() {
  collectRows();
  const invalid = model.rows.find(row=>!row.description || !row.unit);
  if (invalid) { toast('Preencha a descrição e a unidade de todos os custos.', 'error'); return; }
  const lines = model.rows.map((row,index)=>({
    cost_group:row.cost_group, role_key:row.role_key || null, material_id:row.material_id || null,
    operation_id:row.operation_id || null, subcontract_service_id:row.subcontract_service_id || null,
    description:row.description, quantity:numeric(row.quantity), unit:row.unit, waste_pct:numeric(row.waste_pct),
    unit_cost:numeric(row.unit_cost), use_live_price:Boolean(row.use_live_price), required:Boolean(row.required), sequence:(index+1)*10, active:true,
  }));
  try {
    model.template = await put(`/costing/article-types/${model.selectedId}/cost-template`, {lines});
    model.templates[String(model.selectedId)] = model.template;
    model.rows = (model.template.lines || []).map(row=>({...row}));
    toast('Modelo de custos guardado. Será carregado nas novas propostas deste tipo.');
    renderPage();
  } catch (error) { toast(error.message, 'error'); }
}

function bindEditor() {
  host.querySelectorAll('[data-new-type]').forEach(button=>button.addEventListener('click',()=>openTypeModal()));
  host.querySelector('[data-edit-type]')?.addEventListener('click',()=>openTypeModal(model.types.find(row=>Number(row.id)===Number(model.selectedId))));
  host.querySelectorAll('[data-save-template]').forEach(button=>button.addEventListener('click',saveTemplate));
  host.querySelector('[data-add-cost]')?.addEventListener('click',()=>{ collectRows(); model.rows.push(newCost()); renderEditor(); host.querySelector('[data-cost-row]:last-child input[data-field="description"]')?.select(); });
  host.querySelector('[data-reset-template]')?.addEventListener('click',()=>{
    if (!window.confirm('Repor o modelo base? As alterações atuais deste tipo serão substituídas quando guardar.')) return;
    model.rows = (model.template?.suggested_lines || []).map(row=>({...row})); renderEditor();
  });
  host.querySelectorAll('[data-remove-cost]').forEach(button=>button.addEventListener('click',()=>{
    collectRows(); model.rows.splice(Number(button.dataset.removeCost),1); renderEditor();
  }));
  host.querySelectorAll('[data-field="cost_group"]').forEach(select=>select.addEventListener('change',event=>{
    collectRows(); const index=Number(event.target.closest('[data-cost-row]').dataset.costRow); const row=model.rows[index];
    row.material_id=null; row.operation_id=null; row.subcontract_service_id=null; row.role_key=null; row.cost_group=event.target.value; row.unit=['labor','machine'].includes(row.cost_group)?'min':'un'; row.unit_cost=0; row.effective_unit_cost=0;
    renderEditor();
  }));
  host.querySelectorAll('[data-field="reference"]').forEach(select=>select.addEventListener('change',event=>{
    collectRows(); const index=Number(event.target.closest('[data-cost-row]').dataset.costRow); setReference(model.rows[index],event.target.value); renderEditor();
  }));
  host.querySelectorAll('.atc-table input').forEach(input=>input.addEventListener('change',()=>{ collectRows(); renderEditor(); }));
}

function renderPage() {
  host.innerHTML = `${pageHeader('Tipos de peças e modelos de custo','Defina uma vez o que cada peça consome. As propostas ficam pré-preenchidas, valorizadas pelo stock e validadas antes de aceitar.','<button class="btn primary" type="button" data-new-type><span data-icon="add"></span>Novo tipo de peça</button>')}
    <div class="piece-types-layout">
      <aside class="piece-types-sidebar"><div class="piece-types-sidebar-head"><div><small>TIPOS DE PEÇA</small><strong>${model.types.length}</strong></div><button class="btn icon" type="button" data-new-type data-icon="add" aria-label="Novo tipo de peça" title="Novo tipo de peça"></button></div><div class="piece-type-list">${typeList()}</div></aside>
      <div data-type-editor></div>
    </div>`;
  host.querySelectorAll('[data-new-type]').forEach(button=>button.addEventListener('click',()=>openTypeModal()));
  host.querySelectorAll('[data-select-type]').forEach(button=>button.addEventListener('click',async()=>{
    try { model.selectedId=Number(button.dataset.selectType); await loadTemplate(model.selectedId); renderPage(); }
    catch(error) { toast(error.message,'error'); }
  }));
  renderEditor();
}

export async function render(container) {
  host = container;
  await loadData();
  renderPage();
}
