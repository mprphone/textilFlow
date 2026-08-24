import { options } from '../data.js';
import { renderEntityPage } from '../entity.js?v=20260824-41';
import { badge, esc, number } from '../format.js?v=20260819-5';
import { mergeCustomData } from '../forms.js?v=20260824-1';
import { renderStyleDetail } from './style_detail.js?v=20260824-41';

async function styleFields() {
  return [
    {key:'reference',label:'Referência',required:true},
    {key:'description',label:'Descrição',required:true},
    {key:'article_type_id',label:'Tipo de artigo',type:'select',options:await options('article-types','name')},
    {key:'customer_id',label:'Cliente',type:'select',options:await options('customers','name')},
    {key:'collection',label:'Coleção'},{key:'base_unit',label:'Unidade',default:'un'},
  ];
}

export async function render(container) {
  await renderEntityPage(container, {
    resource:'styles', title:'Artigos e fichas técnicas', subtitle:'Fichas adaptativas, versionadas e ligadas a materiais, operações e custos.',
    singular:'artigo', newLabel:'Novo artigo', fields:styleFields,
    formSubtitle: row => row
      ? 'Edição rápida do essencial. Materiais, ciclo de vida, medidas e variantes editam-se na ficha completa ("Abrir ficha").'
      : 'Crie o artigo com o essencial — o resto preenche-se depois na ficha completa.',
    transform:(payload,row)=>mergeCustomData(payload,row?.custom_data),
    rowActions:row=>`<button class="btn icon primary" type="button" data-icon="eye" data-open-style="${row.id}" aria-label="Abrir ficha" title="Abrir ficha"></button>`,
    onAction:event=>{const button=event.target.closest('[data-open-style]');if(button)renderStyleDetail(container,Number(button.dataset.openStyle),()=>render(container));},
    columns:[
      {key:'reference',label:'Referência',render:r=>`<b>${esc(r.reference)}</b>`},{key:'description',label:'Artigo'},
      {key:'collection',label:'Coleção'},{key:'fabric',label:'Malha'},{key:'gsm',label:'g/m²',render:r=>number(r.gsm)},
      {key:'workflow_stage',label:'Etapa',render:r=>badge(r.workflow_stage)},{key:'technical_version',label:'Versão',render:r=>`V${r.technical_version}`},
      {key:'lifecycle_status',label:'Estado',render:r=>badge(r.lifecycle_status)},
    ],
  });
}
