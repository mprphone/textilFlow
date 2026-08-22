import { esc } from './format.js?v=20260819-5';

const modal = document.getElementById('modal');
const modalTitle = document.getElementById('modal-title');
const modalSubtitle = document.getElementById('modal-subtitle');
const modalBody = document.getElementById('modal-body');

export function setHeading(title, subtitle = '') {
  document.getElementById('page-title').textContent = title;
  document.getElementById('page-subtitle').textContent = subtitle;
}

export function pageHeader(title, subtitle, actions = '', extraClass = '') {
  setHeading(title, subtitle);
  return `<div class="page-head${extraClass ? ` ${extraClass}` : ''}"><div><h1>${esc(title)}</h1><p>${esc(subtitle)}</p></div><div class="actions">${actions}</div></div>`;
}

export function openModal(title, body, subtitle = '') {
  modalTitle.textContent = title;
  modalSubtitle.textContent = subtitle;
  modalBody.innerHTML = body;
  modal.setAttribute('aria-hidden', 'false');
  modal.classList.remove('hidden');
  document.body.classList.add('modal-open');
}

export function closeModal() {
  modal.classList.add('hidden');
  modal.setAttribute('aria-hidden', 'true');
  document.body.classList.remove('modal-open');
  modalTitle.textContent = '';
  modalSubtitle.textContent = '';
  modalBody.innerHTML = '';
  const statusSlot = document.getElementById('modal-status-slot');
  if (statusSlot) statusSlot.innerHTML = '';
}

export function toast(message, type = 'success') {
  const item = document.createElement('div');
  item.className = `toast ${type}`; item.textContent = message;
  document.getElementById('toast-stack').appendChild(item);
  setTimeout(() => item.remove(), String(message).length > 90 ? 9000 : 3500);
}

export function loading(message = 'A carregar dados…') { return `<div class="loading">${esc(message)}</div>`; }
export function empty(title = 'Sem registos', detail = 'Crie o primeiro registo para começar.') { return `<div class="empty"><strong>${esc(title)}</strong>${esc(detail)}</div>`; }
export function confirmDelete(label = 'este registo') { return window.confirm(`Eliminar ${label}? Esta ação não pode ser anulada.`); }

document.getElementById('modal-close').addEventListener('click', closeModal);
document.querySelector('.modal-card')?.addEventListener('click', event => event.stopPropagation());
const emergencyClose = document.getElementById('modal-emergency-close');
if (emergencyClose) {
  emergencyClose.hidden = true;
  emergencyClose.setAttribute('aria-hidden', 'true');
}
document.addEventListener('keydown', event => {
  if (event.key === 'Escape' && !modal.classList.contains('hidden')) closeModal();
});

// Evita que o navegador restaure uma camada modal antiga e bloqueie a aplicação.
closeModal();
