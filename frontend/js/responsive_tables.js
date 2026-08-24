import { icon } from './icons.js?v=20260824-41';

const exclusions='.grade-table,.cost-input-table,.wizard-input-table,.invoice-lines,[data-mobile-table="scroll"]';
const labels={eye:'Abrir',edit:'Editar',delete:'Eliminar',save:'Guardar',check:'Concluir',close:'Fechar',truck:'Expedir',box:'Embalar',tag:'Etiqueta',document:'Documento',add:'Adicionar',route:'Dar destino',inbox:'Receber',print:'Imprimir',copy:'Duplicar',more:'Mais ações'};
const rules=[
  ['delete',/delete|eliminar|remover|apagar/],['edit',/edit|editar|alterar/],['eye',/open|abrir|ver\b|ficha|detalhe/],
  ['save',/save|guardar|gravar/],['check',/libertar|aprovar|aceitar|concluir|confirmar|marcar.*lida/],['close',/fechar|cancelar/],
  ['truck',/expedir|enviar|shipment/],['box',/embalar|embalagem|pack/],['tag',/etiqueta|label/],['print',/imprimir|print/],
  ['copy',/duplicar|copiar|copy/],['inbox',/receber|receção|reception/],['route',/destino|transferir|movimentar/],
  ['document',/documento|fatura|factura|guia|nota.*cr[eé]dito/],['add',/criar|novo|adicionar|registar|requisitar/],
];

function enhanceTable(table){
  if(table.matches(exclusions)||table.closest('.mcm-gantt,.pmap-board,.grade-grid'))return;
  const headers=[...table.querySelectorAll('thead th')].map(cell=>cell.textContent.trim());
  if(!headers.length)return;
  table.dataset.mobile='cards';
  table.classList.add('table-list');
  table.querySelectorAll('tbody tr').forEach(row=>{
    const cells=[...row.children].filter(cell=>cell.tagName==='TD');
    if(cells.length===1&&Number(cells[0].getAttribute('colspan')||1)>1){cells[0].dataset.mobileFull='true';return}
    cells.forEach((cell,index)=>{if(!cell.dataset.label)cell.dataset.label=headers[index]||'Detalhe'});
  });
}

function actionName(control){
  const source=[control.getAttribute('aria-label'),control.title,control.textContent,Object.keys(control.dataset).join(' ')].filter(Boolean).join(' ').toLowerCase();
  return rules.find(([,pattern])=>pattern.test(source))?.[0]||'more';
}

function enhanceActionRow(row){
  const cell=row.lastElementChild;
  if(!cell||cell.tagName!=='TD')return;
  let controls=[...cell.querySelectorAll(':scope > .btn,:scope > .row-actions > .btn')];
  if(!controls.length||cell.hasAttribute('colspan'))return;
  let holder=cell.querySelector(':scope > .row-actions');
  if(!holder){holder=document.createElement('div');holder.className='row-actions';controls.forEach(control=>holder.appendChild(control));cell.appendChild(holder)}
  holder.classList.add('table-actions');
  cell.classList.add('table-action-cell');
  cell.dataset.label='Ações';
  const table=cell.closest('table');
  const heading=table?.tHead?.rows?.[0];
  if(heading){while(heading.cells.length<=cell.cellIndex)heading.appendChild(document.createElement('th'));const actionHeading=heading.cells[cell.cellIndex];if(!actionHeading.classList.contains('table-action-header')){actionHeading.className='table-action-header';actionHeading.scope='col';actionHeading.innerHTML=`<span class="sr-only">Ações</span>${icon('more')}`}}
  controls=[...holder.querySelectorAll(':scope > .btn')];
  controls.forEach(control=>{
    const name=actionName(control);
    if(control.dataset.listAction===name&&control.querySelector('svg'))return;
    const label=control.getAttribute('aria-label')||control.title||control.textContent.trim()||labels[name];
    control.dataset.listAction=name;
    control.classList.add('icon','table-action-button',`action-${name}`);
    control.setAttribute('aria-label',label);
    control.title=label;
    if(control.tagName==='BUTTON'&&!control.type)control.type='button';
    control.innerHTML=icon(name);
  });
}

function enhance(root=document){
  if(root.matches?.('table.data-table'))enhanceTable(root);
  root.querySelectorAll?.('table.data-table').forEach(enhanceTable);
  if(root.matches?.('table.data-table tbody tr'))enhanceActionRow(root);
  root.querySelectorAll?.('table.data-table tbody tr').forEach(enhanceActionRow);
}

export function initResponsiveTables(){
  enhance(document);
  const observer=new MutationObserver(records=>records.forEach(record=>record.addedNodes.forEach(node=>{if(node.nodeType===1)enhance(node)})));
  observer.observe(document.body,{childList:true,subtree:true});
}
