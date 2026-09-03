import { post } from './api.js?v=20260828-2';
import { clearSession, setCompany, setSession, state } from './state.js';
import { loading, resetTransientUi, toast } from './ui.js?v=20260826-3';
import { recordModal } from './quick_create.js?v=20260826-3';
import { initExperience } from './experience.js?v=20260828-2';
import { DEFAULT_ENABLED_MODULES, MODULES } from './navigation.js?v=20260828-2';

const ASSET = '20260903-5';
const loaded = {};

function load(path) {
  if (!loaded[path]) loaded[path] = import(`${path}?v=${ASSET}`);
  return loaded[path];
}

function lazy(path, view, method = 'render') {
  return {
    render: async (container) => {
      const mod = await load(path);
      const fn = mod[method] || mod.render;
      return view === undefined ? fn(container) : fn(container, view);
    },
  };
}

async function renderDesign(container, view) {
  const { render } = await load('./pages/design.js');
  return render(container, view);
}

async function renderPrimaveraSettings(container) {
  const [{ render }, { openCompanyFiche }] = await Promise.all([
    load('./pages/settings.js'),
    load('./pages/company_fiche.js'),
  ]);
  await render(container, 6, false);
  const company = state.companies.find((row) => Number(row.id) === Number(state.companyId));
  if (company) await openCompanyFiche(container, company, () => render(container, 6, false), { tab: 'erp' });
}

const routes = {
  dashboard: lazy('./pages/dashboard.js'),
  planning: lazy('./pages/confection.js', 'map'),
  live: lazy('./pages/live.js'),
  styles: lazy('./pages/styles.js'),
  samples: lazy('./pages/samples.js'),
  costing: lazy('./pages/costing.js'),
  orders: lazy('./pages/orders.js'),
  confection: lazy('./pages/confection.js'),
  floor: lazy('./pages/floor.js'),
  cutting: lazy('./pages/cutting.js'),
  quality: lazy('./pages/quality.js'),
  revista: lazy('./pages/quality.js'),
  people: lazy('./pages/people.js'),
  machines: lazy('./pages/machines.js'),
  operations: lazy('./pages/operations.js'),
  overheads: lazy('./pages/overheads.js'),
  subcontracts: lazy('./pages/subcontracts.js'),
  reports: lazy('./pages/reports.js'),
  partners: lazy('./pages/partners.js'),
  settings: lazy('./pages/settings.js'),
  shipping: lazy('./pages/shipping.js'),
  tracking: lazy('./pages/tracking.js'),
  'control-tower': lazy('./pages/control_tower.js'),
  'operations-control': lazy('./pages/operations_control.js'),
  'shipping-prepare': lazy('./pages/shipping.js', 'prepare'),
  'shipping-packing': lazy('./pages/shipping.js', 'packing'),
  'shipping-ready': lazy('./pages/shipping.js', 'ready'),
  'shipping-history': lazy('./pages/shipping.js', 'history'),
  'shipping-incidents': lazy('./pages/operations_control.js', 'claims'),
  'design-today': { render: (container) => renderDesign(container, 'today') },
  'design-requests': { render: (container) => renderDesign(container, 'requests') },
  'design-samples': { render: (container) => renderDesign(container, 'samples') },
  'design-organization': { render: (container) => renderDesign(container, 'organization') },
  'design-report': { render: (container) => renderDesign(container, 'report') },
  'erp-docs': lazy('./pages/commercial_docs.js'),
  'erp-orders': lazy('./pages/erp_orders.js'),
  'erp-doc': { render: async (container) => { const mod = await load('./pages/commercial_docs.js'); return mod.renderDocument(container); } },
  'erp-capture': lazy('./erp/capture.js'),
  'erp-map': { render: async (container) => { const mod = await load('./erp/capture.js'); return mod.renderAliases(container); } },
  'confection-map': lazy('./pages/confection.js', 'map'),
  'confection-days': lazy('./pages/confection.js', 'days'),
  'confection-plans': lazy('./pages/confection.js', 'plans'),
  'confection-execution': lazy('./pages/confection.js', 'execution'),
  'confection-skills': lazy('./pages/confection.js', 'skills'),
  'confection-events': lazy('./pages/confection.js', 'events'),
  'confection-shifts': lazy('./pages/confection.js', 'shifts'),
  'confection-external': lazy('./pages/confection.js', 'external'),
  'confection-lines': lazy('./pages/confection.js', 'lines'),
  'confection-machine-types': lazy('./pages/confection.js', 'machineTypes'),
  'confection-contractors': lazy('./pages/confection.js', 'contractors'),
  'confection-costs': lazy('./pages/confection.js', 'costs'),
  'confection-diary': lazy('./pages/confection.js', 'diary'),
  dyeing: lazy('./pages/process.js', 'dyeing'),
  printing: lazy('./pages/process.js', 'printing'),
  weaving: lazy('./pages/process.js', 'weaving'),
  spinning: lazy('./pages/process.js', 'spinning'),
  corte: { render: async (container) => { const mod = await load('./pages/cutting.js'); return mod.renderMap(container); } },
  'corte-jobs': lazy('./pages/process.js', 'corte'),
  'corte-lines': { render: async (container) => { const mod = await load('./pages/cutting.js'); return mod.renderLines(container); } },
  laundry: lazy('./pages/process.js', 'laundry'),
  embroidery: lazy('./pages/process.js', 'embroidery'),
  finishing: lazy('./pages/process.js', 'finishing'),
  'stock-mp': lazy('./pages/inventory.js', 'mp'),
  'stock-wip': lazy('./pages/inventory.js', 'wip'),
  embalagem: lazy('./pages/inventory.js', 'packing'),
  'stock-fg': lazy('./pages/inventory.js', 'fg'),
  purchases: lazy('./pages/inventory.js', 'purchases'),
  inventory: lazy('./pages/inventory.js', 'mp'),
  'stock-mrp': lazy('./pages/inventory.js', 'mrp'),
  'settings-users': { render: async (container) => { const mod = await load('./pages/settings.js'); return mod.render(container, 4, false); } },
  'settings-companies': { render: async (container) => { const mod = await load('./pages/settings.js'); return mod.render(container, 6, false); } },
  'settings-primavera': { render: renderPrimaveraSettings },
  'tables-customers': lazy('./pages/tables.js', 'customers'),
  'tables-suppliers': lazy('./pages/tables.js', 'suppliers'),
  'tables-article-types': lazy('./pages/article_types.js'),
  'tables-service-stages': lazy('./pages/tables.js', 'service-stages'),
  'tables-items': lazy('./pages/tables.js', 'items'),
  'tables-banks': lazy('./pages/tables.js', 'banks'),
  'tables-exchange-rates': lazy('./pages/tables.js', 'exchange-rates'),
};

const loginScreen = document.getElementById('login-screen');
const shell = document.getElementById('app-shell');
const content = document.getElementById('page-content');

function currentMembership() { return state.companies.find((company) => Number(company.id) === Number(state.companyId)) || {}; }
function allowedModules() {
  const membership = currentMembership();
  let explicit = Array.isArray(membership.permissions) ? membership.permissions : [];
  if (!membership.id) return [];
  if (explicit.includes('none')) return [];
  const enabled = new Set(membership.enabled_modules?.length ? membership.enabled_modules : DEFAULT_ENABLED_MODULES);
  const legacy = { product: ['commercial', 'design'], logistics: ['shipping', 'subcontracting', 'warehouse', 'inventory'] };
  let visible = MODULES.filter((module) => enabled.has(module.id));
  if (explicit.includes('*')) return visible;
  if (explicit.length) {
    explicit = [...new Set(explicit.flatMap((id) => legacy[id] || [id]))];
    return visible.filter((module) => explicit.includes(module.id));
  }
  return visible.filter((module) => module.defaultRoles.includes(membership.role || 'viewer'));
}
function moduleForRoute(route) {
  if (route === 'settings-primavera') {
    return allowedModules().find((module) => module.id === 'management') || allowedModules().find((module) => module.id === 'erp') || allowedModules()[0] || null;
  }
  return allowedModules().find((module) => module.routes.some((item) => item[0] === route || (route === 'erp-doc' && item[0] === 'erp-docs'))) || allowedModules()[0] || null;
}
function canNavigateTo(route) {
  if (route === 'settings-primavera') return allowedModules().some((module) => module.id === 'management' || module.id === 'erp');
  if (route === 'inventory' || route === 'stock-mrp') return allowedModules().some((module) => module.routes.some((item) => item[0] === 'stock-mp'));
  return allowedModules().some((module) => module.routes.some((item) => item[0] === route || (route === 'erp-doc' && item[0] === 'erp-docs')));
}
function navLink([key, label, icon], route) {
  return `<a href="#/${key}" data-route="${key}" class="${key === route ? 'active' : ''}"><i>${icon}</i><span>${label}</span></a>`;
}
function navBlock(title, items, route) {
  if (!items.length) return '';
  return `<div class="nav-section">${title}</div>${items.map((item) => navLink(item, route)).join('')}`;
}
function navGroup(moduleId, group, items, route) {
  if (!items.length) return '';
  const storageKey = `tf_nav_${moduleId}_${group.id}`;
  const activeHere = items.some((item) => item[0] === route);
  const stored = localStorage.getItem(storageKey);
  const open = activeHere || (stored === null ? !group.collapsed : stored === '1');
  return `<details class="nav-group ${group.collapsed ? 'is-setup' : ''}" data-nav-group="${storageKey}" ${open ? 'open' : ''}>
    <summary><span class="nav-group-title">${group.title}</span>${group.hint ? `<small>${group.hint}</small>` : ''}</summary>
    ${items.map((item) => navLink(item, route)).join('')}
  </details>`;
}
function fillCompanyCard() {
  const company = currentMembership();
  const nameEl = document.getElementById('company-card-name');
  const metaEl = document.getElementById('company-card-meta');
  if (nameEl) nameEl.textContent = company.name || '—';
  if (metaEl) {
    const nif = company.tax_id ? `NIF ${company.tax_id}` : 'sem NIF';
    metaEl.textContent = `${nif} · ${new Date().getFullYear()}`;
  }
}
function renderNavigation(route) {
  const visible = allowedModules(), active = moduleForRoute(route), permitted = new Set(visible.flatMap((module) => module.routes.map((item) => item[0]))), quick = active?.quick.filter(([key]) => permitted.has(key)) || [];
  const moduleNav = document.getElementById('module-nav');
  moduleNav.style.setProperty('--module-count', Math.max(1, visible.length));
  moduleNav.innerHTML = visible.map((module) => `<a href="#/${module.home}" class="${module.id === active?.id ? 'active' : ''}" title="${module.label}"><i>${module.icon}</i><span>${module.shortLabel || module.label}</span></a>`).join('');
  document.getElementById('sidebar-module-title').textContent = active?.label || 'Sem acesso';
  fillCompanyCard();
  const navRoute = route === 'erp-doc' ? 'erp-docs' : route === 'settings-primavera' ? 'settings-companies' : route;
  const mainNav = document.getElementById('main-nav');
  if (!active) {
    mainNav.innerHTML = '';
  } else if (active.navGroups) {
    mainNav.innerHTML = active.navGroups.map((group) => navGroup(active.id, group, active.routes.filter((item) => item[3] === group.id), navRoute)).join('');
    mainNav.querySelectorAll('details[data-nav-group]').forEach((el) => {
      el.addEventListener('toggle', () => localStorage.setItem(el.dataset.navGroup, el.open ? '1' : '0'));
    });
  } else {
    const daily = active.routes.filter((item) => !item[3]);
    const recursos = active.routes.filter((item) => item[3] === 'recursos');
    const cadastro = active.routes.filter((item) => item[3] === 'cadastro');
    const dailyTitle = recursos.length || ['production', 'quality', 'shipping', 'warehouse'].includes(active.id) ? 'HOJE' : 'OPÇÕES';
    mainNav.innerHTML = `${navBlock(dailyTitle, daily, navRoute)}${navBlock('RECURSOS', recursos, navRoute)}${navBlock('CADASTROS', cadastro, navRoute)}`;
  }
  document.getElementById('sidebar-shortcuts').innerHTML = active && quick.length ? `<span>TRANSIÇÃO RÁPIDA</span>${quick.map(([key, label]) => `<button data-shortcut-route="${key}">${label}<i>→</i></button>`).join('')}` : '';
}

function showApp() {
  loginScreen.classList.add('hidden'); shell.classList.remove('hidden');
  const select = document.getElementById('company-select'); select.innerHTML = state.companies.map((company) => `<option value="${company.id}" ${company.id === state.companyId ? 'selected' : ''}>${company.name}</option>`).join('');
  const who = state.user?.name || state.user?.username || 'Utilizador';
  const role = currentMembership().role || '';
  document.getElementById('user-button').textContent = who.charAt(0).toUpperCase();
  document.getElementById('user-button').setAttribute('aria-label', `Conta de ${who}`);
  const meta = document.getElementById('user-meta');
  if (meta) meta.textContent = role ? `${who} · ${role}` : who;
  fillCompanyCard();
}

let navGen = 0;

async function navigate() {
  const gen = ++navGen;
  resetTransientUi();
  let route = (location.hash.replace(/^#\//, '').split(/[/?]/)[0] || 'dashboard');
  if (route === 'planning') route = 'confection-map';
  const visibleModules = allowedModules();
  if (!visibleModules.length) { renderNavigation(route); content.innerHTML = `<section class="access-empty"><span>◎</span><h1>Sem módulos atribuídos</h1><p>O seu utilizador está ativo, mas ainda não tem módulos visíveis nesta empresa.</p><button class="btn" id="access-logout">Terminar sessão</button></section>`; document.getElementById('access-logout').addEventListener('click', logout); return; }
  const permitted = new Set(visibleModules.flatMap((module) => module.routes.map((item) => item[0])));
  if (permitted.has('erp-docs')) permitted.add('erp-doc');
  if (permitted.has('stock-mp')) { permitted.add('inventory'); permitted.add('stock-wip'); permitted.add('stock-fg'); permitted.add('purchases'); permitted.add('stock-mrp'); }
  if (visibleModules.some((module) => module.id === 'management' || module.id === 'erp')) permitted.add('settings-primavera');
  if (!permitted.has(route)) { route = visibleModules[0].home; if (location.hash !== `#/${route}`) { location.hash = `#/${route}`; return; } }
  const module = routes[route] || routes.dashboard;
  renderNavigation(route);
  document.querySelector('.sidebar').classList.remove('open');
  content.innerHTML = loading();
  try {
    await module.render(content);
    if (gen !== navGen) return;
  } catch (error) {
    if (gen !== navGen) return;
    if (error.status === 401) { logout(); return; }
    if (error.status === 403 && state.user?.must_change_password) { await forcePasswordChange(); return navigate(); }
    content.innerHTML = `<div class="card"><h2>Não foi possível abrir este módulo</h2><p class="muted">${error.message}</p><button class="btn" onclick="location.reload()">Tentar novamente</button></div>`;
    toast(error.message, 'error');
  }
}

function logout() { clearSession(); shell.classList.add('hidden'); loginScreen.classList.remove('hidden'); location.hash = ''; document.getElementById('login-message').textContent = ''; }

function forcePasswordChange() {
  const ask = () => new Promise((resolve, reject) => {
    recordModal({
      title: 'Altere a palavra-passe inicial',
      subtitle: 'Tem de escolher uma senha nova (mínimo 8 caracteres) antes de usar o sistema.',
      lock: true,
      fields: [
        { key: 'current_password', label: 'Palavra-passe atual', type: 'password', required: true },
        { key: 'new_password', label: 'Nova palavra-passe', type: 'password', required: true, help: 'Mínimo de 8 caracteres, diferente de admin123.' },
      ],
      save: async (payload) => {
        const result = await post('/auth/change-password', payload);
        if (result?.token) { localStorage.setItem('tf_token', result.token); setSession(result); }
        return result;
      },
      onSaved: () => { toast('Palavra-passe alterada.'); resolve(); },
    });
    document.getElementById('modal-close')?.addEventListener('click', () => {
      toast('Tem de alterar a palavra-passe para continuar.', 'error');
      reject(new Error('closed'));
    }, { once: true });
  });
  const loop = async () => {
    while (state.user?.must_change_password) {
      try { await ask(); } catch { /* reabre até gravar */ }
    }
  };
  return loop();
}

let appStarted = false;

export async function bootApp() {
  if (!appStarted) {
    appStarted = true;
    resetTransientUi();
    initExperience({ canNavigate: canNavigateTo });
    document.getElementById('logout-button').addEventListener('click', logout);
    document.getElementById('menu-toggle').addEventListener('click', () => document.querySelector('.sidebar').classList.toggle('open'));
    document.getElementById('company-select').addEventListener('change', (event) => { setCompany(event.target.value); navigate(); });
    document.getElementById('sidebar-shortcuts').addEventListener('click', (event) => { const button = event.target.closest('[data-shortcut-route]'); if (button) location.hash = `#/${button.dataset.shortcutRoute}`; });
    document.getElementById('user-button').addEventListener('click', () => recordModal({ title: 'Alterar palavra-passe', fields: [{ key: 'current_password', label: 'Palavra-passe atual', type: 'password', required: true }, { key: 'new_password', label: 'Nova palavra-passe', type: 'password', required: true, help: 'Mínimo de 8 caracteres.' }], save: async (payload) => { const result = await post('/auth/change-password', payload); if (result?.token) { localStorage.setItem('tf_token', result.token); setSession(result); } return result; }, onSaved: () => toast('Palavra-passe alterada.') }));
    window.addEventListener('hashchange', navigate);
  }
  showApp();
  if (state.user?.must_change_password) await forcePasswordChange();
  try { await navigate(); } catch (error) { content.innerHTML = `<div class="card"><h2>Não foi possível iniciar a área de trabalho</h2><p class="muted">${error.message}</p><button class="btn" onclick="location.reload()">Tentar novamente</button></div>`; toast(error.message, 'error'); }
}

if (!document.querySelector('script[src*="login.js"]')) {
  import('./login.js?v=20260903-5');
}
