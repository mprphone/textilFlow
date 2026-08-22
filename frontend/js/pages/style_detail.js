import { get, post, crudDelete } from '../api.js';
import { options } from '../data.js';
import { badge, date, esc, money, number } from '../format.js?v=20260822-1';
import { recordModal } from '../quick_create.js';
import { state } from '../state.js';
import { confirmDelete, pageHeader, toast } from '../ui.js?v=20260822-1';

function rowsTable(headers, rows) {
  return `<div class="table-wrap"><table class="data-table"><thead><tr>${headers.map(item=>`<th>${item}</th>`).join('')}<th></th></tr></thead><tbody>${rows.join('')}</tbody></table></div>`;
}

const STEP_TYPE_LABEL = { cutting: 'Corte', sewing: 'Confeção interna', subcontract: 'Subcontrato' };

export async function renderStyleDetail(container, styleId, back, activeTab = 'summary') {
  const [data, configuration, route, chainServices] = await Promise.all([
    get(`/products/styles/${styleId}/full`),
    get(`/configuration/${state.companyId}/style`),
    get(`/crud/styles/${styleId}/production-route`).catch(() => []),
    get(`/crud/subcontract-services?company_id=${state.companyId}`).catch(() => []),
  ]);
  data.production_route = (route && route.length) ? route : [
    { sequence: 10, step_type: 'cutting', is_required: true, notes: '' },
    { sequence: 20, step_type: 'sewing', is_required: true, notes: '' },
  ];
  data.chain_services = chainServices || [];
  const style = data.style;
  const tabs = [['summary','Resumo'],['bom','Materiais / BOM'],['routing','Gama operatória'],['chain','Sequência de produção'],['variants','Variantes'],['samples','Amostras'],['costs','Custos'],['history','Histórico']];
  container.innerHTML = pageHeader(`REF. ${style.reference}`, style.description, '<button class="btn" data-back>← Voltar aos artigos</button>') + `
    <div class="detail-hero"><div class="product-image">◈</div><div class="card detail-title"><div class="card-header"><div><h2>${esc(style.description)}</h2><p>${esc(style.collection || '')} · Ficha V${style.technical_version} · Modelo V${style.template_version}</p></div>${badge(style.lifecycle_status)}</div><div class="tag-list"><span class="tag">${esc(style.fabric || 'Sem malha')}</span><span class="tag">${number(style.gsm)} g/m²</span><span class="tag">${esc(style.composition || 'Sem composição')}</span><span class="tag">${esc(style.size_range || 'Sem tamanhos')}</span><span class="tag">${esc(style.workflow_stage)}</span></div></div></div>
    <div class="tabs" style="margin-top:14px">${tabs.map(([key,label])=>`<button class="tab ${key===activeTab?'active':''}" data-detail-tab="${key}">${label}</button>`).join('')}</div>
    <div data-detail-content>${renderTab(activeTab, data, configuration)}</div>`;
  container.querySelector('[data-back]').addEventListener('click', back);
  container.querySelectorAll('[data-detail-tab]').forEach(button=>button.addEventListener('click',()=>renderStyleDetail(container,styleId,back,button.dataset.detailTab)));
  await bindActions(container, data, styleId, back, activeTab);
}

function renderTab(tab, data, configuration) {
  const style = data.style;
  if (tab === 'summary') return `<div class="grid-2"><div class="card"><div class="card-header"><h2>Ficha técnica</h2><span>Campos estruturais</span></div><div class="custom-fields">${[['Referência',style.reference],['Coleção',style.collection],['Malha',style.fabric],['Composição',style.composition],['Gramagem',`${number(style.gsm)} g/m²`],['Cor',style.color],['Tamanhos',style.size_range],['Etapa',style.workflow_stage]].map(([label,value])=>`<div class="custom-field"><small>${label}</small><strong>${esc(value||'—')}</strong></div>`).join('')}</div></div><div class="card"><div class="card-header"><h2>Campos adaptativos</h2><span>${configuration.fields.length} definidos</span></div><div class="custom-fields">${configuration.fields.map(field=>`<div class="custom-field"><small>${esc(field.label)}</small><strong>${esc(typeof style.custom_data?.[field.field_key]==='object'?JSON.stringify(style.custom_data[field.field_key]):style.custom_data?.[field.field_key]||'—')}</strong></div>`).join('')}</div></div></div>`;
  if (tab === 'bom') return `<div class="card"><div class="card-header"><h2>Bill of Materials</h2><button class="btn primary" data-add-bom>+ Material</button></div>${rowsTable(['Material','Quantidade','Unidade','Desperdício','Custo unit.','Custo'],data.bom.map(row=>`<tr><td><b>${esc(row.material_code)}</b><br><small>${esc(row.material_name)}</small></td><td>${number(row.quantity)}</td><td>${esc(row.unit)}</td><td>${number(row.waste_pct)}%</td><td>${money(row.unit_cost)}</td><td>${money(row.quantity*(1+row.waste_pct/100)*row.unit_cost)}</td><td><button class="btn small danger" data-delete-resource="bom-items" data-delete-id="${row.id}">Eliminar</button></td></tr>`))}</div>`;
  if (tab === 'routing') return `<div class="card"><div class="card-header"><h2>Gama operatória</h2><button class="btn primary" data-add-operation>+ Operação</button></div>${rowsTable(['Seq.','Operação','Máquina','SMV','Objetivo/h','Qualidade'],data.routing.map(row=>`<tr><td>${row.sequence}</td><td><b>${esc(row.operation_code)}</b> · ${esc(row.operation_name)}</td><td>${esc(row.machine_type||'Manual')}</td><td>${number(row.smv)} min</td><td>${number(row.target_units_hour)}</td><td>${row.quality_checkpoint?badge('checkpoint'):'—'}</td><td><button class="btn small danger" data-delete-resource="product-operations" data-delete-id="${row.id}">Eliminar</button></td></tr>`))}<p class="muted">SMV total: <b>${number(data.routing.reduce((sum,row)=>sum+row.smv,0))} minutos</b></p></div>`;
  if (tab === 'chain') return `<div class="card"><div class="card-header"><h2>Sequência de produção</h2><button class="btn primary" data-add-chain-step>+ Passo</button><button class="btn" data-save-chain>Guardar sequência</button></div><div data-chain-list>${renderChainList(data.production_route || [], data.chain_services)}</div><p class="muted">A ordem define a sequência obrigatória deste artigo — pode misturar corte, confeção interna e subcontratos (ex.: tingir a malha antes de cortar, ou confecionar e só depois tingir a peça). Cada passo só fica disponível quando o anterior tiver terminado. Sem nenhum passo aqui, aplica-se a regra geral: corte sempre antes de qualquer subcontrato.</p></div>`;
  if (tab === 'variants') return `<div class="card"><div class="card-header"><h2>Cores, tamanhos e SKU</h2><button class="btn primary" data-add-variant>+ Variante</button></div>${rowsTable(['SKU','Cor','Tamanho','Código de barras','Estado'],data.variants.map(row=>`<tr><td><b>${esc(row.sku)}</b></td><td>${esc(row.color)}</td><td>${esc(row.size)}</td><td>${esc(row.barcode||'—')}</td><td>${badge(row.active?'ativa':'inativa')}</td><td><button class="btn small danger" data-delete-resource="style-variants" data-delete-id="${row.id}">Eliminar</button></td></tr>`))}</div>`;
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

async function bindActions(container, data, styleId, back, activeTab) {
  const refresh=()=>renderStyleDetail(container,styleId,back,activeTab);
  container.querySelector('[data-add-bom]')?.addEventListener('click',async()=>recordModal({title:'Adicionar material à ficha',resource:'bom-items',values:{style_id:styleId},fields:[{key:'material_id',label:'Material',type:'select',required:true,options:await options('materials',r=>`${r.code} · ${r.name}`)},{key:'quantity',label:'Quantidade',type:'number',required:true},{key:'unit',label:'Unidade',required:true,default:'kg'},{key:'waste_pct',label:'Desperdício (%)',type:'number',default:0},{key:'unit_cost',label:'Custo unitário',type:'number',default:0},{key:'notes',label:'Notas',type:'textarea',full:true},{key:'style_id',label:'Artigo',type:'hidden'}],onSaved:refresh}));
  container.querySelector('[data-add-operation]')?.addEventListener('click',async()=>recordModal({title:'Adicionar operação à gama',resource:'product-operations',values:{style_id:styleId},fields:[{key:'operation_id',label:'Operação',type:'select',required:true,options:await options('operations',r=>`${r.code} · ${r.name}`)},{key:'sequence',label:'Sequência',type:'number',default:10},{key:'smv',label:'SMV (min)',type:'number',default:0},{key:'target_units_hour',label:'Objetivo/h',type:'number',default:0},{key:'skill_level',label:'Nível',type:'select',options:['basic','standard','advanced'],default:'standard'},{key:'quality_checkpoint',label:'Checkpoint qualidade',type:'checkbox'},{key:'style_id',label:'Artigo',type:'hidden'}],onSaved:refresh}));
  container.querySelector('[data-add-variant]')?.addEventListener('click',()=>recordModal({title:'Nova variante',resource:'style-variants',values:{style_id:styleId,active:true},fields:[{key:'sku',label:'SKU',required:true},{key:'color',label:'Cor'},{key:'size',label:'Tamanho'},{key:'barcode',label:'Código de barras'},{key:'active',label:'Ativa',type:'checkbox'},{key:'style_id',label:'Artigo',type:'hidden'}],onSaved:refresh}));
  container.querySelector('[data-add-sample]')?.addEventListener('click',async()=>recordModal({title:'Nova amostra',resource:'samples',values:{style_id:styleId,status:'requested',version:'V1'},fields:[{key:'sample_type',label:'Tipo',type:'select',required:true,options:['proto','fitting','size_set','salesman','pps']},{key:'version',label:'Versão',required:true},{key:'status',label:'Estado',type:'select',options:['requested','in_progress','sent','approved','rejected']},{key:'responsible_employee_id',label:'Responsável',type:'select',options:await options('employees','name')},{key:'planned_date',label:'Planeada',type:'date'},{key:'completed_date',label:'Concluída',type:'date'},{key:'labor_minutes',label:'Minutos',type:'number',default:0},{key:'labor_cost',label:'Custo mão de obra',type:'number',default:0},{key:'material_cost',label:'Custo materiais',type:'number',default:0},{key:'external_cost',label:'Custo externo',type:'number',default:0},{key:'comments',label:'Comentários',type:'textarea',full:true},{key:'style_id',label:'Artigo',type:'hidden'}],onSaved:refresh}));
  container.querySelector('[data-add-sheet]')?.addEventListener('click',()=>recordModal({title:'Nova folha de custo',resource:'cost-sheets',values:{style_id:styleId,version:(data.cost_sheets[0]?.version||0)+1,status:'draft'},fields:[{key:'version',label:'Versão',type:'number',required:true},{key:'status',label:'Estado',type:'select',options:['draft','approved','obsolete']},{key:'quantity_basis',label:'Quantidade base',type:'number',default:1},{key:'selling_price',label:'Preço venda',type:'number',default:0},{key:'style_id',label:'Artigo',type:'hidden'}],onSaved:refresh}));
  container.querySelectorAll('[data-rebuild-sheet]').forEach(button=>button.addEventListener('click',async()=>{try{await post(`/products/cost-sheets/${button.dataset.rebuildSheet}/rebuild`,{});toast('Custo recalculado a partir da BOM e gama.');refresh();}catch(error){toast(error.message,'error')}}));
  container.querySelectorAll('[data-delete-resource]').forEach(button=>button.addEventListener('click',async()=>{if(!confirmDelete('este elemento'))return;try{await crudDelete(button.dataset.deleteResource,Number(button.dataset.deleteId),state.companyId);toast('Elemento eliminado.');refresh();}catch(error){toast(error.message,'error')}}));

  if (activeTab === 'chain') {
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
        await post(`/crud/styles/${styleId}/production-route`, payload);
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
