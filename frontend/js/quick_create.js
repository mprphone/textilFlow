import { crudCreate, crudUpdate } from './api.js';
import { bindPasswordToggles, bindPhotoFields, readForm, renderForm } from './forms.js?v=20260822-2';
import { state } from './state.js';
import { closeModal, openModal, toast } from './ui.js?v=20260821-19';

export function recordModal({ title, fields, values = {}, resource, recordId = null, transform = null, save = null, onSaved = null, subtitle = '', formClass = 'form-grid', stayOpen = false }) {
  openModal(title, renderForm(fields, values, { formClass }), subtitle);
  bindPasswordToggles(document.getElementById('modal-body'));
  bindPhotoFields(document.getElementById('modal-body'));
  document.querySelector('[data-close-modal]').addEventListener('click', closeModal);
  document.getElementById('record-form').addEventListener('submit', async event => {
    event.preventDefault();
    try {
      let payload = readForm(event.currentTarget, fields);
      if (transform) payload = await transform(payload);
      payload.company_id = state.companyId;
      const saved = save ? await save(payload) : recordId ? await crudUpdate(resource, recordId, payload) : await crudCreate(resource, payload);
      toast('Registo guardado.');
      if (!stayOpen) closeModal();
      if (onSaved) await onSaved(saved);
    } catch (error) { toast(error.message, 'error'); }
  });
}
