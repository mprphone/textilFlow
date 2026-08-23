import { crudCreate, crudDelete, crudList, crudUpdate } from './api.js';
import { esc, humanize } from './format.js?v=20260819-5';
import { bindPasswordToggles, bindPhotoFields, readForm, renderForm } from './forms.js?v=20260822-2';
import { state } from './state.js';
import { closeModal, confirmDelete, empty, openModal, pageHeader, toast } from './ui.js?v=20260820-5';

export async function renderEntityPage(container, config) {
  const defaultFields = typeof config.fields === 'function' ? await config.fields(null) : config.fields;
  const fieldMap = Object.fromEntries((defaultFields || []).map(field => [field.key, field]));
  const listQuery = [config.query || '', 'limit=2000'].filter(Boolean).join('&');
  let rows = await crudList(config.resource, state.companyId, listQuery);
  let currentPage = 1;
  let pageSize = 50;
  let filtered = rows;
  const actionButton = config.readOnly ? '' : `<button class="btn primary" data-new>+ ${esc(config.newLabel || 'Novo registo')}</button>`;
  container.innerHTML = pageHeader(config.title, config.subtitle, `${config.extraActions || ''}${actionButton}`) + `
    <section class="listing-panel">
      <div class="listing-bar">
        <label class="listing-size">Mostrar <select data-page-size><option>25</option><option selected>50</option><option>100</option></select> registos</label>
        <div class="table-search"><span>⌕</span><input class="filter-input" data-filter placeholder="Procurar…"></div>
      </div>
      <div class="table-wrap listing-table"><table class="data-table" aria-label="${esc(config.title || 'Registos')}"><thead><tr>${config.columns.map(column => `<th scope="col">${esc(column.label)}</th>`).join('')}<th scope="col"><span class="sr-only">Ações</span></th></tr></thead><tbody data-body></tbody></table></div>
      <div class="list-pager" data-list-pager role="status" aria-live="polite"></div>
    </section>`;
  const body = container.querySelector('[data-body]');
  const pager = container.querySelector('[data-list-pager]');

  const cell = (row, column) => {
    if (column.render) return column.render(row);
    const field = fieldMap[column.key];
    if (field?.type === 'select' && field.options) {
      const option = field.options.find(item => String(typeof item === 'object' ? item.value : item) === String(row[column.key] ?? ''));
      if (option !== undefined) return esc(typeof option === 'object' ? option.label : humanize(option));
    }
    if (typeof row[column.key] === 'boolean') return row[column.key] ? '<span class="badge green">Sim</span>' : '<span class="badge">Não</span>';
    return esc(row[column.key] ?? '—');
  };
  const rangeLabel = (data) => {
    if (!data.length) return 'Mostrar 0 registos';
    const start = (currentPage - 1) * pageSize + 1;
    const end = Math.min(currentPage * pageSize, data.length);
    return `Mostrar ${start} a ${end} de ${data.length} registos`;
  };
  const rowHtml = row => `<tr>${config.columns.map(column => `<td>${cell(row, column)}</td>`).join('')}<td class="listing-actions"><div class="row-actions">${config.rowActions ? config.rowActions(row) : ''}${config.readOnly?'':`<button class="btn icon" data-edit="${row.id}" aria-label="Editar">✎</button><button class="btn icon danger" data-delete="${row.id}" aria-label="Eliminar">×</button>`}</div></td></tr>`;
  const draw = data => {
    const pages = Math.max(1, Math.ceil(data.length / pageSize));
    currentPage = Math.min(currentPage, pages);
    const visible = data.slice((currentPage - 1) * pageSize, currentPage * pageSize);
    body.innerHTML = visible.length ? visible.map(rowHtml).join('') : `<tr><td colspan="${config.columns.length + 1}">${empty('Sem resultados', 'Altere a pesquisa ou crie o primeiro registo.')}</td></tr>`;
    pager.innerHTML = `<span>${rangeLabel(data)}</span><div><button class="btn small" data-list-page="${currentPage-1}" ${currentPage<=1?'disabled':''}>← Anterior</button><button class="btn small" data-list-page="${currentPage+1}" ${currentPage>=pages?'disabled':''}>Seguinte →</button></div>`;
    pager.querySelectorAll('[data-list-page]').forEach(button=>button.addEventListener('click',()=>{currentPage=Number(button.dataset.listPage);draw(data);}));
  };
  draw(filtered);
  container.querySelector('[data-page-size]').addEventListener('change', event => {
    pageSize = Number(event.target.value);
    currentPage = 1;
    draw(filtered);
  });

  const openEditor = async row => {
    const fields = typeof config.fields === 'function' ? await config.fields(row) : defaultFields;
    const formSubtitle = (typeof config.formSubtitle === 'function' ? config.formSubtitle(row) : config.formSubtitle) || 'Os campos marcados com * são obrigatórios.';
    openModal(row ? `Editar ${config.singular}` : config.newLabel || `Novo ${config.singular}`, renderForm(fields, row || {}), formSubtitle);
    bindPasswordToggles(document.getElementById('modal-body'));
    bindPhotoFields(document.getElementById('modal-body'));
    document.querySelector('[data-close-modal]').addEventListener('click', closeModal);
    document.getElementById('record-form').addEventListener('submit', async event => {
      event.preventDefault();
      try {
        let payload = readForm(event.currentTarget, fields);
        if (config.transform) payload = await config.transform(payload, row);
        payload.company_id = state.companyId;
        if (row) await crudUpdate(config.resource, row.id, payload); else await crudCreate(config.resource, payload);
        closeModal(); toast('Registo guardado.');
        await renderEntityPage(container, config);
      } catch (error) { toast(error.message, 'error'); }
    });
  };

  container.querySelector('[data-new]')?.addEventListener('click', () => openEditor(null));
  container.querySelector('[data-filter]').addEventListener('input', event => {
    const value = event.target.value.toLowerCase();
    currentPage = 1;
    filtered = rows.filter(row => Object.values(row).some(item => String(item ?? '').toLowerCase().includes(value)));
    draw(filtered);
  });
  body.addEventListener('click', async event => {
    const edit = event.target.closest('[data-edit]');
    const removeButton = event.target.closest('[data-delete]');
    if (edit) openEditor(rows.find(row => row.id === Number(edit.dataset.edit)));
    if (removeButton && confirmDelete(config.singular)) {
      try { await crudDelete(config.resource, Number(removeButton.dataset.delete), state.companyId); toast('Registo eliminado.'); await renderEntityPage(container, config); }
      catch (error) { toast(error.message, 'error'); }
    }
    if (config.onAction) config.onAction(event, rows);
  });
}

export async function renderEntityTabs(container, tabs, initial = 0) {
  container.innerHTML = `<div class="tabs">${tabs.map((tab, index) => `<button class="tab ${index === initial ? 'active' : ''}" data-tab="${index}">${esc(tab.label)}</button>`).join('')}</div><div data-tab-panel></div>`;
  const panel = container.querySelector('[data-tab-panel]');
  const openTab = index => tabs[index].render ? tabs[index].render(panel) : renderEntityPage(panel, tabs[index].config);
  await openTab(initial);
  container.querySelector('.tabs').addEventListener('click', async event => {
    const button = event.target.closest('[data-tab]');
    if (!button) return;
    container.querySelectorAll('[data-tab]').forEach(item => item.classList.toggle('active', item === button));
    await openTab(Number(button.dataset.tab));
  });
}
