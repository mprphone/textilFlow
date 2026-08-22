import { get } from '../api.js';
import { options } from '../data.js';
import { renderEntityPage } from '../entity.js?v=20260819-9';
import { badge, esc, number } from '../format.js?v=20260819-5';
import { dynamicFields, mergeCustomData } from '../forms.js?v=20260819-5';
import { state } from '../state.js';
import { renderStyleDetail } from './style_detail.js';

async function styleFields(row = null) {
  const configuration = await get(`/configuration/${state.companyId}/style`);
  return [
    {key:'reference',label:'Referência',required:true,section:'Identificação'},
    {key:'description',label:'Descrição',required:true,section:'Identificação'},
    {key:'article_type_id',label:'Tipo de artigo',type:'select',options:await options('article-types','name'),section:'Identificação'},
    {key:'customer_id',label:'Cliente',type:'select',options:await options('customers','name'),section:'Identificação'},
    {key:'collection',label:'Coleção',section:'Identificação'},{key:'base_unit',label:'Unidade',default:'un',section:'Identificação'},
    {key:'lifecycle_status',label:'Estado',type:'select',options:['development','approved','production','inactive'],default:'development',section:'Ciclo de vida'},
    {key:'workflow_stage',label:'Etapa',type:'select',options:['novo','proposta_cliente','ficha_tecnica','desenvolvimento_malha','modelagem','corte','confecao','finalizacao','envio_cliente','resposta_cliente','retificacoes','conceito','proto','fitting','size_set','pps','aprovado','produção','arquivado'],default:'novo',section:'Ciclo de vida'},
    {key:'fabric',label:'Malha base',section:'Materiais'},{key:'composition',label:'Composição',section:'Materiais'},
    {key:'gsm',label:'Gramagem',type:'number',section:'Materiais'},{key:'color',label:'Cor base',section:'Materiais'},
    {key:'size_range',label:'Gama de tamanhos',section:'Materiais'},{key:'image_url',label:'Imagem / URL',type:'url',section:'Materiais',full:true},
    ...dynamicFields(configuration.fields, row?.custom_data || {}),
    {key:'approved',label:'Aprovação',type:'checkbox',help:'Ficha aprovada',section:'Controlo'},
    {key:'revision_reason',label:'Motivo da alteração',section:'Controlo',full:true},
  ];
}

export async function render(container) {
  await renderEntityPage(container, {
    resource:'styles', title:'Artigos e fichas técnicas', subtitle:'Fichas adaptativas, versionadas e ligadas a materiais, operações e custos.',
    singular:'artigo', newLabel:'Novo artigo', fields:styleFields,
    transform:(payload,row)=>mergeCustomData(payload,row?.custom_data),
    rowActions:row=>`<button class="btn small primary" data-open-style="${row.id}">Abrir ficha</button>`,
    onAction:event=>{const button=event.target.closest('[data-open-style]');if(button)renderStyleDetail(container,Number(button.dataset.openStyle),()=>render(container));},
    columns:[
      {key:'reference',label:'Referência',render:r=>`<b>${esc(r.reference)}</b>`},{key:'description',label:'Artigo'},
      {key:'collection',label:'Coleção'},{key:'fabric',label:'Malha'},{key:'gsm',label:'g/m²',render:r=>number(r.gsm)},
      {key:'workflow_stage',label:'Etapa',render:r=>badge(r.workflow_stage)},{key:'technical_version',label:'Versão',render:r=>`V${r.technical_version}`},
      {key:'lifecycle_status',label:'Estado',render:r=>badge(r.lifecycle_status)},
    ],
  });
}
