const paths={
  menu:'<path d="M4 7h16M4 12h16M4 17h16"/>',
  close:'<path d="m6 6 12 12M18 6 6 18"/>',
  add:'<path d="M12 5v14M5 12h14"/>',
  search:'<circle cx="11" cy="11" r="6.5"/><path d="m16 16 4 4"/>',
  check:'<path d="m5 12 4 4L19 6"/>',
  warning:'<path d="M12 3 2.8 20h18.4L12 3Z"/><path d="M12 9v4M12 17h.01"/>',
  edit:'<path d="m4 16-.8 4 4-.8L18 8.4 15.6 6 4 16Z"/><path d="m14.5 7.1 2.4 2.4"/>',
  delete:'<path d="M4 7h16M9 7V4h6v3M7 7l1 13h8l1-13M10 11v5M14 11v5"/>',
  back:'<path d="m15 18-6-6 6-6"/>',
  forward:'<path d="m9 18 6-6-6-6"/>',
  home:'<path d="m3 11 9-8 9 8"/><path d="M5 10v10h14V10M9 20v-6h6v6"/>',
  document:'<path d="M6 3h8l4 4v14H6V3Z"/><path d="M14 3v5h5M9 12h6M9 16h6"/>',
  grid:'<rect x="4" y="4" width="6" height="6"/><rect x="14" y="4" width="6" height="6"/><rect x="4" y="14" width="6" height="6"/><rect x="14" y="14" width="6" height="6"/>',
  chart:'<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
  production:'<path d="m8 5 11 7-11 7V5Z"/>',
  quality:'<path d="M12 3 5 6v5c0 4.8 2.9 8.1 7 10 4.1-1.9 7-5.2 7-10V6l-7-3Z"/><path d="m8.5 12 2.2 2.2 4.8-5"/>',
  box:'<path d="m4 7 8-4 8 4-8 4-8-4Z"/><path d="M4 7v10l8 4 8-4V7M12 11v10"/>',
  truck:'<path d="M3 6h11v11H3V6ZM14 10h4l3 3v4h-7v-7Z"/><circle cx="7" cy="18" r="2"/><circle cx="18" cy="18" r="2"/>',
  scissors:'<circle cx="6" cy="7" r="3"/><circle cx="6" cy="17" r="3"/><path d="m8.5 8.5 11 7M8.5 15.5 19.5 8"/>',
  settings:'<circle cx="12" cy="12" r="3"/><path d="M19 13.5v-3l-2.2-.7-.5-1.2 1.1-2.1-2.1-2.1-2.1 1.1-1.2-.5L10.5 3h-3l-.7 2.2-1.2.5-2.1-1.1-2.1 2.1 1.1 2.1-.5 1.2-2.2.7v3l2.2.7.5 1.2-1.1 2.1 2.1 2.1 2.1-1.1 1.2.5.7 2.2h3l.7-2.2 1.2-.5 2.1 1.1 2.1-2.1-1.1-2.1.5-1.2 2.2-.7Z" transform="translate(2.5) scale(.78)"/>',
  user:'<circle cx="12" cy="8" r="4"/><path d="M4 21c.6-5 3.2-7 8-7s7.4 2 8 7"/>',
  swap:'<path d="M4 8h14l-3-3M20 16H6l3 3"/>',
  clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  layers:'<path d="m12 3 9 5-9 5-9-5 9-5Z"/><path d="m3 12 9 5 9-5M3 16l9 5 9-5"/>',
  droplet:'<path d="M12 3s6 6.3 6 11a6 6 0 0 1-12 0c0-4.7 6-11 6-11Z"/>',
  euro:'<path d="M18 7.5a7 7 0 1 0 0 9M5 10h10M5 14h9"/>',
  lock:'<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/>',
  circle:'<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="2"/>',
};

const aliases={
  '☰':'menu','×':'close','✕':'close','✖':'close','＋':'add','+':'add','⌕':'search','🔍':'search','✓':'check','✔':'check','!':'warning','⚠':'warning','✎':'edit','←':'back','→':'forward','⌂':'home','◫':'home','▤':'document','▥':'chart','▦':'grid','▣':'box','▶':'production','●':'production','✂':'scissors','⚙':'settings','♙':'user','⇄':'swap','↔':'swap','⇥':'swap','◷':'clock','⌾':'circle','◉':'circle','◎':'circle','◇':'layers','◈':'layers','✦':'layers','✳':'layers','⌁':'layers','▰':'truck','💧':'droplet','€':'euro','🔒':'lock'
};

export function icon(value='circle',className='ui-icon'){
  const name=paths[value]?value:(aliases[String(value).trim()]||'circle');
  return `<svg class="${className}" viewBox="0 0 24 24" aria-hidden="true" focusable="false">${paths[name]}</svg>`;
}

function enhance(root=document){
  const iconElements=[...(root.matches?.('[data-icon]')?[root]:[]),...(root.querySelectorAll?.('[data-icon]')||[])];
  iconElements.forEach(element=>{if(!element.querySelector('svg'))element.innerHTML=icon(element.dataset.icon)});
  const selectors='nav a>i,.module-nav a>i,.command-icon,.btn.icon,.icon-button,.catalog-select,.metric-icon,.quick-workflows button>span,.all-clear>span,.cost-transition-confirm>span,.service-lock,.stock-material-icon,.sidebar-shortcuts button>i';
  const glyphElements=[...(root.matches?.(selectors)?[root]:[]),...(root.querySelectorAll?.(selectors)||[])];
  glyphElements.forEach(element=>{
    if(element.querySelector('svg'))return;
    const glyph=element.textContent.trim();
    if(aliases[glyph]){element.innerHTML=icon(glyph);element.setAttribute('aria-hidden','true')}
  });
}

export function initIconSystem(){
  enhance(document);
  const observer=new MutationObserver(records=>records.forEach(record=>record.addedNodes.forEach(node=>{if(node.nodeType===1)enhance(node)})));
  observer.observe(document.body,{childList:true,subtree:true});
}
