import { esc, money, number } from '../format.js?v=20260819-6';

const PAGE_SIZE = 12;

export function filterCatalog(rows, query) {
  const needle = (query || '').trim().toLocaleLowerCase('pt');
  if (!needle) return rows;
  return rows.filter(row => Object.values(row).some(value =>
    ['string', 'number'].includes(typeof value) && String(value).toLocaleLowerCase('pt').includes(needle)
  ));
}

function pageRows(rows, page) {
  const pages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
  const current = Math.min(Math.max(1, page || 1), pages);
  return { current, pages, rows: rows.slice((current - 1) * PAGE_SIZE, current * PAGE_SIZE) };
}

function pager(kind, page, pages, total) {
  return `<div class="catalog-pager"><span>${number(total)} registos · página ${page} de ${pages}</span><div><button type="button" class="btn icon" data-icon="back" data-catalog-kind="${kind}" data-catalog-page="${page - 1}" aria-label="Página anterior" title="Página anterior" ${page <= 1 ? 'disabled' : ''}></button><button type="button" class="btn icon" data-icon="forward" data-catalog-kind="${kind}" data-catalog-page="${page + 1}" aria-label="Página seguinte" title="Página seguinte" ${page >= pages ? 'disabled' : ''}></button></div></div>`;
}

export function materialCatalogTable(rows, selectedIds, kind, page) {
  const result = pageRows(rows, page);
  const body = result.rows.length ? result.rows.map(row => {
    const selected = selectedIds.includes(row.id);
    return `<tr class="${selected ? 'catalog-selected' : ''}">
      <td><button type="button" class="catalog-select ${selected ? 'selected' : ''}" data-add-${kind}="${row.id}" aria-label="Adicionar ${esc(row.name)}">${selected ? '✓' : '+'}</button></td>
      <td><div class="catalog-name"><span>${row.image_url ? `<img src="${esc(row.image_url)}" alt="">` : esc(row.name.charAt(0))}</span><div><b>${esc(row.name)}</b><small>${esc(row.code)}</small></div></div></td>
      <td>${esc(row.composition || row.category || '—')}${row.gsm ? `<small class="table-subline">${number(row.gsm)} g/m²</small>` : ''}</td>
      <td>${esc(row.supplier_name || 'Sem fornecedor')}</td>
      <td><b>${money(row.unit_cost)} / ${esc(row.unit)}</b></td>
      <td><span class="${row.available_stock > 0 ? 'stock-ok' : 'stock-zero'}">${number(row.available_stock)} ${esc(row.unit)}</span></td>
    </tr>`;
  }).join('') : '<tr><td colspan="6"><div class="empty"><strong>Sem resultados</strong>Altere a pesquisa ou crie um novo registo.</div></td></tr>';
  return `<div class="catalog-table"><div class="table-wrap"><table class="data-table"><thead><tr><th></th><th>Malha / componente</th><th>Composição</th><th>Fornecedor</th><th>Preço real</th><th>Stock livre</th></tr></thead><tbody>${body}</tbody></table></div>${pager(kind, result.current, result.pages, rows.length)}</div>`;
}

export function operationCatalogTable(rows, selectedIds, page) {
  const result = pageRows(rows, page);
  const body = result.rows.length ? result.rows.map(row => {
    const selected = selectedIds.includes(row.id);
    return `<tr class="${selected ? 'catalog-selected' : ''}"><td><button type="button" class="catalog-select ${selected ? 'selected' : ''}" data-operation="${row.id}">${selected ? '✓' : '+'}</button></td><td><b>${esc(row.code)}</b></td><td>${esc(row.name)}</td><td>${esc(row.department || 'Produção')}</td><td>${number(row.standard_time_min)} min</td><td>${money(row.cost_per_minute)}/min</td></tr>`;
  }).join('') : '<tr><td colspan="6"><div class="empty"><strong>Sem operações</strong>Altere a pesquisa.</div></td></tr>';
  return `<div class="catalog-table"><div class="table-wrap"><table class="data-table"><thead><tr><th></th><th>Código</th><th>Operação</th><th>Secção</th><th>Tempo padrão</th><th>Custo/min.</th></tr></thead><tbody>${body}</tbody></table></div>${pager('operation', result.current, result.pages, rows.length)}</div>`;
}

export function subcontractCatalogTable(rows, selectedIds, page) {
  const result = pageRows(rows, page);
  const body = result.rows.length ? result.rows.map(row => {
    const selected = selectedIds.includes(row.id);
    return `<tr class="${selected ? 'catalog-selected' : ''}"><td><button type="button" class="catalog-select ${selected ? 'selected' : ''}" data-subcontract="${row.id}">${selected ? '✓' : '+'}</button></td><td><b>${esc(row.code)}</b></td><td>${esc(row.name)}</td><td>${esc(row.supplier_name)}</td><td>${esc(row.category)}</td><td><b>${money(row.unit_cost)} / ${esc(row.unit)}</b></td><td>${number(row.lead_time_days)} dias</td><td>${number(row.quality_score)}%</td></tr>`;
  }).join('') : '<tr><td colspan="8"><div class="empty"><strong>Sem serviços</strong>Crie o primeiro serviço subcontratado.</div></td></tr>';
  return `<div class="catalog-table"><div class="table-wrap"><table class="data-table"><thead><tr><th></th><th>Código</th><th>Serviço</th><th>Fornecedor</th><th>Tipo</th><th>Preço acordado</th><th>Prazo</th><th>Qualidade</th></tr></thead><tbody>${body}</tbody></table></div>${pager('subcontract', result.current, result.pages, rows.length)}</div>`;
}
