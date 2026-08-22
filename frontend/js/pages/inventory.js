import { get, post } from '../api.js';
import { options } from '../data.js';
import { renderEntityTabs } from '../entity.js?v=20260819-9';
import { badge, date, datetime, esc, money, number } from '../format.js?v=20260819-5';
import { recordModal } from '../quick_create.js';
import { state } from '../state.js';
import { toast } from '../ui.js?v=20260820-5';
import { prepareFromPurchase } from './commercial_docs.js?v=20260822-14';

async function erpPurchaseAction(event, rows) {
  const button = event.target.closest('[data-erp-po]');
  if (!button) return;
  const id = Number(button.dataset.id);
  if (!id) return;
  try {
    const saved = await prepareFromPurchase(id, button.dataset.erpPo);
    toast(`${saved.doc_no} preparado para o Primavera.`);
  } catch (error) { toast(error.message, 'error'); }
}

async function movementAction(event) {
  const button=event.target.closest('[data-movement]');if(!button)return;
  const orderOptions = await options('production-orders','order_no');
  recordModal({title:`Movimento do lote ${button.dataset.lot}`,values:{stock_lot_id:Number(button.dataset.movement)},fields:[
    {key:'stock_lot_id',type:'hidden'},{key:'movement_type',label:'Tipo',type:'select',required:true,options:['receipt','issue','consume','return','transfer_in','transfer_out','adjustment_in','adjustment_out']},
    {key:'quantity',label:'Quantidade',type:'number',required:true},{key:'production_order_id',label:'Ordem de fabrico',type:'select',options:orderOptions},{key:'location_to',label:'Local destino'},{key:'reference',label:'Referência / documento'},
  ],save:payload=>post(`/production/${state.companyId}/stock-movements`,payload),onSaved:()=>render(document.getElementById('page-content'))});
}

export async function render(container){
  const shell = document.createElement('div');
  const tabs = document.createElement('div');
  container.replaceChildren(shell, tabs);
  shell.innerHTML = '<section class="card"><div class="card-header"><h2>Stock Primavera</h2><span>A carregar…</span></div></section>';
  renderPrimaveraStock(shell);
  await renderEntityTabs(tabs,[
    {label:'Artigos',config:{resource:'materials',title:'Artigos (Primavera)',subtitle:'Código artigo, unidade, IVA, família e armazém — os mesmos campos de Base/Items.',singular:'artigo',newLabel:'Novo artigo',extraActions:'<button class="btn" data-sync-pri="items">Puxar artigos do Primavera</button>',fields:async()=>[
      {key:'code',label:'Artigo',required:true,help:'Mesmo código do Primavera'},{key:'name',label:'Descrição',required:true},{key:'item_type',label:'Tipo artigo',default:'M',help:'M mercadoria, S serviço'},
      {key:'category',label:'Categoria interna',type:'select',options:['fabric','thread','trim','label','packaging','chemical','other'],default:'fabric'},
      {key:'unit',label:'Unidade',default:'UN'},{key:'vat_code',label:'IVA / Cód. IVA',default:'23'},{key:'barcode',label:'Cód. barras'},
      {key:'family',label:'Família'},{key:'subfamily',label:'Subfamília'},{key:'brand',label:'Marca'},{key:'warehouse',label:'Armazém default'},
      {key:'supplier_id',label:'Fornecedor',type:'select',options:await options('suppliers','name')},{key:'unit_cost',label:'PC médio',type:'number',default:0},{key:'last_cost',label:'PC último',type:'number',default:0},
      {key:'composition',label:'Composição'},{key:'color',label:'Cor'},{key:'width_m',label:'Largura (m)',type:'number'},{key:'gsm',label:'Gramagem',type:'number'},
      {key:'minimum_stock',label:'Stock mínimo',type:'number',default:0},{key:'lead_time_days',label:'Lead time',type:'number',default:0},{key:'active',label:'Activo',type:'checkbox',default:true},
    ],columns:[{key:'code',label:'Artigo',render:r=>`<b>${esc(r.code)}</b>`},{key:'name',label:'Descrição'},{key:'unit',label:'Un.'},{key:'vat_code',label:'IVA'},{key:'family',label:'Família'},{key:'warehouse',label:'Armazém'},{key:'unit_cost',label:'PC médio',render:r=>money(r.unit_cost)},{key:'sync_status',label:'Sync',render:r=>badge(r.sync_status||'local')},{key:'active',label:'Estado',render:r=>badge(r.active?'activo':'inactivo')}]}},
    {label:'Armazéns',config:{resource:'warehouses',title:'Armazéns',subtitle:'Códigos de armazém iguais ao Primavera (Base/Warehouses).',singular:'armazém',newLabel:'Novo armazém',extraActions:'<button class="btn" data-sync-pri="warehouses">Puxar armazéns</button>',fields:[
      {key:'code',label:'Código',required:true},{key:'name',label:'Descrição',required:true},{key:'location',label:'Localização'},{key:'active',label:'Activo',type:'checkbox',default:true},
    ],columns:[{key:'code',label:'Armazém'},{key:'name',label:'Descrição'},{key:'location',label:'Local'},{key:'active',label:'Estado',render:r=>badge(r.active?'activo':'inactivo')}]}},
    {label:'Lotes de stock',config:{resource:'stock-lots',title:'Lotes e localizações',subtitle:'Disponível, reservado, custo e rastreabilidade documental.',singular:'lote',newLabel:'Novo lote',fields:async()=>[
      {key:'material_id',label:'Material',type:'select',required:true,options:await options('materials',r=>`${r.code} · ${r.name}`)},{key:'supplier_id',label:'Fornecedor',type:'select',options:await options('suppliers','name')},{key:'lot_no',label:'Lote',required:true},
      {key:'location',label:'Localização'},{key:'quantity',label:'Quantidade',type:'number',default:0},{key:'reserved',label:'Reservado',type:'number',default:0},{key:'unit_cost',label:'Custo unitário',type:'number',default:0},
      {key:'received_date',label:'Receção',type:'date'},{key:'expiry_date',label:'Validade',type:'date'},{key:'status',label:'Estado',type:'select',options:['available','quarantine','blocked','consumed'],default:'available'},
      {key:'certification_snapshot',label:'Certificados na receção (JSON)',type:'json',default:{},full:true},
    ],rowActions:r=>`<button class="btn small primary" data-movement="${r.id}" data-lot="${esc(r.lot_no)}">Movimento</button>`,onAction:movementAction,columns:[{key:'lot_no',label:'Lote',render:r=>`<b>${esc(r.lot_no)}</b>`},{key:'material_id',label:'Material'},{key:'location',label:'Local'},{key:'quantity',label:'Stock',render:r=>number(r.quantity)},{key:'reserved',label:'Reservado',render:r=>number(r.reserved)},{key:'available',label:'Disponível',render:r=>number(r.quantity-r.reserved)},{key:'unit_cost',label:'Custo',render:r=>money(r.unit_cost)},{key:'received_date',label:'Receção',render:r=>date(r.received_date)},{key:'status',label:'Estado',render:r=>badge(r.status)}]}},
    {label:'Compras',config:{resource:'purchase-orders',title:'Ordens de compra',subtitle:'Fornecedores, prazos, receções e valor. Os botões preparam o documento para o Primavera.',singular:'ordem de compra',newLabel:'Nova compra',fields:async()=>[
      {key:'supplier_id',label:'Fornecedor',type:'select',required:true,options:await options('suppliers','name')},{key:'order_no',label:'Número',required:true},{key:'order_date',label:'Data',type:'date'},{key:'expected_date',label:'Entrega prevista',type:'date'},
      {key:'status',label:'Estado',type:'select',options:['draft','sent','partial','received','cancelled'],default:'draft'},{key:'total',label:'Total',type:'number',default:0},{key:'notes',label:'Notas',type:'textarea',full:true},
    ],rowActions:r=>`<button class="btn small primary" data-erp-po="requisition" data-id="${r.id}">Requisição</button><button class="btn small" data-erp-po="purchase_invoice" data-id="${r.id}">Fatura compra</button><button class="btn small" data-erp-po="supplier_transport" data-id="${r.id}">Guia</button><button class="btn small" data-erp-po="stock_receipt" data-id="${r.id}">Entrada</button>`,onAction:erpPurchaseAction,columns:[{key:'order_no',label:'OC',render:r=>`<b>${esc(r.order_no)}</b>`},{key:'supplier_id',label:'Fornecedor'},{key:'order_date',label:'Data',render:r=>date(r.order_date)},{key:'expected_date',label:'Entrega',render:r=>date(r.expected_date)},{key:'total',label:'Total',render:r=>money(r.total)},{key:'status',label:'Estado',render:r=>badge(r.status)}]}},
    {label:'Linhas de compra',config:{resource:'purchase-order-lines',title:'Linhas de compra',subtitle:'Materiais, quantidades, preços e receções.',singular:'linha de compra',newLabel:'Nova linha',fields:async()=>[
      {key:'purchase_order_id',label:'Ordem de compra',type:'select',required:true,options:await options('purchase-orders','order_no')},{key:'material_id',label:'Material',type:'select',required:true,options:await options('materials',r=>`${r.code} · ${r.name}`)},
      {key:'quantity',label:'Quantidade',type:'number',required:true},{key:'unit_cost',label:'Custo unitário',type:'number',default:0},{key:'received_quantity',label:'Recebido',type:'number',default:0},
    ],columns:[{key:'purchase_order_id',label:'OC'},{key:'material_id',label:'Material'},{key:'quantity',label:'Encomendado',render:r=>number(r.quantity)},{key:'received_quantity',label:'Recebido',render:r=>number(r.received_quantity)},{key:'unit_cost',label:'Custo',render:r=>money(r.unit_cost)}]}},
    {label:'Movimentos',config:{resource:'inventory-movements',readOnly:true,title:'Histórico de movimentos',subtitle:'Livro de stock imutável por lote, ordem e utilizador.',singular:'movimento',fields:[],columns:[{key:'movement_time',label:'Data/hora',render:r=>datetime(r.movement_time)},{key:'stock_lot_id',label:'Lote ID'},{key:'movement_type',label:'Tipo',render:r=>badge(r.movement_type)},{key:'quantity',label:'Quantidade',render:r=>number(r.quantity)},{key:'unit_cost',label:'Custo',render:r=>money(r.unit_cost)},{key:'production_order_id',label:'OF'},{key:'reference',label:'Referência'},{key:'user_id',label:'Utilizador'}]}},
  ]);
  if (!container.dataset.syncPriBound) {
    container.dataset.syncPriBound = '1';
    container.addEventListener('click', async event => {
      const button = event.target.closest('[data-sync-pri]');
      if (!button) return;
      try {
        toast('A puxar tabelas do Primavera…');
        const result = await post(`/integrations/${state.companyId}/primavera/sync`, {resources:[button.dataset.syncPri]});
        const row = (result.results || [])[0] || {};
        toast(`Sincronizado: ${row.created || 0} novos, ${row.updated || 0} actualizados.`);
        await render(container);
      } catch (error) { toast(error.message, 'error'); }
    });
  }
}

async function renderPrimaveraStock(container) {
  try {
    const data = await get(`/integrations/${state.companyId}/primavera/stock`);
    const items = data.items || [];
    container.innerHTML = `<section class="card"><div class="card-header"><h2>Stock Primavera</h2><span>${data.count || 0} artigos · ${esc(data.path || '')}</span></div>
      ${items.length ? `<div class="table-wrap"><table class="data-table"><thead><tr><th>Artigo</th><th>Armazém</th><th>Stock</th><th>Reservado</th><th>Disponível</th></tr></thead>
      <tbody>${items.slice(0, 80).map(row => `<tr><td><b>${esc(row.item)}</b></td><td>${esc(row.warehouse)}</td><td>${number(row.quantity)}</td><td>${number(row.reserved)}</td><td>${number(row.available)}</td></tr>`).join('')}</tbody></table></div>
      ${items.length > 80 ? `<p class="muted">A mostrar 80 de ${items.length}. Use o Primavera para a lista completa.</p>` : ''}` : '<p class="muted">A Web API não devolveu linhas de stock. Confirme o caminho Inventory/ItemWarehouses.</p>'}
    </section>`;
  } catch (error) {
    container.innerHTML = `<section class="card"><div class="card-header"><h2>Stock Primavera</h2><span>Não ligado</span></div>
      <p class="muted">${esc(error.message)} Configure a Web API em ERP → Ligação Primavera. Até lá o stock local nos lotes continua a ser a referência operacional.</p>
    </section>`;
  }
}
