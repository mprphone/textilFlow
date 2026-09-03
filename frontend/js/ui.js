import { esc } from './format.js?v=20260826-3';

const modal = document.getElementById('modal');
const modalTitle = document.getElementById('modal-title');
const modalSubtitle = document.getElementById('modal-subtitle');
const modalBody = document.getElementById('modal-body');
let previousFocus = null;
let modalLocked = false;

function syncModalVisibility() {
  const isOpen = modal.getAttribute('aria-hidden') === 'false' && !modal.classList.contains('hidden');
  modal.hidden = !isOpen;
  if (isOpen) {
    modal.style.removeProperty('display');
    modal.removeAttribute('inert');
    modal.dataset.locked = String(modalLocked);
  }
  else {
    modal.style.setProperty('display', 'none');
    modal.setAttribute('inert', '');
    delete modal.dataset.locked;
    document.body.classList.remove('modal-open');
  }
}

new MutationObserver(syncModalVisibility).observe(modal, {
  attributes: true,
  attributeFilter: ['class', 'aria-hidden'],
});

export function setHeading(title, subtitle = '') {
  document.getElementById('page-title').textContent = title;
  document.getElementById('page-subtitle').textContent = subtitle;
}

export function pageHeader(title, subtitle, actions = '', extraClass = '') {
  setHeading(title, subtitle);
  return `<div class="page-head${extraClass ? ` ${extraClass}` : ''}"><div><h1>${esc(title)}</h1><p>${esc(subtitle)}</p></div><div class="actions">${actions}</div></div>`;
}

export function openModal(title, body, subtitle = '', options = {}) {
  previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  modalLocked = Boolean(options.lock);
  const card = modal.querySelector('.modal-card');
  card?.classList.remove('supplier-ficha-card', 'company-fiche-card');
  if (options.cardClass) card?.classList.add(options.cardClass);
  const closeBtn = document.getElementById('modal-close');
  if (closeBtn) closeBtn.hidden = modalLocked;
  const statusSlot = document.getElementById('modal-status-slot');
  if (statusSlot) statusSlot.innerHTML = '';
  modalTitle.textContent = title;
  modalSubtitle.textContent = subtitle;
  modalBody.innerHTML = body;
  modal.hidden = false;
  modal.style.removeProperty('display');
  modal.setAttribute('aria-hidden', 'false');
  modal.classList.remove('hidden');
  syncModalVisibility();
  document.body.classList.add('modal-open');
  requestAnimationFrame(() => {
    const card = modal.querySelector('.modal-card');
    const rect = card?.getBoundingClientRect();
    if (card && rect && (rect.width < 1 || rect.height < 1)) {
      card.style.setProperty('display', 'flex', 'important');
      card.style.setProperty('visibility', 'visible', 'important');
      card.style.setProperty('opacity', '1', 'important');
    } else if (!card || !rect) {
      modalLocked = false;
      closeModal(true);
      document.dispatchEvent(new CustomEvent('tf:modal-render-error'));
      return;
    }
    modal.querySelector('input:not(:disabled),select:not(:disabled),textarea:not(:disabled),button:not(:disabled),a[href]')?.focus();
  });
}

export function closeModal(force = false) {
  if (modalLocked && force !== true) return;
  modalLocked = false;
  const closeBtn = document.getElementById('modal-close');
  if (closeBtn) closeBtn.hidden = false;
  modal.classList.add('hidden');
  modal.setAttribute('aria-hidden', 'true');
  modal.hidden = true;
  modal.setAttribute('inert', '');
  modal.style.setProperty('display', 'none');
  document.body.classList.remove('modal-open');
  modal.querySelector('.modal-card')?.classList.remove('supplier-ficha-card', 'company-fiche-card');
  modalTitle.textContent = '';
  modalSubtitle.textContent = '';
  modalBody.innerHTML = '';
  if (previousFocus?.isConnected) previousFocus.focus();
  previousFocus = null;
  const statusSlot = document.getElementById('modal-status-slot');
  if (statusSlot) statusSlot.innerHTML = '';
}

export function resetTransientUi() {
  if (!modalLocked) closeModal(true);
  document.querySelectorAll('.design-overlay').forEach(layer => layer.remove());
  document.querySelectorAll('.pri-lookup-layer').forEach(layer => {
    layer.classList.add('hidden');
    layer.setAttribute('aria-hidden', 'true');
  });
}

export function toast(message, type = 'success') {
  const item = document.createElement('div');
  item.className = `toast ${type}`;
  item.setAttribute('role', type === 'error' ? 'alert' : 'status');
  const symbol = document.createElement('span'); symbol.dataset.icon = type === 'error' ? 'warning' : 'check'; symbol.setAttribute('aria-hidden', 'true');
  const copy = document.createElement('span'); copy.textContent = message;
  item.append(symbol, copy);
  document.getElementById('toast-stack').appendChild(item);
  setTimeout(() => item.remove(), String(message).length > 90 ? 9000 : 3500);
}

export function loading(message = 'A carregar dados…') { return `<div class="loading" role="status" aria-live="polite"><span>${esc(message)}</span></div>`; }
export function empty(title = 'Sem registos', detail = 'Crie o primeiro registo para começar.') { return `<div class="empty" role="status"><strong>${esc(title)}</strong><span>${esc(detail)}</span></div>`; }
export function confirmDelete(label = 'este registo') { return window.confirm(`Eliminar ${label}? Esta ação não pode ser anulada.`); }

document.getElementById('modal-close')?.addEventListener('click', closeModal);
document.querySelector('.modal-card')?.addEventListener('click', event => event.stopPropagation());
modal?.addEventListener('click', event => {
  if (event.target === modal && !modalLocked) closeModal();
});
const emergencyClose = document.getElementById('modal-emergency-close');
if (emergencyClose) {
  emergencyClose.hidden = true;
  emergencyClose.setAttribute('aria-hidden', 'true');
}
document.addEventListener('keydown', event => {
  if (event.key === 'Escape' && !modal.classList.contains('hidden')) closeModal();
  if(event.key==='Tab'&&!modal.classList.contains('hidden')){
    const focusable=[...modal.querySelectorAll('a[href],button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),[tabindex]:not([tabindex="-1"])')].filter(element=>!element.hidden&&element.offsetParent!==null);
    if(!focusable.length)return;
    const first=focusable[0],last=focusable[focusable.length-1];
    if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus()}
    else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus()}
  }
});

// Evita que o navegador restaure uma camada modal antiga e bloqueie a aplicação.
resetTransientUi();
window.addEventListener('pageshow', event => {
  if (event.persisted || modal.getAttribute('aria-hidden') !== 'false') resetTransientUi();
});
