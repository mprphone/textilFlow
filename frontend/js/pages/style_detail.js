import { get, post, crudDelete, crudUpdate } from '../api.js';
import { options } from '../data.js';
import { badge, date, esc, money, number } from '../format.js?v=20260822-1';
import { dynamicFields, fieldsCard, fieldsMarkup, mergeCustomData, readForm } from '../forms.js?v=20260824-1';
import { recordModal } from '../quick_create.js';
import { state } from '../state.js';
import { confirmDelete, pageHeader, toast } from '../ui.js?v=20260822-1';

function rowsTable(headers, rows) {
  return `<div class="table-wrap"><table class="data-table"><thead><tr>${headers.map(item=>`<th>${item}</th>`).join('')}<th></th></tr></thead><tbody>${rows.join('')}</tbody></table></div>`;
}

const STEP_TYPE_LABEL = { cutting: 'Corte', sewing: 'Confeção interna', subcontract: 'Subcontrato' };
const COLOR_HEX = {
  preto: '#1a1a1a', branco: '#f5f5f5', cinzento: '#8a8a8a', cinza: '#8a8a8a',
  azul: '#2f5fa8', azulmarinho: '#1c2e4a', marinho: '#1c2e4a', navy: '#1c2e4a',
  vermelho: '#b5352f', verde: '#3f7a4e', bege: '#d8c7a1', rosa: '#d98aa3', cru: '#e4dcc8',
  amarelo: '#e0c23a', laranja: '#d97a34', roxo: '#7454a0', castanho: '#7a5030', camel: '#b58a55',
};
function colorSwatch(name) {
  const key = (name || '').trim().toLocaleLowerCase('pt').normalize('NFD').replace(/[^a-z]/g, '');
  if (!key) return '#d7dee8';
  if (COLOR_HEX[key]) return COLOR_HEX[key];
  let hash = 0;
  for (const ch of key) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  return `hsl(${hash % 360}, 45%, 55%)`;
}

export async function renderStyleDetail(container, styleId, back, activeTab = 'general') {
  const [data, configuration, route, chainServices, articleTypeOptions, customerOptions] = await Promise.all([
    get(`/products/styles/${styleId}/full`),
    get(`/configuration/${state.companyId}/style`),
    get(`/crud/styles/${styleId}/production-route?company_id=${state.companyId}`).catch(() => []),
    get(`/crud/subcontract-services?company_id=${state.companyId}`).catch(() => []),
    options('article-types', 'name'),
    options('customers', 'name'),
  ]);
  data.production_route = (route && route.length) ? route : [
    { sequence: 10, step_type: 'cutting', is_required: true, notes: '' },
    { sequence: 20, step_type: 'sewing', is_required: true, notes: '' },
  ];
  data.chain_services = chainServices || [];
  const meta = { configuration, articleTypeOptions, customerOptions };
  const style = data.style;
  const tabs = [
    ['general', 'Geral'], ['variants', 'Variantes'], ['technical', 'Ficha Técnica'], ['bom', 'BOM / Componentes'],
    ['production', 'Produção'], ['purchasing', 'Compras & Fornecedores'], ['stock', 'Stock'], ['costs', 'Custos'],
    ['samples', 'Amostras'], ['history', 'Histórico'],
  ];
  container.innerHTML = pageHeader(`${esc(style.reference)}`, style.description, `
    <button class="btn" data-back>← Voltar aos artigos</button>
    <button class="btn" type="button" data-print-style>Imprimir ficha</button>
  `) + `
    <div class="detail-hero">
      <div class="product-image">${style.image_url ? `<img src="${esc(style.image_url)}" alt="">` : '◈'}</div>
      <div class="card detail-title">
        <div class="card-header"><div><h2>${esc(style.description)}</h2><p>${esc(style.collection || '')} · Ficha V${style.technical_version} · Modelo V${style.template_version}</p></div>${badge(style.lifecycle_status)}</div>
        <div class="tag-list"><span class="tag">${esc(style.fabric || 'Sem malha')}</span><span class="tag">${number(style.gsm)} g/m²</span><span class="tag">${esc(style.composition || 'Sem composição')}</span><span class="tag">${esc(style.size_range || 'Sem tamanhos')}</span><span class="tag">${esc(style.workflow_stage)}</span></div>
      </div>
    </div>
    <div class="tabs" style="margin-top:14px">${tabs.map(([key,label])=>`<button class="tab ${key===activeTab?'active':''}" data-detail-tab="${key}">${label}</button>`).join('')}</div>
    <div data-detail-content>${renderTab(activeTab, data, meta)}</div>`;
  container.querySelector('[data-back]').addEventListener('click', back);
  container.querySelector('[data-print-style]')?.addEventListener('click', () => window.print());
  container.querySelectorAll('[data-detail-tab]').forEach(button=>button.addEventListener('click',()=>renderStyleDetail(container,styleId,back,button.dataset.detailTab)));
  await bindActions(container, data, styleId, back, activeTab, meta);
}

function statTile(icon, label, value, hint) {
  return `<article class="style-stat"><span class="style-stat-icon">${icon}</span><div><small>${esc(label)}</small><strong>${value}</strong>${hint ? `<small class="muted">${esc(hint)}</small>` : ''}</div></article>`;
}

function variantMatrixHtml(data, styleId) {
  const matrix = data.variant_matrix || { colors: [], sizes: [], cells: {} };
  const { colors, sizes, cells } = matrix;
  if (!colors.length || !sizes.length) {
    return `<div class="card"><div class="card-header"><h2>Variantes (Cor × Tamanho)</h2><button class="btn primary" data-add-variant-cell>+ Nova variante</button></div><p class="muted" style="padding:0 16px 16px">Ainda sem variantes cor×tamanho. Crie a primeira para começar a grelha.</p></div>`;
  }
  const totalsBySize = sizes.map(size => colors.reduce((sum, color) => sum + (cells[`${color}|${size}`]?.on_hand || 0), 0));
  const grandTotal = totalsBySize.reduce((sum, value) => sum + value, 0);
  return `<div class="card variant-matrix-card">
    <div class="card-header"><h2>Variantes (Cor × Tamanho)</h2><span>Cada célula corresponde a um artigo/variante no Primavera.</span><button class="btn primary" data-add-variant-cell>+ Nova variante</button></div>
    <div class="table-wrap"><table class="data-table variant-matrix"><thead><tr><th>Cor / Tamanho</th>${sizes.map(size => `<th>${esc(size)}</th>`).join('')}<th>Total</th></tr></thead>
    <tbody>${colors.map(color => {
      const rowTotal = sizes.reduce((sum, size) => sum + (cells[`${color}|${size}`]?.on_hand || 0), 0);
      return `<tr><td class="variant-matrix-color"><span class="grade-swatch" style="background:${colorSwatch(color)}"></span>${esc(color)}</td>${sizes.map(size => {
        const cell = cells[`${color}|${size}`];
        if (!cell) return `<td class="variant-cell empty"><button type="button" class="btn small" data-add-variant-cell data-color="${esc(color)}" data-size="${esc(size)}">+</button></td>`;
        const cellState = cell.on_hand > 0 ? 'ok' : cell.in_production > 0 ? 'wip' : 'none';
        return `<td class="variant-cell ${cell.active ? '' : 'inactive'}" data-open-variant="${cell.variant_id}"><b class="variant-cell-sku">${esc(cell.sku)}</b><small class="variant-cell-qty ${cellState}">${number(cell.on_hand)}</small></td>`;
      }).join('')}<td class="variant-matrix-total">${number(rowTotal)}</td></tr>`;
    }).join('')}
    <tr class="variant-matrix-footer"><td>Total (un)</td>${totalsBySize.map(value => `<td>${number(value)}</td>`).join('')}<td>${number(grandTotal)}</td></tr>
    </tbody></table></div>
    <div class="variant-matrix-legend"><span><i class="dot ok"></i> Em stock disponível</span><span><i class="dot wip"></i> Em produção / OF</span><span><i class="dot none"></i> Sem stock</span></div>
    <p class="muted" style="padding:0 16px 14px">Clique numa célula para ver o detalhe da variante (código, EAN, stock por armazém, histórico).</p>
  </div>`;
}

const LIFECYCLE_OPTIONS = ['development', 'approved', 'production', 'inactive'];
const STAGE_OPTIONS = ['novo','proposta_cliente','ficha_tecnica','desenvolvimento_malha','modelagem','corte','confecao','finalizacao','envio_cliente','resposta_cliente','retificacoes','conceito','proto','fitting','size_set','pps','aprovado','produção','arquivado'];

function ensureOption(list, current) {
  return current && !list.includes(current) ? [current, ...list] : list;
}

function styleFieldGroups(style, meta) {
  const core = [
    { key: 'description', label: 'Descrição', required: true },
    { key: 'article_type_id', label: 'Tipo de artigo', type: 'select', options: meta.articleTypeOptions },
    { key: 'customer_id', label: 'Cliente', type: 'select', options: meta.customerOptions },
    { key: 'collection', label: 'Coleção / Época' },
    { key: 'base_unit', label: 'Unidade', default: 'un' },
  ];
  const lifecycle = [
    { key: 'lifecycle_status', label: 'Estado', type: 'select', options: ensureOption(LIFECYCLE_OPTIONS, style.lifecycle_status), default: 'development' },
    { key: 'workflow_stage', label: 'Etapa', type: 'select', options: ensureOption(STAGE_OPTIONS, style.workflow_stage), default: 'novo' },
  ];
  const construction = [
    { key: 'fabric', label: 'Malha base' }, { key: 'composition', label: 'Composição' },
    { key: 'gsm', label: 'Gramagem (g/m²)', type: 'number' }, { key: 'color', label: 'Cor base' },
    { key: 'size_range', label: 'Gama de tamanhos' },
  ];
  const image = [{ key: 'image_url', label: 'Imagem (URL)', type: 'url', full: true }];
  const bySection = new Map();
  for (const field of dynamicFields(meta.configuration.fields, style.custom_data || {})) {
    const title = field.section || 'Outros campos';
    if (!bySection.has(title)) bySection.set(title, []);
    bySection.get(title).push({ ...field, section: undefined });
  }
  const dynamicGroups = [...bySection.entries()].map(([title, fields]) => ({ title, fields }));
  return {
    core, lifecycle, construction, image, dynamicGroups,
    allFields: [...core, ...lifecycle, ...construction, ...image, ...dynamicGroups.flatMap(group => group.fields)],
  };
}

function generalTabHtml(data, meta) {
  const style = data.style;
  const summary = data.summary || {};
  const colors = (data.variant_matrix?.colors || []);
  const { core, lifecycle, construction, image, dynamicGroups } = styleFieldGroups(style, meta);
  return `<form data-style-form>
    <div class="style-general-grid">
      ${fieldsCard('Identificação', core, style)}
      <div class="card"><div class="card-header"><h2>Resumo rápido</h2></div>
        <div class="style-stats-grid">
          ${statTile('📦', 'Stock disponível (total)', `${number(summary.stock_available)} un`)}
          ${statTile('📈', 'Em produção / OF', `${number(summary.in_production_qty)} un`, `${number(summary.in_production_orders)} ordens de fabrico`)}
          ${statTile('€', 'Custo médio atual', money(summary.avg_cost))}
          ${statTile('🛒', 'Última compra', summary.last_purchase_price ? money(summary.last_purchase_price) : '—', summary.last_purchase_date ? `Data: ${date(summary.last_purchase_date)}` : '')}
          ${statTile('📅', 'Última movimentação', summary.last_movement_date ? date(summary.last_movement_date) : '—')}
          ${statTile('🏭', 'Fornecedores ativos', number(summary.active_suppliers), 'Para este artigo')}
        </div>
      </div>
      <div class="card"><div class="card-header"><h2>Imagem e cores</h2></div>
        <div class="form-grid">${fieldsMarkup(image, style)}</div>
        <div class="style-image-preview">${style.image_url ? `<img src="${esc(style.image_url)}" alt="">` : '<span class="style-image-placeholder">◈</span>'}</div>
        <div class="style-color-swatches">${colors.map(color => `<span class="style-color-chip" title="${esc(color)}"><i style="background:${colorSwatch(color)}"></i>${esc(color)}</span>`).join('')}</div>
      </div>
    </div>
    ${fieldsCard('Ciclo de vida', lifecycle, style)}
    ${fieldsCard('Malha e construção', construction, style)}
    ${dynamicGroups.map(group => fieldsCard(group.title, group.fields, {})).join('')}
    <div class="card style-save-bar">
      <div><strong>Atualizar dados do artigo</strong><p class="muted">As alterações aplicam-se de imediato à ficha e às listagens.</p></div>
      <button type="submit" class="btn primary">Guardar alterações</button>
    </div>
  </form>
  ${variantMatrixHtml(data)}`;
}

function technicalTabHtml(style, configuration) {
  return `<div class="grid-2"><div class="card"><div class="card-header"><h2>Ficha técnica</h2><span>Campos estruturais</span></div><div class="custom-fields">${[['Referência',style.reference],['Coleção',style.collection],['Malha',style.fabric],['Composição',style.composition],['Gramagem',`${number(style.gsm)} g/m²`],['Cor',style.color],['Tamanhos',style.size_range],['Etapa',style.workflow_stage]].map(([label,value])=>`<div class="custom-field"><small>${label}</small><strong>${esc(value||'—')}</strong></div>`).join('')}</div></div><div class="card"><div class="card-header"><h2>Campos adaptativos</h2><span>${configuration.fields.length} definidos</span></div><div class="custom-fields">${configuration.fields.map(field=>`<div class="custom-field"><small>${esc(field.label)}</small><strong>${esc(typeof style.custom_data?.[field.field_key]==='object'?JSON.stringify(style.custom_data[field.field_key]):style.custom_data?.[field.field_key]||'—')}</strong></div>`).join('')}</div></div></div>`;
}

function purchasingTabHtml(data) {
  const summary = data.summary || {};
  return `<div class="card"><div class="card-header"><h2>Compras & Fornecedores</h2><span>Baseado nos artigos ligados a cada variante</span></div>
    <div class="style-stats-grid" style="padding:0 16px 16px">
      ${statTile('🏭', 'Fornecedores ativos', number(summary.active_suppliers))}
      ${statTile('🛒', 'Último preço de compra', summary.last_purchase_price ? money(summary.last_purchase_price) : '—', summary.last_purchase_date ? `Data: ${date(summary.last_purchase_date)}` : '')}
      ${statTile('€', 'Custo médio dos artigos', money(summary.avg_cost))}
    </div>
    <p class="muted" style="padding:0 16px 16px">Para o detalhe de cada compra, preço e fornecedor por variante, abra o artigo em Tabelas → Artigos.</p>
  </div>`;
}

function stockTabHtml(data) {
  const matrix = data.variant_matrix || { colors: [], sizes: [], cells: {} };
  const rows = [];
  matrix.colors.forEach(color => matrix.sizes.forEach(size => {
    const cell = matrix.cells[`${color}|${size}`];
    if (cell) rows.push({ color, size, ...cell });
  }));
  return `<div class="card"><div class="card-header"><h2>Stock por variante</h2></div>${rowsTable(
    ['Variante', 'Cor', 'Tamanho', 'Em stock', 'Reservado', 'Em produção', 'Primavera'],
    rows.map(row => `<tr>
      <td><b>${esc(row.sku)}</b></td><td>${esc(row.color)}</td><td>${esc(row.size)}</td>
      <td>${number(row.on_hand)}</td><td>${number(row.reserved)}</td><td>${number(row.in_production)}</td>
      <td>${badge(row.sync_status || 'local')}</td><td></td>
    </tr>`),
  )}</div>`;
}

function renderTab(tab, data, meta) {
  const style = data.style;
  if (tab === 'general') return generalTabHtml(data, meta);
  if (tab === 'variants') return variantMatrixHtml(data);
  if (tab === 'technical') return technicalTabHtml(style, meta.configuration);
  if (tab === 'purchasing') return purchasingTabHtml(data);
  if (tab === 'stock') return stockTabHtml(data);
  if (tab === 'bom') return `<div class="card"><div class="card-header"><h2>Bill of Materials</h2><button class="btn primary" data-add-bom>+ Material</button></div>${rowsTable(['Material','Quantidade','Unidade','Desperdício','Custo unit.','Custo'],data.bom.map(row=>`<tr><td><b>${esc(row.material_code)}</b><br><small>${esc(row.material_name)}</small></td><td>${number(row.quantity)}</td><td>${esc(row.unit)}</td><td>${number(row.waste_pct)}%</td><td>${money(row.unit_cost)}</td><td>${money(row.quantity*(1+row.waste_pct/100)*row.unit_cost)}</td><td><button class="btn small danger" data-delete-resource="bom-items" data-delete-id="${row.id}">Eliminar</button></td></tr>`))}</div>`;
  if (tab === 'production') return `<div class="card"><div class="card-header"><h2>Gama operatória</h2><button class="btn primary" data-add-operation>+ Operação</button></div>${rowsTable(['Seq.','Operação','Máquina','SMV','Objetivo/h','Qualidade'],data.routing.map(row=>`<tr><td>${row.sequence}</td><td><b>${esc(row.operation_code)}</b> · ${esc(row.operation_name)}</td><td>${esc(row.machine_type||'Manual')}</td><td>${number(row.smv)} min</td><td>${number(row.target_units_hour)}</td><td>${row.quality_checkpoint?badge('checkpoint'):'—'}</td><td><button class="btn small danger" data-delete-resource="product-operations" data-delete-id="${row.id}">Eliminar</button></td></tr>`))}<p class="muted">SMV total: <b>${number(data.routing.reduce((sum,row)=>sum+row.smv,0))} minutos</b></p></div>
    <div class="card" style="margin-top:14px"><div class="card-header"><h2>Sequência de produção</h2><button class="btn primary" data-add-chain-step>+ Passo</button><button class="btn" data-save-chain>Guardar sequência</button></div><div data-chain-list>${renderChainList(data.production_route || [], data.chain_services)}</div><p class="muted">A ordem define a sequência obrigatória deste artigo — pode misturar corte, confeção interna e subcontratos. Sem nenhum passo aqui, aplica-se a regra geral: corte sempre antes de qualquer subcontrato.</p></div>`;
  if (tab === 'samples') return `<div class="card"><div class="card-header"><h2>Amostras e aprovações</h2><button class="btn primary" data-add-sample>+ Amostra</button></div>${rowsTable(['Tipo / Versão','Estado','Planeada','Concluída','Tempo','Materiais','Mão de obra','Total'],data.samples.map(row=>`<tr><td><b>${esc(row.sample_type)} ${esc(row.version)}</b></td><td>${badge(row.status)}</td><td>${date(row.planned_date)}</td><td>${date(row.completed_date)}</td><td>${number(row.labor_minutes)} min</td><td>${money(row.material_cost)}</td><td>${money(row.labor_cost)}</td><td><b>${money(row.total_cost)}</b></td><td><button class="btn small danger" data-delete-resource="samples" data-delete-id="${row.id}">Eliminar</button></td></tr>`))}</div>`;
  if (tab === 'costs') return `<div class="card"><div class="card-header"><h2>Folhas de custo</h2><button class="btn primary" data-add-sheet>+ Nova versão</button></div>${rowsTable(['Versão','Estado','Materiais','Mão de obra','Máquina','Subcontrato','Indiretos','Custo total','Venda','Margem'],data.cost_sheets.map(row=>`<tr><td>V${row.version}</td><td>${badge(row.status)}</td><td>${money(row.material_cost)}</td><td>${money(row.labor_cost)}</td><td>${money(row.machine_cost)}</td><td>${money(row.subcontract_cost)}</td><td>${money(row.overhead_cost)}</td><td><b>${money(row.total_cost)}</b></td><td>${money(row.selling_price)}</td><td>${number(row.margin_pct)}%</td><td><button class="btn small" data-rebuild-sheet="${row.id}">Recalcular</button></td></tr>`))}</div>`;
  return `<div class="card"><div class="card-header"><h2>Histórico imutável da ficha</h2><span>As versões antigas permanecem legíveis</span></div>${rowsTable(['Versão','Data','Motivo','Utilizador'],data.revisions.map(row=>`<tr><td><b>V${row.version}</b></td><td>${date(row.created_at)}</td><td>${esc(row.reason||'Alteração')}</td><td>${row.user_id||'—'}</td><td></td></tr>`))}</div>`;
}

function renderChainList(chain, services) {
  if (!chain.length) return '<p class="muted">Nenhum passo configurado.</p>';
  return rowsTable(['Seq.','Tipo','Serviço (só subcontrato)','Categoria','Obrigatório','Notas',''], chain.map((step, idx) => {
    const type = step.step_type || 'subcontract';
    const isSub = type === 'subcontract';
    return `<tr data-chain-idx="${idx}">
    <td><input type="number" data-chain-seq value="${step.sequence || (idx + 1) * 10}" style="width:60px"></td>
    <td><select data-chain-type>${Object.entries(STEP_TYPE_LABEL).map(([value,label]) => `<option value="${value}" ${value === type ? 'selected' : ''}>${label}</option>`).join('')}</select></td>
    <td><select data-chain-service ${isSub ? '' : 'disabled'}>${(services || []).map(s => `<option value="${s.id}" ${s.id === step.subcontract_service_id ? 'selected' : ''}>${esc(s.code)} · ${esc(s.name)}</option>`).join('')}</select></td>
    <td>${isSub ? esc((services || []).find(s => s.id === step.subcontract_service_id)?.category || '—') : '—'}</td>
    <td><input type="checkbox" data-chain-required ${step.is_required ? 'checked' : ''}></td>
    <td><input type="text" data-chain-notes value="${esc(step.notes || '')}" style="width:100%"></td>
    <td><button class="btn small danger" data-chain-remove="${idx}">×</button></td>
  </tr>`;
  }));
}

async function bindActions(container, data, styleId, back, activeTab, meta) {
  const refresh=()=>renderStyleDetail(container,styleId,back,activeTab);
  container.querySelector('[data-style-form]')?.addEventListener('submit', async event => {
    event.preventDefault();
    const { allFields } = styleFieldGroups(data.style, meta);
    try {
      let payload = readForm(event.currentTarget, allFields);
      payload = mergeCustomData(payload, data.style.custom_data);
      await crudUpdate('styles', styleId, payload);
      toast('Artigo atualizado.');
      refresh();
    } catch (error) { toast(error.message, 'error'); }
  });
  container.querySelector('[data-add-bom]')?.addEventListener('click',async()=>recordModal({title:'Adicionar material à ficha',resource:'bom-items',values:{style_id:styleId},fields:[{key:'material_id',label:'Material',type:'select',required:true,options:await options('materials',r=>`${r.code} · ${r.name}`)},{key:'quantity',label:'Quantidade',type:'number',required:true},{key:'unit',label:'Unidade',required:true,default:'kg'},{key:'waste_pct',label:'Desperdício (%)',type:'number',default:0},{key:'unit_cost',label:'Custo unitário',type:'number',default:0},{key:'notes',label:'Notas',type:'textarea',full:true},{key:'style_id',label:'Artigo',type:'hidden'}],onSaved:refresh}));
  container.querySelector('[data-add-operation]')?.addEventListener('click',async()=>recordModal({title:'Adicionar operação à gama',resource:'product-operations',values:{style_id:styleId},fields:[{key:'operation_id',label:'Operação',type:'select',required:true,options:await options('operations',r=>`${r.code} · ${r.name}`)},{key:'sequence',label:'Sequência',type:'number',default:10},{key:'smv',label:'SMV (min)',type:'number',default:0},{key:'target_units_hour',label:'Objetivo/h',type:'number',default:0},{key:'skill_level',label:'Nível',type:'select',options:['basic','standard','advanced'],default:'standard'},{key:'quality_checkpoint',label:'Checkpoint qualidade',type:'checkbox'},{key:'style_id',label:'Artigo',type:'hidden'}],onSaved:refresh}));
  container.querySelectorAll('[data-add-variant-cell]').forEach(button => button.addEventListener('click', () => {
    recordModal({
      title: 'Nova variante', resource: 'style-variants',
      values: { style_id: styleId, active: true, color: button.dataset.color || '', size: button.dataset.size || '' },
      fields: [{key:'sku',label:'SKU (deixe em branco para gerar)',help:'Se ficar vazio, o backend não gera automaticamente aqui — use Cor/Tamanho e depois "Nova variante" na grelha da OF/Encomenda para SKU automático.'},{key:'color',label:'Cor'},{key:'size',label:'Tamanho'},{key:'barcode',label:'Código de barras'},{key:'active',label:'Ativa',type:'checkbox'},{key:'style_id',label:'Artigo',type:'hidden'}],
      onSaved:refresh,
    });
  }));
  container.querySelectorAll('[data-open-variant]').forEach(cell => cell.addEventListener('click', () => {
    const variant = data.variants.find(row => row.id === Number(cell.dataset.openVariant));
    if (!variant) return;
    recordModal({
      title: `Variante · ${variant.sku}`, resource: 'style-variants', recordId: variant.id, values: variant,
      fields: [{key:'sku',label:'SKU',required:true},{key:'color',label:'Cor'},{key:'size',label:'Tamanho'},{key:'barcode',label:'Código de barras'},{key:'active',label:'Ativa',type:'checkbox'},{key:'style_id',label:'Artigo',type:'hidden'}],
      onSaved:refresh,
    });
  }));
  container.querySelector('[data-add-sample]')?.addEventListener('click',async()=>recordModal({title:'Nova amostra',resource:'samples',values:{style_id:styleId,status:'requested',version:'V1'},fields:[{key:'sample_type',label:'Tipo',type:'select',required:true,options:['proto','fitting','size_set','salesman','pps']},{key:'version',label:'Versão',required:true},{key:'status',label:'Estado',type:'select',options:['requested','in_progress','sent','approved','rejected']},{key:'responsible_employee_id',label:'Responsável',type:'select',options:await options('employees','name')},{key:'planned_date',label:'Planeada',type:'date'},{key:'completed_date',label:'Concluída',type:'date'},{key:'labor_minutes',label:'Minutos',type:'number',default:0},{key:'labor_cost',label:'Custo mão de obra',type:'number',default:0},{key:'material_cost',label:'Custo materiais',type:'number',default:0},{key:'external_cost',label:'Custo externo',type:'number',default:0},{key:'comments',label:'Comentários',type:'textarea',full:true},{key:'style_id',label:'Artigo',type:'hidden'}],onSaved:refresh}));
  container.querySelector('[data-add-sheet]')?.addEventListener('click',()=>recordModal({title:'Nova folha de custo',resource:'cost-sheets',values:{style_id:styleId,version:(data.cost_sheets[0]?.version||0)+1,status:'draft'},fields:[{key:'version',label:'Versão',type:'number',required:true},{key:'status',label:'Estado',type:'select',options:['draft','approved','obsolete']},{key:'quantity_basis',label:'Quantidade base',type:'number',default:1},{key:'selling_price',label:'Preço venda',type:'number',default:0},{key:'style_id',label:'Artigo',type:'hidden'}],onSaved:refresh}));
  container.querySelectorAll('[data-rebuild-sheet]').forEach(button=>button.addEventListener('click',async()=>{try{await post(`/products/cost-sheets/${button.dataset.rebuildSheet}/rebuild`,{});toast('Custo recalculado a partir da BOM e gama.');refresh();}catch(error){toast(error.message,'error')}}));
  container.querySelectorAll('[data-delete-resource]').forEach(button=>button.addEventListener('click',async()=>{if(!confirmDelete('este elemento'))return;try{await crudDelete(button.dataset.deleteResource,Number(button.dataset.deleteId),state.companyId);toast('Elemento eliminado.');refresh();}catch(error){toast(error.message,'error')}}));

  if (activeTab === 'production') {
    const chainServices = data.chain_services || [];
    container.querySelector('[data-add-chain-step]')?.addEventListener('click', () => {
      data.production_route = data.production_route || [];
      data.production_route.push({ sequence: (data.production_route.length + 1) * 10, step_type: 'subcontract', subcontract_service_id: chainServices[0]?.id, is_required: true, notes: '' });
      container.querySelector('[data-chain-list]').innerHTML = renderChainList(data.production_route, chainServices);
      bindChainActions(container, data, styleId, chainServices);
    });
    container.querySelector('[data-save-chain]')?.addEventListener('click', async () => {
      const rows = container.querySelectorAll('[data-chain-idx]');
      const payload = [];
      rows.forEach((row, idx) => {
        const stepType = row.querySelector('[data-chain-type]').value;
        payload.push({
          sequence: Number(row.querySelector('[data-chain-seq]').value) || (idx + 1) * 10,
          step_type: stepType,
          subcontract_service_id: stepType === 'subcontract' ? Number(row.querySelector('[data-chain-service]').value) : null,
          is_required: row.querySelector('[data-chain-required]').checked,
          notes: row.querySelector('[data-chain-notes]').value,
        });
      });
      try {
        await post(`/crud/styles/${styleId}/production-route?company_id=${state.companyId}`, payload);
        toast('Sequência de produção guardada');
        refresh();
      } catch (error) { toast(error.message, 'error'); }
    });
    bindChainActions(container, data, styleId, chainServices);
  }
}

function bindChainActions(container, data, styleId, chainServices) {
  container.querySelectorAll('[data-chain-remove]').forEach(button => button.addEventListener('click', () => {
    const idx = Number(button.dataset.chainRemove);
    data.production_route.splice(idx, 1);
    container.querySelector('[data-chain-list]').innerHTML = renderChainList(data.production_route, chainServices);
    bindChainActions(container, data, styleId, chainServices);
  }));
  container.querySelectorAll('[data-chain-type]').forEach(select => select.addEventListener('change', () => {
    const row = select.closest('[data-chain-idx]');
    const idx = Number(row.dataset.chainIdx);
    data.production_route[idx].step_type = select.value;
    data.production_route[idx].subcontract_service_id = select.value === 'subcontract' ? (chainServices[0]?.id) : null;
    container.querySelector('[data-chain-list]').innerHTML = renderChainList(data.production_route, chainServices);
    bindChainActions(container, data, styleId, chainServices);
  }));
}
