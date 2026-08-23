import { esc, humanize } from './format.js?v=20260819-5';
import { toast } from './ui.js?v=20260821-19';

const MAX_PHOTOS = 6;
const MAX_PHOTO_BYTES = 1.5 * 1024 * 1024;

function optionMarkup(option, selected) {
  const value = typeof option === 'object' ? option.value : option;
  const label = typeof option === 'object' ? option.label : humanize(option);
  return `<option value="${esc(value)}" ${String(value) === String(selected ?? '') ? 'selected' : ''}>${esc(label)}</option>`;
}

const EYE_OPEN = '<svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true"><path fill="currentColor" d="M12 5c-5.2 0-9.4 4.1-10.5 7 1.1 2.9 5.3 7 10.5 7s9.4-4.1 10.5-7C21.4 9.1 17.2 5 12 5zm0 11.5A4.5 4.5 0 1 1 12 7a4.5 4.5 0 0 1 0 9.5zm0-2.2A2.3 2.3 0 1 0 12 9.7a2.3 2.3 0 0 0 0 4.6z"/></svg>';
const EYE_OFF = '<svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true"><path fill="currentColor" d="M3.3 2.3 2 3.6l3.1 3.1C3.3 8.3 1.8 10.2 1.5 12c1.1 2.9 5.3 7 10.5 7 2 0 3.8-.6 5.4-1.5l3.6 3.6 1.3-1.3L3.3 2.3zM12 17c-4.1 0-7.5-3.1-8.5-5 .5-.9 1.6-2.3 3.1-3.4l2.1 2.1A4.5 4.5 0 0 0 12 16.5V17zm8.5-5c-.3.6-.8 1.3-1.4 2l-1.5-1.5c.4-.5.7-1 .9-1.5-.9-1.7-3.6-4.2-7.5-4.5l-1.8-1.8C9.8 5.1 10.9 5 12 5c5.2 0 9.4 4.1 10.5 7-.3.6-.7 1.3-1.2 2z"/></svg>';

export function bindPasswordToggles(root = document) {
  root.querySelectorAll('.pw-toggle').forEach(button => {
    if (button.dataset.bound) return;
    button.dataset.bound = '1';
    button.addEventListener('click', () => {
      const wrap = button.closest('.pw-wrap');
      const input = wrap && wrap.querySelector('input');
      if (!input) return;
      const show = input.type === 'password';
      input.type = show ? 'text' : 'password';
      button.classList.toggle('is-on', show);
      button.setAttribute('aria-label', show ? 'Ocultar senha' : 'Mostrar senha');
      button.innerHTML = show ? EYE_OFF : EYE_OPEN;
    });
  });
}

export function bindPhotoFields(root = document) {
  root.querySelectorAll('[data-photo-widget]').forEach(widget => {
    if (widget.dataset.bound) return;
    widget.dataset.bound = '1';
    const hidden = widget.querySelector('[data-photo-value]');
    const thumbs = widget.querySelector('[data-photo-thumbs]');
    const input = widget.querySelector('[data-photo-input]');
    const getPhotos = () => { try { return JSON.parse(hidden.value || '[]'); } catch { return []; } };
    const renderThumbs = () => {
      const photos = getPhotos();
      thumbs.innerHTML = photos.map((src, index) => `<span class="photo-thumb"><img src="${esc(src)}" alt="Fotografia ${index + 1}"><button type="button" data-remove-photo="${index}" aria-label="Remover fotografia ${index + 1}">×</button></span>`).join('');
      thumbs.querySelectorAll('[data-remove-photo]').forEach(button => button.addEventListener('click', () => {
        const photos = getPhotos();
        photos.splice(Number(button.dataset.removePhoto), 1);
        hidden.value = JSON.stringify(photos);
        renderThumbs();
      }));
    };
    input.addEventListener('change', async () => {
      const photos = getPhotos();
      for (const file of Array.from(input.files || [])) {
        if (photos.length >= MAX_PHOTOS) { toast(`Máximo de ${MAX_PHOTOS} fotografias.`, 'error'); break; }
        if (file.size > MAX_PHOTO_BYTES) { toast(`"${file.name}" é maior que ${(MAX_PHOTO_BYTES / 1024 / 1024).toFixed(1)} MB.`, 'error'); continue; }
        try {
          const dataUrl = await new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(reader.result);
            reader.onerror = () => reject(new Error('Falha a ler o ficheiro'));
            reader.readAsDataURL(file);
          });
          photos.push(dataUrl);
        } catch { toast(`Não foi possível ler "${file.name}".`, 'error'); }
      }
      input.value = '';
      hidden.value = JSON.stringify(photos);
      renderThumbs();
    });
    renderThumbs();
  });
}

export function fieldsMarkup(fields, values = {}) {
  let section = null;
  return fields.map(field => {
    const value = values[field.key] ?? field.default ?? '';
    const sectionHeader = field.section && field.section !== section ? `<div class="form-section">${esc(field.section)}</div>` : '';
    if (field.section) section = field.section;
    if (field.type === 'hidden') return `<input type="hidden" name="${field.key}" value="${esc(value)}">`;
    const required = field.required ? 'required' : '';
    const spanClass = field.span === 2 ? 'span-2' : field.span === 3 ? 'span-3' : (['json','photo'].includes(field.type) || field.full ? 'full' : '');
    const title = field.title ? `title="${esc(field.title)}"` : '';
    let input;
    if (field.type === 'photo') {
      const photos = Array.isArray(value) ? value : [];
      input = `<div class="photo-field" data-photo-widget="${field.key}">
        <input type="hidden" name="${field.key}" data-photo-value value="${esc(JSON.stringify(photos))}">
        <div class="photo-thumbs" data-photo-thumbs></div>
        <label class="btn small">+ Adicionar fotografia<input type="file" accept="image/*" multiple data-photo-input style="display:none"></label>
      </div>`;
    } else if (field.type === 'select') {
      input = `<select name="${field.key}" ${required} ${title}><option value="">Selecionar…</option>${(field.options || []).map(option => optionMarkup(option, value)).join('')}</select>`;
    } else if (field.type === 'textarea' || field.type === 'json') {
      const shown = field.type === 'json' && typeof value === 'object' ? JSON.stringify(value, null, 2) : value;
      input = field.type === 'json'
        ? `<details class="advanced-data"><summary>Dados avançados — abrir apenas se necessário</summary><textarea name="${field.key}" ${required}>${esc(shown)}</textarea><small>Esta área é normalmente gerida pelo sistema.</small></details>`
        : `<textarea name="${field.key}" rows="${field.rows || 2}" ${required} placeholder="${esc(field.placeholder || '')}">${esc(shown)}</textarea>`;
    } else if (field.type === 'checkbox') {
      input = `<input name="${field.key}" type="checkbox" ${value ? 'checked' : ''}><span>${esc(field.help || 'Ativo')}</span>`;
    } else if (field.type === 'password') {
      input = `<span class="pw-wrap"><input name="${field.key}" type="password" value="${esc(value)}" ${required} ${title} placeholder="${esc(field.placeholder || '')}" autocomplete="new-password"><button type="button" class="pw-toggle" aria-label="Mostrar senha" title="Mostrar ou ocultar">${EYE_OPEN}</button></span>`;
    } else if (field.type === 'money') {
      const currencyKey = field.currencyKey || `${field.key}_currency`;
      const currency = values[currencyKey] ?? field.currencyDefault ?? 'EUR';
      const currencies = field.currencies || ['EUR', 'USD', 'GBP'];
      input = `<span class="money-pair"><input name="${field.key}" type="number" step="${field.step || 'any'}" value="${esc(value)}" ${required} placeholder="${esc(field.placeholder || '0.00')}"><select name="${currencyKey}" aria-label="Moeda">${currencies.map(code => optionMarkup(code, currency)).join('')}</select></span>`;
    } else {
      const type = ['number','date','datetime-local','email','url'].includes(field.type) ? field.type : 'text';
      const step = type === 'number' ? `step="${field.step || 'any'}"` : '';
      const locked = field.readonly ? 'readonly' : '';
      input = `<input name="${field.key}" type="${type}" value="${esc(value)}" ${step} ${required} ${locked} ${title} placeholder="${esc(field.placeholder || '')}" ${field.autocomplete === false ? 'autocomplete="off"' : ''}>`;
    }
    return `${sectionHeader}<div class="field ${spanClass}"><label>${esc(field.label)}${field.required ? ' *' : ''}${input}</label>${field.help && field.type !== 'checkbox' ? `<small class="muted">${esc(field.help)}</small>` : ''}</div>`;
  }).join('');
}

export function fieldsCard(title, fields, values = {}, hint = '') {
  if (!fields.length) return '';
  return `<div class="card"><div class="card-header"><h2>${esc(title)}</h2>${hint ? `<span>${esc(hint)}</span>` : ''}</div><div class="form-grid">${fieldsMarkup(fields, values)}</div></div>`;
}

export function renderForm(fields, values = {}, { submitLabel = 'Guardar', formId = 'record-form', formClass = 'form-grid' } = {}) {
  const content = fieldsMarkup(fields, values);
  return `<form id="${formId}" class="${esc(formClass)}">${content}<div class="form-footer"><button type="button" class="btn" data-close-modal>Cancelar</button><button type="submit" class="btn primary">${esc(submitLabel)}</button></div></form>`;
}

export function readForm(form, fields) {
  const data = {};
  for (const field of fields) {
    if (field.type === 'money') {
      const amountEl = form.elements.namedItem(field.key);
      const currencyKey = field.currencyKey || `${field.key}_currency`;
      const currencyEl = form.elements.namedItem(currencyKey);
      const raw = amountEl ? amountEl.value : '';
      data[field.key] = raw === '' ? null : Number(raw);
      data[currencyKey] = currencyEl ? currencyEl.value : (field.currencyDefault || 'EUR');
      continue;
    }
    const element = form.elements.namedItem(field.key);
    if (!element) continue;
    let value = field.type === 'checkbox' ? element.checked : element.value;
    if (field.type === 'number' || (field.type === 'hidden' && /^-?\d+(\.\d+)?$/.test(value))) value = value === '' ? null : Number(value);
    if (field.type === 'json') {
      try { value = value.trim() ? JSON.parse(value) : {}; }
      catch { throw new Error(`O campo “${field.label}” não contém JSON válido.`); }
    }
    if (field.type === 'photo') {
      try { value = value.trim() ? JSON.parse(value) : []; }
      catch { value = []; }
    }
    if (value === '' && !field.required) value = null;
    data[field.key] = value;
  }
  return data;
}

export function dynamicFields(definitions, customData = {}) {
  return definitions.map(definition => ({
    key: `custom__${definition.field_key}`, label: definition.label,
    type: definition.data_type === 'boolean' ? 'checkbox' : definition.data_type,
    required: definition.required, options: definition.options || [], section: definition.section,
    default: customData[definition.field_key] ?? definition.default_value,
  }));
}

export function mergeCustomData(payload, existing = {}) {
  const custom = { ...(existing || {}) };
  for (const key of Object.keys(payload)) {
    if (key.startsWith('custom__')) { custom[key.slice(8)] = payload[key]; delete payload[key]; }
  }
  if (Object.keys(custom).length) payload.custom_data = custom;
  return payload;
}
