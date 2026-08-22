import { options } from '../data.js';
import { renderEntityTabs } from '../entity.js?v=20260819-9';
import { badge, date, esc, number, progress } from '../format.js?v=20260819-5';
import { loadOrderDossier } from '../production/dossier.js?v=20260822-21';
import { stageLabel } from '../production/cycle.js?v=20260822-18';
import { toast } from '../ui.js?v=20260820-5';
import { prepareFromSales } from './commercial_docs.js?v=20260822-30';

function showTrace(container, event) {
  const button = event.target.closest('[data-trace]');
  if (!button) return;
  loadOrderDossier(Number(button.dataset.trace));
}

async function erpSalesAction(event, rows) {
  const button = event.target.closest('[data-erp-so]');
  if (!button) return;
  try {
    const saved = await prepareFromSales(Number(button.dataset.id), button.dataset.erpSo);
    toast(`${saved.doc_no} preparado para o Primavera.`);
  } catch (error) { toast(error.message, 'error'); }
}

export async function render(container) {
  await renderEntityTabs(container,[
    {label:'Encomendas',config:{resource:'sales-orders',title:'Encomendas de cliente',subtitle:'Prazos, PO, estado e valor comercial. Os botões preparam fatura, NC, ND e guia para o Primavera.',singular:'encomenda',newLabel:'Nova encomenda',fields:async()=>[
      {key:'customer_id',label:'Cliente',type:'select',required:true,options:await options('customers','name')},{key:'order_no',label:'Número interno',required:true},{key:'customer_po',label:'PO cliente'},
      {key:'order_date',label:'Data',type:'date'},{key:'delivery_date',label:'Entrega',type:'date'},{key:'status',label:'Estado',type:'select',options:['draft','confirmed','in_production','ready','shipped','cancelled'],default:'confirmed'},
      {key:'currency',label:'Moeda',default:'EUR'},{key:'notes',label:'Notas',type:'textarea',full:true},
    ],rowActions:r=>`<button class="btn small primary" data-erp-so="sales_invoice" data-id="${r.id}">Fatura</button><button class="btn small" data-erp-so="sales_credit" data-id="${r.id}">NC</button><button class="btn small" data-erp-so="sales_debit" data-id="${r.id}">ND</button><button class="btn small" data-erp-so="sales_delivery" data-id="${r.id}">Guia</button>`,onAction:erpSalesAction,columns:[{key:'order_no',label:'Encomenda',render:r=>`<b>${esc(r.order_no)}</b>`},{key:'customer_po',label:'PO cliente'},{key:'customer_id',label:'Cliente ID'},{key:'order_date',label:'Data',render:r=>date(r.order_date)},{key:'delivery_date',label:'Entrega',render:r=>date(r.delivery_date)},{key:'status',label:'Estado',render:r=>badge(r.status)}]}},
    {label:'Linhas da encomenda',config:{resource:'sales-order-lines',title:'Artigos encomendados',subtitle:'Quantidades, variantes, preço e data por linha.',singular:'linha',newLabel:'Nova linha',fields:async()=>[
      {key:'sales_order_id',label:'Encomenda',type:'select',required:true,options:await options('sales-orders',r=>r.order_no)},{key:'style_id',label:'Artigo',type:'select',required:true,options:await options('styles',r=>`${r.reference} · ${r.description}`)},
      {key:'variant_id',label:'Variante',type:'select',options:await options('style-variants','sku')},{key:'description',label:'Descrição'},{key:'quantity',label:'Quantidade',type:'number',required:true},
      {key:'unit_price',label:'Preço unitário',type:'number',default:0},{key:'delivery_date',label:'Entrega',type:'date'},
    ],columns:[{key:'sales_order_id',label:'Encomenda'},{key:'style_id',label:'Artigo'},{key:'variant_id',label:'Variante'},{key:'description',label:'Descrição'},{key:'quantity',label:'Quantidade',render:r=>number(r.quantity)},{key:'unit_price',label:'Preço',render:r=>`${number(r.unit_price)} €`},{key:'delivery_date',label:'Entrega',render:r=>date(r.delivery_date)}]}},
    {label:'Ordens de fabrico',config:{resource:'production-orders',title:'Ordens de fabrico',subtitle:'Planeamento, prioridade, fase, local e progresso real.',singular:'ordem de fabrico',newLabel:'Nova OF',fields:async()=>[
      {key:'sales_order_line_id',label:'Linha de encomenda',type:'select',options:await options('sales-order-lines',r=>`Linha #${r.id} · ${number(r.quantity)} un.`)},{key:'style_id',label:'Artigo',type:'select',required:true,options:await options('styles',r=>`${r.reference} · ${r.description}`)},
      {key:'line_id',label:'Linha/célula',type:'select',options:await options('production-lines','name')},{key:'order_no',label:'Número OF',required:true},{key:'quantity',label:'Quantidade',type:'number',required:true},
      {key:'planned_start',label:'Início planeado',type:'date'},{key:'planned_end',label:'Fim planeado',type:'date'},{key:'priority',label:'Prioridade',type:'number',default:3},
      {key:'status',label:'Estado',type:'select',options:['planned','released','in_progress','paused','completed','cancelled'],default:'planned'},{key:'current_stage',label:'Fase atual',default:'planning'},{key:'current_location',label:'Local atual'},
    ],rowActions:r=>`<button class="btn small primary" data-trace="${r.id}">Rastrear</button>`,onAction:showTrace,columns:[{key:'order_no',label:'OF',render:r=>`<b>${esc(r.order_no)}</b>`},{key:'style_id',label:'Artigo'},{key:'quantity',label:'Quantidade',render:r=>number(r.quantity)},{key:'completed_quantity',label:'Progresso',render:r=>progress(r.quantity?r.completed_quantity/r.quantity*100:0)},{key:'planned_end',label:'Prazo',render:r=>date(r.planned_end)},{key:'current_stage',label:'Fase',render:r=>badge(stageLabel(r.current_stage))},{key:'current_location',label:'Local'},{key:'status',label:'Estado',render:r=>badge(r.status)}]}},
    {label:'Lotes',config:{resource:'batches',title:'Lotes de produção',subtitle:'Rastreio por cor, tamanho, quantidade, código e localização.',singular:'lote',newLabel:'Novo lote',fields:async()=>[
      {key:'production_order_id',label:'Ordem',type:'select',required:true,options:await options('production-orders','order_no')},{key:'batch_no',label:'Número do lote',required:true},{key:'color',label:'Cor'},{key:'size',label:'Tamanho'},
      {key:'quantity',label:'Quantidade',type:'number',required:true},{key:'current_operation_id',label:'Operação atual',type:'select',options:await options('operations','name')},{key:'current_location',label:'Local'},{key:'status',label:'Estado',type:'select',options:['waiting','in_progress','blocked','completed'],default:'waiting'},{key:'barcode',label:'Código de barras'},
    ],columns:[{key:'batch_no',label:'Lote',render:r=>`<b>${esc(r.batch_no)}</b>`},{key:'production_order_id',label:'OF'},{key:'color',label:'Cor'},{key:'size',label:'Tam.'},{key:'quantity',label:'Qtd.',render:r=>number(r.quantity)},{key:'completed_quantity',label:'Concluído',render:r=>number(r.completed_quantity)},{key:'current_location',label:'Local'},{key:'status',label:'Estado',render:r=>badge(r.status)}]}},
    {label:'Atribuições',config:{resource:'work-assignments',title:'Atribuição de trabalho',subtitle:'Operação por ordem, lote, funcionário, máquina e linha.',singular:'atribuição',newLabel:'Nova atribuição',fields:async()=>[
      {key:'production_order_id',label:'Ordem',type:'select',required:true,options:await options('production-orders','order_no')},{key:'batch_id',label:'Lote',type:'select',options:await options('batches','batch_no')},{key:'operation_id',label:'Operação',type:'select',required:true,options:await options('operations','name')},
      {key:'employee_id',label:'Funcionário',type:'select',options:await options('employees','name')},{key:'machine_id',label:'Máquina',type:'select',options:await options('machines','name')},{key:'line_id',label:'Linha',type:'select',options:await options('production-lines','name')},
      {key:'planned_quantity',label:'Quantidade',type:'number',required:true},{key:'standard_minutes',label:'Minutos-padrão totais',type:'number',default:0},{key:'status',label:'Estado',type:'select',options:['queued','in_progress','paused','completed'],default:'queued'},
    ],columns:[{key:'production_order_id',label:'OF'},{key:'batch_id',label:'Lote'},{key:'operation_id',label:'Operação'},{key:'employee_id',label:'Funcionário'},{key:'machine_id',label:'Máquina'},{key:'planned_quantity',label:'Planeado',render:r=>number(r.planned_quantity)},{key:'completed_quantity',label:'Produzido',render:r=>number(r.completed_quantity)},{key:'status',label:'Estado',render:r=>badge(r.status)}]}},
  ]);
}
