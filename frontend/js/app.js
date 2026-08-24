import { post } from './api.js?v=20260822-16';
import { clearSession, setCompany, setSession, state } from './state.js';
import { loading, resetTransientUi, toast } from './ui.js?v=20260824-42';
import { recordModal } from './quick_create.js?v=20260821-19';
import { initExperience } from './experience.js?v=20260824-43';
import * as dashboard from './pages/dashboard.js?v=20260822-10';
import * as live from './pages/live.js?v=20260819-7';
import * as styles from './pages/styles.js?v=20260824-41';
import * as samples from './pages/samples.js?v=20260822-30';
import * as costing from './pages/costing.js?v=20260824-41';
import * as orders from './pages/orders.js?v=20260825-48';
import * as floor from './pages/floor.js?v=20260822-30';
import * as cutting from './pages/cutting.js?v=20260824-41';
import * as quality from './pages/quality.js?v=20260824-1';
import * as inventoryPage from './pages/inventory.js?v=20260824-3';
import * as people from './pages/people.js?v=20260822-1';
import * as machines from './pages/machines.js?v=20260824-41';
import * as operations from './pages/operations.js?v=20260822-1';
import * as overheads from './pages/overheads.js?v=20260819-8';
import * as confection from './pages/confection.js?v=20260824-41';
import * as processPlant from './pages/process.js?v=20260820-1';
import * as tracking from './pages/tracking.js?v=20260824-1';
import * as controlTower from './pages/control_tower.js?v=20260824-2';
import * as operationsControl from './pages/operations_control.js?v=20260824-40';
import * as subcontracts from './pages/subcontracts.js?v=20260824-41';
import * as reports from './pages/reports.js?v=20260819-7';
import * as partners from './pages/partners.js?v=20260824-41';
import * as tables from './pages/tables.js?v=20260824-41';
import * as shipping from './pages/shipping.js?v=20260824-2';
import * as commercialDocs from './pages/commercial_docs.js?v=20260824-41';
import * as erpOrders from './pages/erp_orders.js?v=20260824-1';
import * as settings from './pages/settings.js?v=20260822-27';
import { DEFAULT_ENABLED_MODULES, MODULES } from './navigation.js?v=20260824-2';

async function renderDesign(container, view) {
  const { render } = await import('./pages/design.js?v=20260824-41');
  return render(container, view);
}

const routes={dashboard,planning:tracking,live,styles,samples,costing,orders,confection,floor,cutting,quality,revista:quality,people,machines,operations,overheads,subcontracts,reports,partners,settings,shipping,tracking,'control-tower':controlTower,
  'operations-control':operationsControl,
  'design-today':{render:container=>renderDesign(container,'today')},
  'design-requests':{render:container=>renderDesign(container,'requests')},
  'design-samples':{render:container=>renderDesign(container,'samples')},
  'design-organization':{render:container=>renderDesign(container,'organization')},
  'design-report':{render:container=>renderDesign(container,'report')},
  'erp-docs':commercialDocs,
  'erp-orders':erpOrders,
  'erp-doc':{render:container=>commercialDocs.renderDocument(container)},
  'erp-capture':{render:container=>commercialDocs.renderCapture(container)},
  'erp-map':{render:container=>commercialDocs.renderAliases(container)},
  'confection-map':{render:container=>confection.render(container,'map')},'confection-days':{render:container=>confection.render(container,'days')},'confection-plans':{render:container=>confection.render(container,'plans')},'confection-execution':{render:container=>confection.render(container,'execution')},'confection-skills':{render:container=>confection.render(container,'skills')},'confection-events':{render:container=>confection.render(container,'events')},'confection-shifts':{render:container=>confection.render(container,'shifts')},'confection-external':{render:container=>confection.render(container,'external')},'confection-lines':{render:container=>confection.render(container,'lines')},'confection-machine-types':{render:container=>confection.render(container,'machineTypes')},'confection-contractors':{render:container=>confection.render(container,'contractors')},
  'confection-costs':{render:container=>confection.render(container,'costs')},
  'confection-diary':{render:container=>confection.render(container,'diary')},
  dyeing:{render:container=>processPlant.render(container,'dyeing')},
  printing:{render:container=>processPlant.render(container,'printing')},
  weaving:{render:container=>processPlant.render(container,'weaving')},
  spinning:{render:container=>processPlant.render(container,'spinning')},
  corte:{render:container=>cutting.renderMap(container)},
  'corte-jobs':{render:container=>processPlant.render(container,'corte')},
  'corte-lines':{render:container=>cutting.renderLines(container)},
  laundry:{render:container=>processPlant.render(container,'laundry')},
  embroidery:{render:container=>processPlant.render(container,'embroidery')},
  finishing:{render:container=>processPlant.render(container,'finishing')},
  'stock-mp':{render:container=>inventoryPage.render(container,'mp')},
  'stock-wip':{render:container=>inventoryPage.render(container,'wip')},
  embalagem:{render:container=>inventoryPage.render(container,'packing')},
  'stock-fg':{render:container=>inventoryPage.render(container,'fg')},
  purchases:{render:container=>inventoryPage.render(container,'purchases')},
  inventory:{render:container=>inventoryPage.render(container,'mp')},
  'settings-users':{render:container=>settings.render(container,4,false)},
  'settings-companies':{render:container=>settings.render(container,6,false)},
  'settings-primavera':{render:container=>settings.render(container,7,false)},
  'tables-customers':{render:container=>tables.render(container,'customers')},
  'tables-suppliers':{render:container=>tables.render(container,'suppliers')},
  'tables-service-stages':{render:container=>tables.render(container,'service-stages')},
  'tables-items':{render:container=>tables.render(container,'items')},
  'tables-banks':{render:container=>tables.render(container,'banks')},
  'tables-exchange-rates':{render:container=>tables.render(container,'exchange-rates')},
};
const loginScreen=document.getElementById('login-screen');
const shell=document.getElementById('app-shell');
const content=document.getElementById('page-content');

function currentMembership(){return state.companies.find(company=>Number(company.id)===Number(state.companyId))||{};}
function allowedModules(){
  const membership=currentMembership();
  let explicit=Array.isArray(membership.permissions)?membership.permissions:[];
  if(!membership.id)return[];
  if(explicit.includes('none'))return[];
  const enabled=new Set(membership.enabled_modules?.length?membership.enabled_modules:DEFAULT_ENABLED_MODULES);
  const legacy={product:['commercial','design'],logistics:['shipping','subcontracting','inventory']};
  let visible=MODULES.filter(module=>enabled.has(module.id));
  if(explicit.includes('*'))return visible;
  if(explicit.length){
    explicit=[...new Set(explicit.flatMap(id=>legacy[id]||[id]))];
    return visible.filter(module=>explicit.includes(module.id));
  }
  return visible.filter(module=>module.defaultRoles.includes(membership.role||'viewer'));
}
function moduleForRoute(route){return allowedModules().find(module=>module.routes.some(item=>item[0]===route||(route==='erp-doc'&&item[0]==='erp-docs')))||allowedModules()[0]||null;}
function canNavigateTo(route){return allowedModules().some(module=>module.routes.some(item=>item[0]===route||(route==='erp-doc'&&item[0]==='erp-docs')));}
function navLink([key,label,icon], route){
  return `<a href="#/${key}" data-route="${key}" class="${key===route?'active':''}"><i>${icon}</i><span>${label}</span></a>`;
}
function navBlock(title, items, route){
  if(!items.length)return '';
  return `<div class="nav-section">${title}</div>${items.map(item=>navLink(item,route)).join('')}`;
}
function navGroup(moduleId, group, items, route){
  if(!items.length)return '';
  const storageKey=`tf_nav_${moduleId}_${group.id}`;
  const activeHere=items.some(item=>item[0]===route);
  const stored=localStorage.getItem(storageKey);
  const open=activeHere || (stored===null ? !group.collapsed : stored==='1');
  return `<details class="nav-group ${group.collapsed?'is-setup':''}" data-nav-group="${storageKey}" ${open?'open':''}>
    <summary><span class="nav-group-title">${group.title}</span>${group.hint?`<small>${group.hint}</small>`:''}</summary>
    ${items.map(item=>navLink(item,route)).join('')}
  </details>`;
}
function fillCompanyCard(){
  const company=currentMembership();
  const nameEl=document.getElementById('company-card-name');
  const metaEl=document.getElementById('company-card-meta');
  if(nameEl) nameEl.textContent=company.name||'—';
  if(metaEl){
    const nif=company.tax_id?`NIF ${company.tax_id}`:'sem NIF';
    metaEl.textContent=`${nif} · ${new Date().getFullYear()}`;
  }
}
function renderNavigation(route){
  const visible=allowedModules(),active=moduleForRoute(route),permitted=new Set(visible.flatMap(module=>module.routes.map(item=>item[0]))),quick=active?.quick.filter(([key])=>permitted.has(key))||[];
  const moduleNav=document.getElementById('module-nav');
  moduleNav.style.setProperty('--module-count',Math.max(1,visible.length));
  moduleNav.innerHTML=visible.map(module=>`<a href="#/${module.home}" class="${module.id===active?.id?'active':''}" title="${module.label}"><i>${module.icon}</i><span>${module.shortLabel||module.label}</span></a>`).join('');
  document.getElementById('sidebar-module-title').textContent=active?.label||'Sem acesso';
  fillCompanyCard();
  const navRoute=route==='erp-doc'?'erp-docs':route;
  const mainNav=document.getElementById('main-nav');
  if(!active){
    mainNav.innerHTML='';
  }else if(active.navGroups){
    mainNav.innerHTML=active.navGroups.map(group=>navGroup(active.id,group,active.routes.filter(item=>item[3]===group.id),navRoute)).join('');
    mainNav.querySelectorAll('details[data-nav-group]').forEach(el=>{
      el.addEventListener('toggle',()=>localStorage.setItem(el.dataset.navGroup,el.open?'1':'0'));
    });
  }else{
    const daily=active.routes.filter(item=>!item[3]);
    const recursos=active.routes.filter(item=>item[3]==='recursos');
    const cadastro=active.routes.filter(item=>item[3]==='cadastro');
    const dailyTitle=recursos.length||['production','quality','shipping','inventory'].includes(active.id)?'HOJE':'OPÇÕES';
    mainNav.innerHTML=`${navBlock(dailyTitle,daily,navRoute)}${navBlock('RECURSOS',recursos,navRoute)}${navBlock('CADASTROS',cadastro,navRoute)}`;
  }
  document.getElementById('sidebar-shortcuts').innerHTML=active&&quick.length?`<span>TRANSIÇÃO RÁPIDA</span>${quick.map(([key,label])=>`<button data-shortcut-route="${key}">${label}<i>→</i></button>`).join('')}`:'';
}

function showApp(){
  loginScreen.classList.add('hidden');shell.classList.remove('hidden');
  const select=document.getElementById('company-select');select.innerHTML=state.companies.map(company=>`<option value="${company.id}" ${company.id===state.companyId?'selected':''}>${company.name}</option>`).join('');
  const who=state.user?.name||state.user?.username||'Utilizador';
  const role=currentMembership().role||'';
  document.getElementById('user-button').textContent=who.charAt(0).toUpperCase();
  document.getElementById('user-button').setAttribute('aria-label',`Conta de ${who}`);
  const meta=document.getElementById('user-meta');
  if(meta) meta.textContent=role?`${who} · ${role}`:who;
  fillCompanyCard();
}

async function navigate(){
  resetTransientUi();
  let route=(location.hash.replace(/^#\//,'').split(/[/?]/)[0]||'dashboard');
  if(route==='planning')route='tracking';
  const visibleModules=allowedModules();
  if(!visibleModules.length){renderNavigation(route);content.innerHTML=`<section class="access-empty"><span>◎</span><h1>Sem módulos atribuídos</h1><p>O seu utilizador está ativo, mas ainda não tem módulos visíveis nesta empresa.</p><button class="btn" id="access-logout">Terminar sessão</button></section>`;document.getElementById('access-logout').addEventListener('click',logout);return;}
  const permitted=new Set(visibleModules.flatMap(module=>module.routes.map(item=>item[0])));
  if(permitted.has('erp-docs'))permitted.add('erp-doc');
  if(permitted.has('inventory')){permitted.add('stock-mp');permitted.add('stock-wip');permitted.add('stock-fg');permitted.add('purchases');}
  if(!permitted.has(route)){route=visibleModules[0].home;if(location.hash!==`#/${route}`){location.hash=`#/${route}`;return;}}
  const module=routes[route]||dashboard;
  renderNavigation(route);
  document.querySelector('.sidebar').classList.remove('open');
  content.innerHTML=loading();
  try{await module.render(content);}catch(error){
    if(error.status===401){logout();return;}
    content.innerHTML=`<div class="card"><h2>Não foi possível abrir este módulo</h2><p class="muted">${error.message}</p><button class="btn" onclick="location.reload()">Tentar novamente</button></div>`;
    toast(error.message,'error');
  }
}

function logout(){clearSession();shell.classList.add('hidden');loginScreen.classList.remove('hidden');location.hash='';document.getElementById('login-message').textContent='';}

function forcePasswordChange(){
  return new Promise(resolve=>{
    recordModal({
      title:'Altere a palavra-passe inicial',
      subtitle:'admin123 não deve ficar na rede da fábrica. Pode fechar e alterar depois no círculo do utilizador.',
      fields:[
        {key:'current_password',label:'Palavra-passe atual',type:'password',required:true},
        {key:'new_password',label:'Nova palavra-passe',type:'password',required:true,help:'Mínimo de 8 caracteres, diferente de admin123.'},
      ],
      save:async payload=>{
        const result=await post('/auth/change-password',payload);
        if(result?.token){localStorage.setItem('tf_token',result.token);setSession(result);}
        return result;
      },
      onSaved:()=>{toast('Palavra-passe alterada.');resolve();},
    });
  });
}

let appStarted=false;

export async function bootApp(){
  if(!appStarted){
    appStarted=true;
    resetTransientUi();
    initExperience({canNavigate:canNavigateTo});
    document.getElementById('logout-button').addEventListener('click',logout);
    document.getElementById('menu-toggle').addEventListener('click',()=>document.querySelector('.sidebar').classList.toggle('open'));
    document.getElementById('company-select').addEventListener('change',event=>{setCompany(event.target.value);navigate();});
    document.getElementById('sidebar-shortcuts').addEventListener('click',event=>{const button=event.target.closest('[data-shortcut-route]');if(button)location.hash=`#/${button.dataset.shortcutRoute}`;});
    document.getElementById('user-button').addEventListener('click',()=>recordModal({title:'Alterar palavra-passe',fields:[{key:'current_password',label:'Palavra-passe atual',type:'password',required:true},{key:'new_password',label:'Nova palavra-passe',type:'password',required:true,help:'Mínimo de 8 caracteres.'}],save:async payload=>{const result=await post('/auth/change-password',payload);if(result?.token){localStorage.setItem('tf_token',result.token);setSession(result);}return result;},onSaved:()=>toast('Palavra-passe alterada.')}));
    window.addEventListener('hashchange',navigate);
  }
  showApp();
  try{await navigate();}catch(error){content.innerHTML=`<div class="card"><h2>Não foi possível iniciar a área de trabalho</h2><p class="muted">${error.message}</p><button class="btn" onclick="location.reload()">Tentar novamente</button></div>`;toast(error.message,'error');}
}

if(!document.querySelector('script[src*="login.js"]')){
  import('./login.js?v=20260822-21');
}
