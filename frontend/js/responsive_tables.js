const exclusions='.grade-table,.cost-input-table,.wizard-input-table,.invoice-lines,[data-mobile-table="scroll"]';

function enhanceTable(table){
  if(table.dataset.mobile||table.matches(exclusions)||table.closest('.mcm-gantt,.pmap-board,.grade-grid'))return;
  const headers=[...table.querySelectorAll('thead th')].map(cell=>cell.textContent.trim());
  if(!headers.length)return;
  table.dataset.mobile='cards';
  table.querySelectorAll('tbody tr').forEach(row=>{
    const cells=[...row.children].filter(cell=>cell.tagName==='TD');
    if(cells.length===1&&Number(cells[0].getAttribute('colspan')||1)>1){cells[0].dataset.mobileFull='true';return}
    cells.forEach((cell,index)=>{cell.dataset.label=headers[index]||'Detalhe'});
  });
}

function enhance(root=document){
  if(root.matches?.('table.data-table'))enhanceTable(root);
  root.querySelectorAll?.('table.data-table').forEach(enhanceTable);
}

export function initResponsiveTables(){
  enhance(document);
  const observer=new MutationObserver(records=>records.forEach(record=>record.addedNodes.forEach(node=>{if(node.nodeType===1)enhance(node)})));
  observer.observe(document.body,{childList:true,subtree:true});
}
