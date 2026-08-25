import { get, post } from '../api.js';
import { esc, money, number } from '../format.js?v=20260819-6';
import { state as appState } from '../state.js';
import { pageHeader, toast } from '../ui.js?v=20260820-5';
import { recordModal } from '../quick_create.js';
import { articleTypeCards, componentEditor, customCostRows, productionRows, stepper, subcontractRows, totals } from './wizard_components.js?v=20260825-56';
import { filterCatalog, materialCatalogTable, operationCatalogTable, subcontractCatalogTable } from './wizard_catalogs.js?v=20260825-55';


function blankState() {
  const validUntil = new Date();
  validUntil.setDate(validUntil.getDate() + 30);
  return {
    article_type_id:null, customer_id:null, reference:'', description:'', quantity:1000,
    selling_price:0, valid_until:validUntil.toISOString().slice(0,10), piece_image_url:'', color:'', notes:'',
    financial_cost_pct:2, markup_pct:35, commission_pct:0,
    materials:[], accessories:[], operations:[], services:[], overheads:[],
  };
}

function fromMaterial(row) {
  const configured = Number(row.custom_data?.default_consumption);
  return {material_id:row.id, description:row.name, quantity:Number.isFinite(configured) ? configured : (row.category === 'fabric' ? 0.5 : 1), unit:row.unit, unit_cost:Number(row.effective_unit_cost ?? row.unit_cost ?? 0), waste_pct:row.category === 'fabric' ? 5 : 0, image_url:row.image_url || null, color:row.color || ''};
}

function fromService(row) {
  return {subcontract_service_id:row.id,description:row.name,supplier_name:row.supplier_name,quantity:1,unit:row.unit,unit_cost:row.unit_cost,waste_pct:0,lead_time_days:row.lead_time_days};
}

function applyCostingTemplate(data, catalog, articleTypeId) {
  const template = catalog.article_type_templates?.[String(articleTypeId)];
  const lines = template?.lines || [];
  const component = item => ({
    template_cost_id:item.id || null, cost_group:item.cost_group,
    material_id:item.material_id || null, operation_id:item.operation_id || null,
    subcontract_service_id:item.subcontract_service_id || null,
    description:item.description, quantity:Number(item.quantity || 0), unit:item.unit || 'un',
    unit_cost:Number(item.effective_unit_cost ?? item.unit_cost ?? 0), waste_pct:Number(item.waste_pct || 0),
    image_url:catalog.materials.find(row => row.id === item.material_id)?.image_url || null,
    color:'', required:item.required !== false,
  });
  data.materials = lines.filter(item => item.cost_group === 'fabric' && item.material_id).map(component);
  data.accessories = lines.filter(item => item.cost_group === 'accessory').map(component);
  data.operations = lines.filter(item => ['labor','machine'].includes(item.cost_group)).map(component);
  data.services = lines.filter(item => ['dyeing','printing','subcontract'].includes(item.cost_group)).map(item => ({
    ...component(item),
    supplier_name:catalog.subcontract_services.find(row => row.id === item.subcontract_service_id)?.supplier_name || '',
    lead_time_days:catalog.subcontract_services.find(row => row.id === item.subcontract_service_id)?.lead_time_days || 0,
  }));
  data.overheads = lines.filter(item => item.cost_group === 'overhead').map(component);
  Object.assign(data, catalog.costing_template?.pricing || {});
}

function suggestedPrice(data) {
  const base = totals(data).unit;
  const divisor = 1 - Math.min(99, Math.max(0, Number(data.commission_pct || 0))) / 100;
  return divisor > 0 ? base * (1 + Number(data.financial_cost_pct || 0) / 100 + Number(data.markup_pct || 0) / 100) / divisor : 0;
}

function stepContent(step, data, catalog, ui) {
  if (step === 0) return `<div class="wizard-intro"><span>1</span><div><h2>Que peça vamos orçamentar?</h2><p>Ao escolher o tipo, o programa carrega malhas, acessórios, operações, serviços e custos indiretos definidos em <a href="#/tables-article-types">Tabelas → Tipos de peças</a>.</p></div></div>
    ${articleTypeCards(catalog.article_types, data.article_type_id, catalog.article_type_templates)}
    <div class="wizard-form card"><div class="cost-meta-grid">
      <label>Cliente *<select data-header="customer_id"><option value="">Selecionar cliente…</option>${catalog.customers.map(row => `<option value="${row.id}" ${row.id===data.customer_id?'selected':''}>${esc(row.name)}</option>`).join('')}</select></label>
      <label>Referência do modelo<input data-header="reference" value="${esc(data.reference)}" placeholder="Ex.: POLO-2027-01"></label>
      <label class="cost-notes">Designação *<input data-header="description" value="${esc(data.description)}" placeholder="Ex.: Polo Piquet Manga Curta"></label>
      <label>Quantidade *<input data-header="quantity" type="number" min="1" value="${data.quantity}"></label>
      <label>Cor principal<input data-header="color" value="${esc(data.color)}" placeholder="Ex.: Azul marinho"></label>
      <label class="cost-notes">Fotografia da peça<input data-header="piece_image_url" value="${esc(data.piece_image_url)}" placeholder="Cole um endereço de imagem"></label>
    </div>${data.piece_image_url ? `<div class="piece-preview"><img src="${esc(data.piece_image_url)}" alt="Pré-visualização"><span>Pré-visualização da peça</span></div>` : ''}</div>`;

  if (step === 1) {
    const fabrics = filterCatalog(catalog.materials.filter(row => row.category === 'fabric'), ui.fabric.search);
    return `<div class="wizard-intro"><span>2</span><div><h2>Escolha as malhas</h2><p>O preço vem da ficha do material; pode substituí-lo nesta proposta.</p></div><button class="btn small" data-new-material="fabric">+ Nova malha</button></div>
      <div class="wizard-pick">
        <div>
          <div class="catalog-tools"><div class="table-search"><span>⌕</span><input data-catalog-search="fabric" value="${esc(ui.fabric.search)}" placeholder="Procurar malha, composição ou fornecedor…"></div><span>Stock atualizado</span></div>
          ${materialCatalogTable(fabrics, data.materials.map(item=>item.material_id), 'fabric', ui.fabric.page)}
        </div>
        <div class="wizard-pick-selected">${componentEditor(data.materials, 'fabric', 'Malhas na proposta')}</div>
      </div>`;
  }

  if (step === 2) {
    const accessories = filterCatalog(catalog.materials.filter(row => row.category !== 'fabric'), ui.accessory.search);
    return `<div class="wizard-intro"><span>3</span><div><h2>Escolha acessórios e embalagem</h2><p>Linhas, etiquetas, botões e embalagens ligam-se ao stock e à ordem de produção.</p></div><button class="btn small" data-new-material="accessory">+ Novo acessório</button></div>
      <div class="wizard-pick">
        <div>
          <div class="catalog-tools"><div class="table-search"><span>⌕</span><input data-catalog-search="accessory" value="${esc(ui.accessory.search)}" placeholder="Procurar acessório…"></div><span>${accessories.length} encontrados</span></div>
          ${materialCatalogTable(accessories, data.accessories.map(item=>item.material_id), 'accessory', ui.accessory.page)}
        </div>
        <div class="wizard-pick-selected">${componentEditor(data.accessories, 'accessory', 'Acessórios na proposta')}</div>
      </div>`;
  }

  if (step === 3) {
    const operations = filterCatalog(catalog.operations, ui.operation.search);
    const subcontractServices = filterCatalog(catalog.subcontract_services || [], ui.subcontract.search);
    return `<div class="wizard-intro"><span>4</span><div><h2>Como será produzida?</h2><p>Selecione operações e serviços. Os valores podem ser ajustados só nesta proposta.</p></div></div>
    <div class="wizard-subsection">
      <div class="section-title"><h3>Operações e tempos</h3><span>${operations.length} encontradas</span></div>
      <div class="wizard-pick">
        <div>
          <div class="catalog-tools"><div class="table-search"><span>⌕</span><input data-catalog-search="operation" value="${esc(ui.operation.search)}" placeholder="Procurar operação, código ou secção…"></div></div>
          ${operationCatalogTable(operations, data.operations.map(item=>item.operation_id), ui.operation.page)}
        </div>
        <div class="wizard-pick-selected"><div class="table-wrap"><table class="data-table wizard-input-table"><thead><tr><th>Operação</th><th>Min/peça</th><th>€/min</th><th>€/peça</th><th></th></tr></thead><tbody data-operation-rows>${productionRows(data.operations)}</tbody></table></div></div>
      </div>
    </div>
    <div class="wizard-subsection wizard-spaced">
      <div class="section-title"><h3>Serviços subcontratados</h3><div class="section-actions"><button class="btn small" data-open-subcontracts>Tabela completa</button><button class="btn small" data-new-subcontract>+ Novo serviço</button></div></div>
      <div class="wizard-pick">
        <div>
          <div class="catalog-tools"><div class="table-search"><span>⌕</span><input data-catalog-search="subcontract" value="${esc(ui.subcontract.search)}" placeholder="Procurar serviço ou fornecedor…"></div><span>${subcontractServices.length} encontrados</span></div>
          ${subcontractCatalogTable(subcontractServices, data.services.map(item=>item.subcontract_service_id), ui.subcontract.page)}
        </div>
        <div class="wizard-pick-selected"><div class="table-wrap"><table class="data-table wizard-input-table"><thead><tr><th>Serviço</th><th>Qtd.</th><th>Un.</th><th>Preço</th><th>Prazo</th><th>Total</th><th></th></tr></thead><tbody data-services-rows>${subcontractRows(data.services)}</tbody></table></div></div>
      </div>
    </div>
    <div class="wizard-subsection wizard-spaced"><div class="section-title"><h3>Custos gerais imputados</h3><button class="btn small" data-add-custom="overheads">+ Custo</button></div><div class="table-wrap"><table class="data-table wizard-input-table"><thead><tr><th>Descrição</th><th>Qtd.</th><th>Un.</th><th>Preço</th><th>Total</th><th></th></tr></thead><tbody data-overheads-rows>${customCostRows(data.overheads,'overhead')}</tbody></table></div></div>`;
  }

  const total = totals(data);
  const suggested = suggestedPrice(data);
  const type = catalog.article_types.find(row => row.id === data.article_type_id);
  const customer = catalog.customers.find(row => row.id === data.customer_id);
  const allComponents = [...data.materials, ...data.accessories];
  return `<div class="wizard-intro"><span>5</span><div><h2>Confirme a proposta</h2><p>Revise o custo por peça, defina o preço de venda e crie a ficha. Poderá editar o rascunho e gerar PDF.</p></div></div>
    <div class="proposal-preview">
      <div class="proposal-cover">${data.piece_image_url ? `<img src="${esc(data.piece_image_url)}" alt="${esc(data.description)}">` : `<div class="piece-placeholder">${esc((type?.name || 'P').charAt(0))}</div>`}<span>${esc(data.color || 'Cor por definir')}</span></div>
      <div class="proposal-info"><span class="decision-eyebrow">PROPOSTA EM PREPARAÇÃO</span><h2>${esc(data.description)}</h2><p>${esc(type?.name || '')} · ${esc(customer?.name || '')}</p><div><span><small>Quantidade</small><b>${number(data.quantity)}</b></span><span><small>Componentes</small><b>${allComponents.length}</b></span><span><small>Tempo</small><b>${number(data.operations.reduce((sum,item)=>sum+Number(item.quantity||0),0))} min</b></span></div></div>
      <div class="proposal-price"><label>Venda por peça *<input data-header="selling_price" type="number" min="0" step="any" value="${data.selling_price}"><button type="button" class="wizard-use-price" data-wizard-use-price>Usar recomendado · ${money(suggested)}</button></label><label>Válida até<input data-header="valid_until" type="date" value="${esc(data.valid_until)}"></label></div>
    </div>
    <div class="cost-breakdown-cards"><div><span>Materiais e acessórios</span><strong>${money(total.material)}</strong></div><div><span>Produção</span><strong>${money(total.labor)}</strong></div><div><span>Subcontratos</span><strong>${money(total.services)}</strong></div><div><span>Custos gerais</span><strong>${money(total.overhead)}</strong></div></div>
    <div class="wizard-final-totals"><div><span>Custo por peça</span><strong data-wizard-unit>${money(total.unit)}</strong></div><div><span>Preço recomendado</span><strong>${money(suggested)}</strong><small>${number(data.financial_cost_pct)}% encargos · ${number(data.markup_pct)}% acréscimo · ${number(data.commission_pct)}% comissão</small></div><div><span>Venda total</span><strong data-wizard-sale>${money(total.saleTotal)}</strong></div><div><span>Margem</span><strong class="${total.margin < 20 ? 'cost-bad':'cost-good'}" data-wizard-margin>${number(total.margin)}%</strong></div></div>
    <div class="wizard-notes"><label>Notas e condições<textarea data-header="notes" placeholder="Prazos, condições de pagamento, observações para o cliente…">${esc(data.notes)}</textarea></label></div>`;
}

function syncRows(root, items, rowSelector, fieldAttribute) {
  root.querySelectorAll(rowSelector).forEach((row, index) => {
    row.querySelectorAll(`[${fieldAttribute}]`).forEach(input => {
      const key = input.getAttribute(fieldAttribute);
      items[index][key] = input.type === 'number' ? Number(input.value || 0) : input.value;
    });
  });
}

function bindHeader(root, data) {
  root.querySelectorAll('[data-header]').forEach(input => input.addEventListener('input', () => {
    const key = input.dataset.header;
    data[key] = ['customer_id','quantity','selling_price'].includes(key) ? Number(input.value || 0) : input.value;
    if (key === 'selling_price') {
      const total = totals(data);
      root.querySelector('[data-wizard-sale]').textContent = money(total.saleTotal);
      root.querySelector('[data-wizard-margin]').textContent = `${number(total.margin)}%`;
      root.querySelector('[data-wizard-margin]').className = total.margin < 20 ? 'cost-bad' : 'cost-good';
    }
  }));
}

function createMaterial(kind, catalog, rerender) {
  const isFabric = kind === 'fabric';
  recordModal({
    title:isFabric ? 'Criar nova malha' : 'Criar novo acessório', resource:'materials',
    values:{category:isFabric?'fabric':'trim',unit:isFabric?'kg':'un',active:true},
    fields:[
      {key:'code',label:'Código',required:true,section:'Identificação'},{key:'name',label:'Designação',required:true,section:'Identificação'},
      {key:'category',label:'Categoria',type:'select',options:isFabric?['fabric']:['thread','trim','label','packaging','other'],section:'Identificação'},
      {key:'supplier_id',label:'Fornecedor',type:'select',options:catalog.suppliers.map(row=>({value:row.id,label:row.name})),section:'Compra e stock'},
      {key:'unit',label:'Unidade',required:true,section:'Compra e stock'},{key:'unit_cost',label:'Preço real',type:'number',default:0,section:'Compra e stock'},
      {key:'minimum_stock',label:'Stock mínimo',type:'number',default:0,section:'Compra e stock'},{key:'lead_time_days',label:'Prazo do fornecedor (dias)',type:'number',default:0,section:'Compra e stock'},
      {key:'composition',label:'Composição',section:'Características'},{key:'gsm',label:'Gramagem g/m²',type:'number',section:'Características'},
      {key:'width_m',label:'Largura (m)',type:'number',section:'Características'},{key:'color',label:'Cor',section:'Características'},
      {key:'photo_url',label:'Fotografia / endereço',type:'url',section:'Características',full:true},{key:'active',label:'Estado',type:'checkbox',default:true,help:'Material ativo',section:'Controlo'},
    ],
    transform:payload=>{payload.custom_data={image_url:payload.photo_url||null};delete payload.photo_url;return payload;},
    onSaved:row=>{const supplier=catalog.suppliers.find(item=>item.id===row.supplier_id);catalog.materials.push({...row,available_stock:0,supplier_name:supplier?.name||'Sem fornecedor',image_url:row.custom_data?.image_url||null});toast('Material criado e disponível para seleção.');rerender();},
  });
}

function createSubcontractService(catalog, rerender) {
  recordModal({
    title:'Criar serviço subcontratado', resource:'subcontract-services',
    values:{category:'other',unit:'un',unit_cost:0,minimum_quantity:0,lead_time_days:0,quality_score:100,active:true},
    fields:[
      {key:'code',label:'Código',required:true,section:'Identificação'},{key:'name',label:'Serviço',required:true,section:'Identificação'},
      {key:'supplier_id',label:'Fornecedor',type:'select',required:true,options:catalog.suppliers.map(row=>({value:row.id,label:row.name})),section:'Identificação'},
      {key:'category',label:'Tipo',type:'select',options:['sewing','dyeing','printing','embroidery','laundry','finishing','transport','other'],section:'Condições'},
      {key:'unit',label:'Unidade',required:true,section:'Condições'},{key:'unit_cost',label:'Preço acordado',type:'number',required:true,section:'Condições'},
      {key:'minimum_quantity',label:'Quantidade mínima',type:'number',section:'Condições'},{key:'lead_time_days',label:'Prazo (dias)',type:'number',section:'Condições'},
      {key:'quality_score',label:'Qualidade (%)',type:'number',section:'Controlo'},{key:'active',label:'Estado',type:'checkbox',default:true,help:'Serviço disponível',section:'Controlo'},
      {key:'notes',label:'Notas / condições',type:'textarea',full:true,section:'Controlo'},
    ],
    onSaved:row=>{const supplier=catalog.suppliers.find(item=>item.id===row.supplier_id);catalog.subcontract_services.push({...row,supplier_name:supplier?.name||'Fornecedor desconhecido',supplier_score:supplier?.score||0});toast('Serviço adicionado à tabela de subcontratos.');rerender();},
  });
}

function validate(step, data) {
  if (step === 0 && (!data.article_type_id || !data.customer_id || !data.description.trim() || data.quantity <= 0)) return 'Escolha o tipo de peça, o cliente, a designação e a quantidade.';
  if (step === 1 && !data.materials.length) return 'Selecione pelo menos uma malha.';
  if (step === 4 && data.selling_price <= 0) return 'Introduza o preço de venda por peça.';
  return null;
}

export async function renderProposalWizard(container, onDone, onCancel) {
  const catalog = await get(`/costing/${appState.companyId}/wizard-catalog`);
  const data = blankState();
  const ui = {
    fabric:{search:'',page:1}, accessory:{search:'',page:1},
    operation:{search:'',page:1}, subcontract:{search:'',page:1},
  };
  let current = 0;

  const render = () => {
    container.innerHTML = pageHeader('Nova proposta guiada', 'Construa o custo com dados reais, passo a passo.', '<button class="btn" data-cancel-wizard>Cancelar</button>', 'compact') + `<div class="proposal-wizard">${stepper(current)}<div class="wizard-body">${stepContent(current,data,catalog,ui)}</div><footer class="wizard-footer"><span>Passo ${current+1} de 5</span><div>${current ? '<button class="btn" data-wizard-back>← Anterior</button>' : ''}<button class="btn primary" data-wizard-next>${current === 4 ? 'Criar ficha de custo' : 'Continuar →'}</button></div></footer></div>`;
    const root = container.querySelector('.proposal-wizard');
    bindHeader(root,data);
    root.querySelector('[data-wizard-use-price]')?.addEventListener('click',()=>{data.selling_price=Number(suggestedPrice(data).toFixed(4));render();});
    container.querySelector('[data-cancel-wizard]').addEventListener('click', onCancel);
    container.querySelector('[data-wizard-back]')?.addEventListener('click',()=>{current--;render();});
    root.querySelectorAll('[data-article-type]').forEach(button=>button.addEventListener('click',()=>{const nextType=Number(button.dataset.articleType);if(nextType!==data.article_type_id)applyCostingTemplate(data,catalog,nextType);data.article_type_id=nextType;const type=catalog.article_types.find(r=>r.id===data.article_type_id);if(!data.description)data.description=type.name;render();}));
    root.querySelectorAll('[data-catalog-search]').forEach(input=>input.addEventListener('input',event=>{const kind=event.target.dataset.catalogSearch;ui[kind].search=event.target.value;ui[kind].page=1;render();requestAnimationFrame(()=>{const next=container.querySelector(`[data-catalog-search="${kind}"]`);next?.focus();next?.setSelectionRange(next.value.length,next.value.length);});}));
    root.querySelectorAll('[data-catalog-page]').forEach(button=>button.addEventListener('click',()=>{ui[button.dataset.catalogKind].page=Number(button.dataset.catalogPage);render();}));
    root.querySelectorAll('[data-add-fabric]').forEach(button=>button.addEventListener('click',()=>{const row=catalog.materials.find(r=>r.id===Number(button.dataset.addFabric));if(!data.materials.some(i=>i.material_id===row.id))data.materials.push(fromMaterial(row));render();}));
    root.querySelectorAll('[data-add-accessory]').forEach(button=>button.addEventListener('click',()=>{const row=catalog.materials.find(r=>r.id===Number(button.dataset.addAccessory));if(!data.accessories.some(i=>i.material_id===row.id))data.accessories.push(fromMaterial(row));render();}));
    root.querySelector('[data-new-material]')?.addEventListener('click',event=>createMaterial(event.target.dataset.newMaterial,catalog,render));
    root.querySelectorAll('[data-remove-fabric]').forEach(button=>button.addEventListener('click',()=>{data.materials.splice(Number(button.dataset.removeFabric),1);render();}));
    root.querySelectorAll('[data-remove-accessory]').forEach(button=>button.addEventListener('click',()=>{data.accessories.splice(Number(button.dataset.removeAccessory),1);render();}));
    root.querySelectorAll('[data-operation]').forEach(button=>button.addEventListener('click',()=>{const id=Number(button.dataset.operation);const index=data.operations.findIndex(i=>i.operation_id===id);if(index>=0)data.operations.splice(index,1);else{const row=catalog.operations.find(r=>r.id===id);data.operations.push({operation_id:id,description:row.name,quantity:row.standard_time_min,unit:'min',unit_cost:row.cost_per_minute,waste_pct:0});}render();}));
    root.querySelectorAll('[data-subcontract]').forEach(button=>button.addEventListener('click',()=>{const id=Number(button.dataset.subcontract);const index=data.services.findIndex(i=>i.subcontract_service_id===id);if(index>=0)data.services.splice(index,1);else{const row=catalog.subcontract_services.find(r=>r.id===id);data.services.push(fromService(row));}render();}));
    root.querySelector('[data-new-subcontract]')?.addEventListener('click',()=>createSubcontractService(catalog,render));
    root.querySelector('[data-open-subcontracts]')?.addEventListener('click',()=>window.open(`${location.origin}${location.pathname}#/subcontracts`,'_blank'));
    root.querySelectorAll('[data-remove-operation]').forEach(button=>button.addEventListener('click',()=>{data.operations.splice(Number(button.dataset.removeOperation),1);render();}));
    root.querySelectorAll('[data-add-custom]').forEach(button=>button.addEventListener('click',()=>{data[button.dataset.addCustom].push({description:'',quantity:1,unit:'un',unit_cost:0,waste_pct:0});render();}));
    root.querySelectorAll('[data-remove-service]').forEach(button=>button.addEventListener('click',()=>{data.services.splice(Number(button.dataset.removeService),1);render();}));
    root.querySelectorAll('[data-remove-overhead]').forEach(button=>button.addEventListener('click',()=>{data.overheads.splice(Number(button.dataset.removeOverhead),1);render();}));
    root.addEventListener('input',()=>{
      syncRows(root,data.materials,'[data-fabric-rows] [data-component-row]','data-component');
      syncRows(root,data.accessories,'[data-accessory-rows] [data-component-row]','data-component');
      syncRows(root,data.operations,'[data-operation-rows] [data-operation-row]','data-operation-field');
      syncRows(root,data.services,'[data-services-rows] [data-service-row]','data-service-field');
      syncRows(root,data.overheads,'[data-overheads-rows] [data-custom-row]','data-custom');
    });
    root.querySelector('[data-wizard-next]').addEventListener('click',async()=>{
      root.dispatchEvent(new Event('input'));
      const error=validate(current,data);if(error){toast(error,'error');return;}
      if(current<4){current++;if(current===4 && data.selling_price<=0)data.selling_price=Number(suggestedPrice(data).toFixed(4));render();return;}
      try{root.querySelector('[data-wizard-next]').disabled=true;const payload={...data,services:data.services.filter(item=>item.description?.trim()),overheads:data.overheads.filter(item=>item.description?.trim())};const result=await post('/costing/wizard',{company_id:appState.companyId,...payload});toast('Ficha de custo criada. Pode agora rever, imprimir ou aprovar.');await onDone(result);}
      catch(error){root.querySelector('[data-wizard-next]').disabled=false;toast(error.message,'error');}
    });
  };
  render();
}
