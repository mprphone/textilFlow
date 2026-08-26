import { crudList } from './api.js';
import { esc } from './format.js?v=20260826-3';
import { state } from './state.js';

export const CIVA = [
  {code:'23', name:'IVA 23%', rate:23},
  {code:'13', name:'IVA intermédio 13%', rate:13},
  {code:'6', name:'IVA reduzido 6%', rate:6},
  {code:'0', name:'Isento', rate:0},
];

export const UNITS = [
  {code:'UN', name:'Unidade'},
  {code:'KG', name:'Quilograma'},
  {code:'M', name:'Metro'},
  {code:'MT', name:'Metro linear'},
  {code:'PAR', name:'Par'},
  {code:'CX', name:'Caixa'},
  {code:'RL', name:'Rolo'},
  {code:'H', name:'Hora'},
];

let layer;

function ensureLayer() {
  if (layer) return layer;
  layer = document.createElement('div');
  layer.className = 'pri-lookup-layer hidden';
  layer.innerHTML = `<div class="pri-lookup" role="dialog" aria-modal="true">
    <header><span data-f4-title>Tabela</span><button type="button" class="icon-button" data-icon="close" data-f4-close aria-label="Fechar" title="Fechar (Esc)"></button></header>
    <div class="pri-lookup-tools"><input data-f4-filter placeholder="Procurar"></div>
    <div class="table-wrap"><table class="data-table pri-lookup-table"><thead data-f4-head></thead><tbody data-f4-body></tbody></table></div>
    <footer><small>Enter confirma · Esc fecha</small></footer>
  </div>`;
  document.body.appendChild(layer);
  return layer;
}

function hideLookup() {
  ensureLayer().classList.add('hidden');
}

export function f4Field(name, value, {placeholder = '', width} = {}) {
  const style = width ? `style="width:${width}"` : '';
  return `<span class="pri-f4wrap"${style}><input class="pri-lookup-in" name="${esc(name)}" value="${esc(value || '')}" placeholder="${esc(placeholder)}" data-f4-field="${esc(name)}" autocomplete="off"></span>`;
}

export async function loadTable(kind, catalog, side) {
  if (kind === 'documento' || kind === 'doc_type' || kind === 'erp_code') {
    return (catalog.types || []).map(item => ({
      code: item.code, name: item.label, id: item.id, series: item.default_series, side: item.side,
    }));
  }
  if (kind === 'serie' || kind === 'series') {
    return (catalog.series || ['A']).map(code => ({code, name:`Série ${code}`}));
  }
  if (kind === 'civa' || kind === 'vat_code') {
    return CIVA.map(item => ({code: item.code, name: item.name, rate: item.rate}));
  }
  if (kind === 'un' || kind === 'unit') {
    return UNITS.map(item => ({code: item.code, name: item.name}));
  }
  const map = {
    entidade: side === 'purchase' ? 'suppliers' : 'customers',
    entity: side === 'purchase' ? 'suppliers' : 'customers',
    customer_id: 'customers',
    supplier_id: 'suppliers',
    artigo: 'materials',
    code: 'materials',
    warehouse: 'warehouses',
    armazem: 'warehouses',
    condpag: 'payment-terms',
    payment_term: 'payment-terms',
  };
  const resource = map[kind];
  if (!resource) return [];
  try {
    return await crudList(resource, state.companyId, 'limit=2000');
  } catch {
    return [];
  }
}

export function columnsFor(kind) {
  if (kind === 'documento' || kind === 'doc_type' || kind === 'erp_code') return [{key:'code',label:'Documento'},{key:'name',label:'Descrição'},{key:'side',label:'Família'}];
  if (kind === 'serie' || kind === 'series') return [{key:'code',label:'Série'},{key:'name',label:'Descrição'}];
  if (kind === 'civa' || kind === 'vat_code') return [{key:'code',label:'CIVA'},{key:'name',label:'Descrição'},{key:'rate',label:'%'}];
  if (kind === 'un' || kind === 'unit') return [{key:'code',label:'UN'},{key:'name',label:'Descrição'}];
  if (kind === 'artigo' || kind === 'code') return [{key:'code',label:'Artigo'},{key:'name',label:'Descrição'},{key:'unit',label:'UN'},{key:'vat_code',label:'CIVA'},{key:'warehouse',label:'Arm.'}];
  if (kind === 'warehouse' || kind === 'armazem') return [{key:'code',label:'Armazém'},{key:'name',label:'Descrição'}];
  if (kind === 'condpag' || kind === 'payment_term') return [{key:'code',label:'CondPag'},{key:'name',label:'Descrição'},{key:'days',label:'Dias'}];
  return [{key:'code',label:'Código'},{key:'name',label:'Nome'},{key:'tax_id',label:'NIF'},{key:'city',label:'Localidade'}];
}

export function titleFor(kind, side) {
  const titles = {
    documento:'Tabela de documentos', doc_type:'Tabela de documentos', erp_code:'Tabela de documentos',
    serie:'Séries', series:'Séries',
    entidade: side === 'purchase' ? 'Tabela de fornecedores' : 'Tabela de clientes',
    entity: side === 'purchase' ? 'Tabela de fornecedores' : 'Tabela de clientes',
    artigo:'Tabela de artigos', code:'Tabela de artigos',
    warehouse:'Tabela de armazéns', armazem:'Tabela de armazéns',
    civa:'Códigos de IVA', vat_code:'Códigos de IVA',
    un:'Unidades', unit:'Unidades',
    condpag:'Condições de pagamento', payment_term:'Condições de pagamento',
  };
  return titles[kind] || 'Tabela';
}

export function openF4({kind, catalog, side, onPick}) {
  const host = ensureLayer();
  const columns = columnsFor(kind);
  host.querySelector('[data-f4-title]').textContent = titleFor(kind, side);
  host.querySelector('[data-f4-head]').innerHTML = `<tr>${columns.map(col => `<th>${esc(col.label)}</th>`).join('')}</tr>`;
  const body = host.querySelector('[data-f4-body]');
  const filter = host.querySelector('[data-f4-filter]');
  let rows = [];
  let selected = 0;

  const draw = () => {
    const q = (filter.value || '').toLowerCase();
    const visible = rows.filter(row => !q || Object.values(row).some(value => String(value ?? '').toLowerCase().includes(q)));
    selected = Math.min(selected, Math.max(0, visible.length - 1));
    body.innerHTML = visible.length
      ? visible.map((row, index) => `<tr data-f4-index="${index}" class="${index===selected?'is-selected':''}">${columns.map(col => `<td>${esc(row[col.key] ?? '—')}</td>`).join('')}</tr>`).join('')
      : `<tr><td colspan="${columns.length}">Sem registos. Confirme se a tabela está preenchida ou puxe do Primavera.</td></tr>`;
    body.querySelectorAll('tr[data-f4-index]').forEach(tr => {
      tr.addEventListener('click', () => { selected = Number(tr.dataset.f4Index); draw(); });
      tr.addEventListener('dblclick', () => pick(visible));
    });
    body.querySelector('.is-selected')?.scrollIntoView({block:'nearest'});
    return visible;
  };

  const pick = (visible) => {
    const row = (visible || draw())[selected];
    if (!row) return;
    hideLookup();
    onPick(row);
  };

  const onKey = event => {
    const visible = draw();
    if (event.key === 'Escape') { event.preventDefault(); hideLookup(); cleanup(); }
    if (event.key === 'ArrowDown') { event.preventDefault(); selected += 1; draw(); }
    if (event.key === 'ArrowUp') { event.preventDefault(); selected -= 1; if (selected < 0) selected = 0; draw(); }
    if (event.key === 'Enter' || event.key === 'F4') { event.preventDefault(); pick(visible); }
  };

  const cleanup = () => {
    document.removeEventListener('keydown', onKey, true);
    host.classList.add('hidden');
  };

  host.querySelector('[data-f4-close]').onclick = cleanup;
  host.onclick = event => { if (event.target === host) cleanup(); };
  filter.oninput = () => { selected = 0; draw(); };
  document.addEventListener('keydown', onKey, true);
  host.classList.remove('hidden');
  filter.value = '';
  filter.focus();

  loadTable(kind, catalog, side).then(data => { rows = data; draw(); });
}

export function matchRow(rows, code) {
  const needle = String(code || '').trim().toLowerCase();
  if (!needle) return null;
  return rows.find(row => String(row.code || '').toLowerCase() === needle)
    || rows.find(row => String(row.code || '').toLowerCase().startsWith(needle))
    || null;
}
