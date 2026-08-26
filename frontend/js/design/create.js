import { crudList } from '../api.js?v=20260826-3';
import { designApi } from './api.js?v=20260826-3';
import { initials as nameInitials, SOURCES } from './constants.js';
import { esc } from '../format.js?v=20260826-3';
import { state } from '../state.js';
import { closeModal, openModal, toast } from '../ui.js?v=20260826-3';

function emptyModel() {
  return {title: '', user_ids: [], quantity: '', cover_url: '', code: ''};
}

function initialsFor(team, ids) {
  const chosen = ids.map(id => team.find(user => user.id === id)).filter(Boolean);
  if (!chosen.length) return '';
  if (chosen.length === 1) return chosen[0].initials || nameInitials(chosen[0].name);
  return chosen.map(user => (user.name || ' ').trim()[0].toUpperCase()).join('');
}

export async function openCreateRequest(onCreated) {
  const [customers, team] = await Promise.all([
    crudList('customers', state.companyId, 'limit=2000'),
    designApi.team(),
  ]);
  const designers = team.filter(user => ['designer', 'admin', 'manager', 'planner'].includes(user.role));
  const models = [emptyModel()];
  const order = {customer_id: '', request_source: 'whatsapp', request_group: '', request_notes: '', due_date: ''};

  function draw() {
    const body = document.getElementById('modal-body');
    if (!body) return;
    body.querySelector('[data-models]').innerHTML = models.map((model, index) => `
      <article class="design-model-row">
        <b>${index + 1}</b>
        <div>
          <input data-model-title="${index}" required placeholder="Peça / descrição *" value="${esc(model.title)}">
          <div class="design-designer-row">
            <small>Designer / parceria</small>
            ${designers.map(user => `<button type="button" class="design-chip ${model.user_ids.includes(user.id) ? 'on' : ''}" data-toggle-designer="${index}" data-user="${user.id}">${esc(user.name)}${user.initials ? ` (${esc(user.initials)})` : ''}</button>`).join('') || '<span class="muted">Sem contas de designer nesta empresa.</span>'}
          </div>
          <div class="design-model-line">
            <input type="number" min="1" data-model-qty="${index}" placeholder="Quantidade" value="${esc(model.quantity)}">
            <input data-model-code="${index}" placeholder="Referência" value="${esc(model.code)}">
            <input data-model-cover="${index}" placeholder="URL da fotografia" value="${esc(model.cover_url)}">
          </div>
        </div>
        ${models.length > 1 ? `<button type="button" class="btn icon danger" data-icon="delete" data-remove-model="${index}" aria-label="Remover modelo" title="Remover modelo"></button>` : ''}
      </article>`).join('');
  }

  openModal('Novo pedido do cliente', `
    <form class="design-create" data-create-request>
      <p class="muted">Registe o briefing. Um pedido pode ter vários modelos — cada um fica com a sua designer, parceria e referência.</p>
      <div class="form-grid">
        <label class="field">Cliente *
          <select name="customer_id" required>
            <option value="">Selecionar…</option>
            ${customers.filter(row => row.active !== false).map(row => `<option value="${row.id}">${esc(row.name)}${row.code ? ` (${esc(row.code)})` : ''}</option>`).join('')}
          </select>
        </label>
        <label class="field">Origem
          <select name="request_source">${SOURCES.map(([id, label]) => `<option value="${id}">${label}</option>`).join('')}</select>
        </label>
        <label class="field">Pedido / campanha<input name="request_group" placeholder="Ex.: Brownie julho"></label>
        <label class="field">Data pretendida<input type="date" name="due_date"></label>
        <label class="field full">Briefing recebido<textarea name="request_notes" rows="2" placeholder="O que o cliente pediu, tipo de peça, cores, referências…"></textarea></label>
      </div>
      <div class="design-models-head">
        <strong>Modelos pedidos</strong>
        <button type="button" class="btn small" data-generate>Gerar referências</button>
      </div>
      <div data-models></div>
      <button type="button" class="btn" data-add-model>+ Adicionar modelo</button>
      <div class="design-create-actions"><button class="btn primary" type="submit">Criar pedido</button></div>
    </form>`, 'Pedido → referências → ficha técnica → amostra');
  draw();

  const body = document.getElementById('modal-body');
  body.addEventListener('input', event => {
    const title = event.target.closest('[data-model-title]');
    const qty = event.target.closest('[data-model-qty]');
    const code = event.target.closest('[data-model-code]');
    const cover = event.target.closest('[data-model-cover]');
    if (title) models[Number(title.dataset.modelTitle)].title = title.value;
    if (qty) models[Number(qty.dataset.modelQty)].quantity = qty.value;
    if (code) models[Number(code.dataset.modelCode)].code = code.value.toUpperCase();
    if (cover) models[Number(cover.dataset.modelCover)].cover_url = cover.value;
  });
  body.addEventListener('click', async event => {
    const add = event.target.closest('[data-add-model]');
    const remove = event.target.closest('[data-remove-model]');
    const toggle = event.target.closest('[data-toggle-designer]');
    const generate = event.target.closest('[data-generate]');
    if (add) { models.push(emptyModel()); draw(); }
    if (remove) { models.splice(Number(remove.dataset.removeModel), 1); draw(); }
    if (toggle) {
      const index = Number(toggle.dataset.toggleDesigner);
      const userId = Number(toggle.dataset.user);
      const ids = models[index].user_ids;
      models[index].user_ids = ids.includes(userId) ? ids.filter(id => id !== userId) : [...ids, userId];
      draw();
    }
    if (generate) {
      const customerId = body.querySelector('[name="customer_id"]').value;
      if (!customerId) { toast('Escolha primeiro o cliente.', 'error'); return; }
      try {
        const first = await designApi.nextReference(customerId, models[0].user_ids[0]);
        const customer = customers.find(row => Number(row.id) === Number(customerId));
        let seq = first.sequence;
        models.forEach(model => {
          const ini = initialsFor(team, model.user_ids);
          model.code = `${ini ? `${ini}_` : ''}${customer.code}_${String(seq).padStart(3, '0')}`;
          seq += 1;
        });
        draw();
        toast('Referências geradas. Pode ajustar antes de guardar.');
      } catch (error) { toast(error.message, 'error'); }
    }
  });
  body.querySelector('[data-create-request]').addEventListener('submit', async event => {
    event.preventDefault();
    const form = event.currentTarget;
    const payload = {
      customer_id: Number(form.customer_id.value),
      request_source: form.request_source.value,
      request_group: form.request_group.value || null,
      due_date: form.due_date.value || null,
      request_notes: form.request_notes.value || null,
      models: models.filter(model => model.title.trim() && model.code.trim()).map(model => ({
        title: model.title.trim(),
        code: model.code.trim().toUpperCase(),
        user_ids: model.user_ids,
        quantity: model.quantity ? Number(model.quantity) : null,
        cover_url: model.cover_url || null,
      })),
    };
    if (!payload.models.length) { toast('Cada modelo precisa de peça e referência.', 'error'); return; }
    try {
      const created = await designApi.create(payload);
      toast(created.length === 1 ? 'Pedido criado.' : `Pedido criado com ${created.length} modelos.`);
      closeModal();
      onCreated?.(created);
    } catch (error) { toast(error.message, 'error'); }
  });
}
