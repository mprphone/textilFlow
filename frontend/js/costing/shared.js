import { esc } from '../format.js?v=20260819-6';

export const categories = [
  ['material', 'Materiais'],
  ['labor', 'Mão de obra'],
  ['machine', 'Máquinas'],
  ['subcontract', 'Serviços externos'],
  ['overhead', 'Custos gerais'],
  ['other', 'Outros'],
];

export const categoryLabel = key => categories.find(([value]) => value === key)?.[1] || key;

export function categoryOptions(selected = '') {
  return categories.map(([value, label]) => `<option value="${value}" ${value === selected ? 'selected' : ''}>${esc(label)}</option>`).join('');
}

export function statusText(status) {
  return ({draft:'Rascunho', approved:'Aceite', production:'Em produção', obsolete:'Obsoleta', on_track:'Dentro do custo', warning:'Atenção', risk:'Acima do custo'})[status] || status;
}

export function todayIso() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
}

export const valueOf = (root, selector) => root.querySelector(selector)?.value ?? '';
export const numericValue = (root, selector) => {
  const parsed = Number(valueOf(root, selector));
  return Number.isFinite(parsed) ? parsed : 0;
};
