import { options } from '../data.js';
import { renderEntityPage } from '../entity.js?v=20260826-3';
import { date, money } from '../format.js?v=20260826-3';

export async function render(container){
  await renderEntityPage(container,{resource:'overheads',title:'Custos gerais e centros de custo',subtitle:'Energia, rendas, manutenção, administração e bases de imputação.',singular:'custo geral',newLabel:'Novo custo geral',fields:async()=>[
    {key:'department_id',label:'Departamento',type:'select',options:await options('departments','name')},{key:'category',label:'Categoria',type:'select',required:true,options:['energy','rent','maintenance','administration','insurance','depreciation','other']},
    {key:'description',label:'Descrição',required:true},{key:'period_start',label:'Início',type:'date',required:true},{key:'period_end',label:'Fim',type:'date',required:true},{key:'amount',label:'Valor',type:'number',required:true},
    {key:'allocation_basis',label:'Base de imputação',type:'select',options:['production_minutes','units','labor_hours','machine_hours','revenue'],default:'production_minutes'},
  ],columns:[{key:'category',label:'Categoria'},{key:'description',label:'Descrição'},{key:'department_id',label:'Dept.'},{key:'period_start',label:'Início',render:r=>date(r.period_start)},{key:'period_end',label:'Fim',render:r=>date(r.period_end)},{key:'allocation_basis',label:'Imputação'},{key:'amount',label:'Valor',render:r=>`<b>${money(r.amount)}</b>`}]});
}
