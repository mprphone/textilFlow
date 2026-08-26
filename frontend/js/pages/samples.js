import { options } from '../data.js';
import { renderEntityPage } from '../entity.js?v=20260826-3';
import { badge, date, money, number } from '../format.js?v=20260826-3';
import { recordModal } from '../quick_create.js';
import { post } from '../api.js';

export async function render(container) {
  await renderEntityPage(container, {
    resource:'samples',title:'Amostras e aprovações',subtitle:'Tempo, materiais, custo real, versões e feedback.',singular:'amostra',newLabel:'Nova amostra',
    fields:async()=>[
      {key:'style_id',label:'Artigo',type:'select',required:true,options:await options('styles',r=>`${r.reference} · ${r.description}`),section:'Amostra'},
      {key:'sample_type',label:'Tipo',type:'select',required:true,options:['proto','fitting','size_set','salesman','pps'],section:'Amostra'},
      {key:'version',label:'Versão',required:true,default:'V1',section:'Amostra'},{key:'status',label:'Estado',type:'select',options:['requested','in_progress','sent','approved','rejected'],default:'requested',section:'Amostra'},
      {key:'responsible_employee_id',label:'Responsável',type:'select',options:await options('employees','name'),section:'Planeamento'},
      {key:'planned_date',label:'Data planeada',type:'date',section:'Planeamento'},{key:'completed_date',label:'Data conclusão',type:'date',section:'Planeamento'},
      {key:'labor_minutes',label:'Tempo (min)',type:'number',default:0,section:'Custos'},{key:'labor_cost',label:'Mão de obra',type:'number',default:0,section:'Custos'},
      {key:'material_cost',label:'Materiais',type:'number',default:0,section:'Custos'},{key:'external_cost',label:'Serviços externos',type:'number',default:0,section:'Custos'},
      {key:'comments',label:'Comentários / alterações',type:'textarea',full:true,section:'Resultado'},
    ],
    columns:[{key:'style_id',label:'Artigo ID'},{key:'sample_type',label:'Tipo'},{key:'version',label:'Versão'},{key:'status',label:'Estado',render:r=>badge(r.status)},{key:'responsible_employee_id',label:'Responsável ID'},{key:'planned_date',label:'Planeada',render:r=>date(r.planned_date)},{key:'labor_minutes',label:'Tempo',render:r=>`${number(r.labor_minutes)} min`},{key:'total_cost',label:'Custo total',render:r=>`<b>${money(r.total_cost)}</b>`}],
    rowActions:row=>row.custom_data?.production_order_id?`<span class="badge blue">OF #${row.custom_data.production_order_id}</span>`:row.status==='approved'?`<button class="btn small success" data-production-sample="${row.id}">Enviar para produção</button>`:'',
    onAction:async(event,rows)=>{const button=event.target.closest('[data-production-sample]');if(!button)return;const sample=rows.find(row=>row.id===Number(button.dataset.productionSample));recordModal({title:'Libertar amostra para produção',values:{priority:3},fields:[{key:'order_no',label:'Número da ordem de fabrico',required:true,section:'Ordem'},{key:'quantity',label:'Quantidade',type:'number',required:true,section:'Ordem'},{key:'line_id',label:'Linha / célula',type:'select',options:await options('production-lines','name'),section:'Planeamento'},{key:'planned_start',label:'Início planeado',type:'date',section:'Planeamento'},{key:'planned_end',label:'Entrega planeada',type:'date',section:'Planeamento'},{key:'priority',label:'Prioridade',type:'select',options:[1,2,3,4,5],default:3,section:'Planeamento'}],save:payload=>post(`/production/samples/${sample.id}/release`,payload),onSaved:()=>{location.hash='#/orders';}});},
  });
}
