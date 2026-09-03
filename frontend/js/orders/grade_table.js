import { esc } from '../format.js?v=20260826-3';

export const DEFAULT_SIZES = ['S', 'M', 'L', 'XL', 'XXL'];

const COLOR_HEX = {
  preto: '#1a1a1a', branco: '#f5f5f5', cinzento: '#8a8a8a', cinza: '#8a8a8a',
  azul: '#2f5fa8', azulmarinho: '#1c2e4a', marinho: '#1c2e4a', navy: '#1c2e4a',
  vermelho: '#b5352f', verde: '#3f7a4e', bege: '#d8c7a1', rosa: '#d98aa3',
  amarelo: '#e0c23a', laranja: '#d97a34', roxo: '#7454a0', castanho: '#7a5030', camel: '#b58a55',
};

export function colorSwatch(name) {
  const key = (name || '').trim().toLocaleLowerCase('pt').normalize('NFD').replace(/[^a-z]/g, '');
  if (!key) return '#d7dee8';
  if (COLOR_HEX[key]) return COLOR_HEX[key];
  let hash = 0;
  for (const ch of key) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  return `hsl(${hash % 360}, 45%, 55%)`;
}

export function uid() {
  return Math.random().toString(36).slice(2, 9);
}

export function gradeTableMarkup(gradeState, currency = 'EUR', { emptyRow = false, labelSize, labelColor } = {}) {
  const { rows, sizes } = gradeState;
  if (!sizes.length) return '';
  const sizeText = (size) => (labelSize ? labelSize(size) : size);
  const colorText = (color) => (labelColor ? labelColor(color) : (color || ''));
  const body = rows.length ? rows.map((row) => `
      <tr data-grade-row="${row.id}">
        <td class="grade-color-cell"><span class="grade-swatch" style="background:${colorSwatch(row.color)}"></span><input type="text" data-color-input data-row="${row.id}" value="${esc(colorText(row.color))}" placeholder="Cor"></td>
        <td><div class="grade-price-cell"><input type="number" min="0" step="0.01" data-price-input data-row="${row.id}" value="${row.price || ''}" placeholder="0,00"><span>${esc(currency)}</span></div></td>
        ${sizes.map((size) => `<td><input type="number" min="0" step="1" data-qty-input data-row="${row.id}" data-size="${esc(size)}" value="${row.qty[size] || ''}" placeholder="0"></td>`).join('')}
        <td class="grade-row-total" data-row-total="${row.id}">0</td>
        <td><button type="button" class="btn icon danger" data-icon="delete" data-remove-color="${row.id}" aria-label="Remover cor" title="Remover cor"></button></td>
      </tr>`).join('') : (emptyRow ? `<tr class="grade-empty-row"><td colspan="${sizes.length + 4}"><span data-icon="palette" aria-hidden="true"></span><b>Adicione a primeira cor</b><small>Use o campo acima para construir a grelha deste artigo.</small></td></tr>` : '');
  return `<thead><tr>
      <th class="grade-color-heading">Cor</th><th class="grade-price-heading">Preço unitário<small>(por peça)</small></th>
      ${sizes.map((size) => `<th class="grade-size-heading"><span>${esc(sizeText(size))}</span><button type="button" class="grade-remove-size" data-icon="delete" data-remove-size="${esc(size)}" aria-label="Remover tamanho ${esc(size)}" title="Remover tamanho ${esc(size)}"></button></th>`).join('')}
      <th class="grade-total-heading">Total</th><th class="grade-action-heading"><span class="sr-only">Ações</span></th>
    </tr></thead>
    <tbody>${body}</tbody>
    <tfoot><tr><td colspan="2">Total por tamanho</td>${sizes.map(() => '<td data-col-total>0</td>').join('')}<td colspan="2" class="grade-grand-total"><small>Total do artigo</small><b data-grand-total>0</b></td></tr></tfoot>`;
}
