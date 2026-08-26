import { options } from '../data.js';
import { renderEntityPage } from '../entity.js?v=20260826-3';
import { badge, money, number } from '../format.js?v=20260826-3';

export async function render(container) {
  const typeOptions = await options('machine-types','name','code');
  await renderEntityPage(container, {
    resource:'operations', title:'Operações e tempos de confeção', subtitle:'Métodos da costura: SMV, máquina, instruções e custo-padrão.', singular:'operação', newLabel:'Nova operação',
    fields:[
      {key:'code',label:'Código',required:true,section:'Operação'},{key:'name',label:'Nome',required:true,section:'Operação'},{key:'department',label:'Departamento',section:'Operação'},
      {key:'machine_type',label:'Tipo de máquina',type:'select',options:typeOptions,section:'Método'},{key:'standard_time_min',label:'Tempo-padrão (min)',type:'number',default:0,section:'Método'},
      {key:'cost_per_minute',label:'Custo mão de obra/min',type:'number',default:0,section:'Método'},
      {key:'machine_cost_per_minute',label:'Custo máquina/min',type:'number',default:0,help:'Se preenchido, a ficha de custo gera automaticamente uma linha de máquina além da de mão de obra.',section:'Método'},
      {key:'instruction',label:'Instrução de trabalho',type:'textarea',section:'Instruções',full:true},{key:'media_url',label:'Vídeo/imagem de apoio',type:'url',section:'Instruções',full:true},
      {key:'active',label:'Estado',type:'checkbox',default:true,help:'Operação disponível',section:'Estado'},
    ],
    columns:[{key:'code',label:'Código'},{key:'name',label:'Operação'},{key:'department',label:'Área'},{key:'machine_type',label:'Máquina'},{key:'standard_time_min',label:'SMV',render:r=>`${number(r.standard_time_min)} min`},{key:'cost_per_minute',label:'Mão de obra/min',render:r=>money(r.cost_per_minute)},{key:'machine_cost_per_minute',label:'Máquina/min',render:r=>money(r.machine_cost_per_minute)},{key:'active',label:'Estado',render:r=>badge(r.active?'ativa':'inativa')}],
  });
}
