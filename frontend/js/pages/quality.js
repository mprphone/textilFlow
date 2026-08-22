import { options } from '../data.js';
import { renderEntityPage } from '../entity.js?v=20260819-9';
import { badge, datetime, number, percent } from '../format.js?v=20260819-5';

export async function render(container){
  await renderEntityPage(container,{resource:'quality-inspections',title:'Qualidade e defeitos',subtitle:'Inspeção inline/final, AQL, causa, severidade e decisão.',singular:'inspeção',newLabel:'Nova inspeção',fields:async()=>[
    {key:'production_order_id',label:'Ordem',type:'select',options:await options('production-orders','order_no')},{key:'batch_id',label:'Lote',type:'select',options:await options('batches','batch_no')},{key:'operation_id',label:'Operação',type:'select',options:await options('operations','name')},
    {key:'employee_id',label:'Inspetor',type:'select',options:await options('employees','name')},{key:'supplier_id',label:'Fornecedor',type:'select',options:await options('suppliers','name')},
    {key:'inspection_type',label:'Tipo',type:'select',options:['incoming','inline','endline','final','aql'],default:'inline'},{key:'inspected_quantity',label:'Inspecionadas',type:'number',default:0},{key:'defect_quantity',label:'Defeitos',type:'number',default:0},
    {key:'defect_code',label:'Código defeito'},{key:'severity',label:'Severidade',type:'select',options:['minor','major','critical'],default:'minor'},{key:'result',label:'Resultado',type:'select',options:['pending','passed','conditional','failed'],default:'pending'},
    {key:'notes',label:'Observações e ação corretiva',type:'textarea',full:true},{key:'photos',label:'Fotografias (JSON/URLs)',type:'json',default:[],full:true},
  ],columns:[{key:'created_at',label:'Data',render:r=>datetime(r.created_at)},{key:'production_order_id',label:'OF'},{key:'batch_id',label:'Lote'},{key:'inspection_type',label:'Tipo'},{key:'inspected_quantity',label:'Inspec.',render:r=>number(r.inspected_quantity)},{key:'defect_quantity',label:'Defeitos',render:r=>number(r.defect_quantity)},{key:'defect_code',label:'Código'},{key:'severity',label:'Severidade',render:r=>badge(r.severity)},{key:'result',label:'Resultado',render:r=>badge(r.result)}]});
}
