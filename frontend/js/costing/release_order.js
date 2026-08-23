import { crudList, get, post } from '../api.js';
import { esc, money, number } from '../format.js?v=20260819-8';
import { state } from '../state.js';
import { toast } from '../ui.js?v=20260820-5';
import { releaseRequirements } from './proposals.js?v=20260823-1';

const DEFAULT_SIZES = ['S', 'M', 'L', 'XL', 'XXL'];

const COLOR_HEX = {
  preto: '#1a1a1a', branco: '#f5f5f5', cinzento: '#8a8a8a', cinza: '#8a8a8a',
  azul: '#2f5fa8', azulmarinho: '#1c2e4a', marinho: '#1c2e4a', navy: '#1c2e4a',
  vermelho: '#b5352f', verde: '#3f7a4e', bege: '#d8c7a1', rosa: '#d98aa3',
  amarelo: '#e0c23a', laranja: '#d97a34', roxo: '#7454a0', castanho: '#7a5030', camel: '#b58a55',
};

function colorSwatch(name) {
  const key = (name || '').trim().toLocaleLowerCase('pt').normalize('NFD').replace(/[^a-z]/g, '');
  if (!key) return '#d7dee8';
  if (COLOR_HEX[key]) return COLOR_HEX[key];
  let hash = 0;
  for (const ch of key) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  return `hsl(${hash % 360}, 45%, 55%)`;
}

function uid() { return Math.random().toString(36).slice(2, 9); }

function gradeTableMarkup(gradeState) {
  const { rows, sizes } = gradeState;
  if (!rows.length || !sizes.length) return '';
  return `<thead><tr>
      <th>Cor</th><th>Preço unitário</th>
      ${sizes.map(size => `<th>${esc(size)}<button type="button" class="grade-remove-size" data-remove-size="${esc(size)}" aria-label="Remover tamanho ${esc(size)}">×</button></th>`).join('')}
      <th>Total</th><th></th>
    </tr></thead>
    <tbody>${rows.map(row => `
      <tr data-grade-row="${row.id}">
        <td class="grade-color-cell"><span class="grade-swatch" style="background:${colorSwatch(row.color)}"></span><input type="text" data-color-input data-row="${row.id}" value="${esc(row.color)}" placeholder="Cor"></td>
        <td><div class="grade-price-cell"><input type="number" min="0" step="0.01" data-price-input data-row="${row.id}" value="${row.price || ''}" placeholder="0,00"><span>EUR</span></div></td>
        ${sizes.map(size => `<td><input type="number" min="0" step="1" data-qty-input data-row="${row.id}" data-size="${esc(size)}" value="${row.qty[size] || ''}" placeholder="0"></td>`).join('')}
        <td class="grade-row-total" data-row-total="${row.id}">0</td>
        <td><button type="button" class="btn icon danger" data-remove-color="${row.id}" aria-label="Remover cor">🗑</button></td>
      </tr>`).join('')}</tbody>
    <tfoot><tr><td>Total por tamanho</td><td></td>${sizes.map(() => '<td data-col-total>0</td>').join('')}<td data-grand-total>0</td><td></td></tr></tfoot>`;
}

export async function renderReleaseOrder(container, sheetId, afterRelease) {
  const detail = await get(`/costing/sheets/${sheetId}`);
  const { sheet, lines } = detail;
  const [customers, existingVariants] = await Promise.all([
    crudList('customers', state.companyId),
    crudList('style-variants', state.companyId, `style_id=${sheet.style_id}`).catch(() => []),
  ]);
  const customer = customers.find(row => String(row.id) === String(sheet.customer_id));
  const idempotencyKey = globalThis.crypto?.randomUUID?.() || `cost-${sheet.id}-${Date.now()}`;
  const defaultOrder = `OF-${new Date().getFullYear()}-${String(sheet.id).padStart(5, '0')}`;

  const knownColors = [...new Set(existingVariants.map(row => row.color).filter(Boolean))];
  const knownSizes = [...new Set(existingVariants.map(row => row.size).filter(Boolean))];
  const gradeState = {
    sizes: knownSizes.length ? [...knownSizes] : [...DEFAULT_SIZES],
    rows: knownColors.length
      ? knownColors.map(color => ({ id: uid(), color, price: sheet.selling_price || 0, qty: {} }))
      : [{ id: uid(), color: '', price: sheet.selling_price || 0, qty: {} }],
  };

  container.innerHTML = `<div class="release-order-page">
    <header class="release-order-header">
      <button type="button" class="btn icon" data-back-release aria-label="Voltar">←</button>
      <div><h2>Nova Ordem de Fabrico</h2><p>Criação rápida a partir da proposta ${esc(sheet.quote_no)}</p></div>
      <div class="release-order-actions">
        <button type="button" class="btn" data-cancel-release>Cancelar</button>
        <button type="button" class="btn primary" data-submit-release>Criar Ordem de Fabrico</button>
      </div>
    </header>

    <section class="release-order-card">
      <h3><span class="step-badge">1</span> Dados principais</h3>
      <div class="release-order-fields">
        <label>Cliente<input value="${esc(customer ? customer.name : (sheet.customer_name === '—' ? 'Sem cliente' : sheet.customer_name))}" disabled></label>
        <label>Modelo / Artigo<input value="${esc(sheet.style_reference)} · ${esc(sheet.style_description)}" disabled></label>
        <label>Referência cliente / Encomenda<input name="customer_po" placeholder="Referência da encomenda do cliente"></label>
        <label>Data de entrega<input type="date" name="delivery_date"></label>
        <label>N.º ordem de fabrico<input name="order_no" value="${esc(defaultOrder)}" required></label>
      </div>
    </section>

    <section class="release-order-card">
      <div class="release-order-card-head">
        <h3><span class="step-badge">2</span> Grade de cores, tamanhos e preços</h3>
        <div class="release-order-grade-actions">
          <label>Nova cor<input type="text" data-new-color placeholder="Ex.: Preto" list="release-color-list"></label>
          <button type="button" class="btn small" data-add-color>+ Adicionar cor</button>
          <label>Novo tamanho<input type="text" data-new-size placeholder="Ex.: 3XL"></label>
          <button type="button" class="btn small" data-add-size>+ Tamanho</button>
        </div>
      </div>
      <datalist id="release-color-list">${knownColors.map(c => `<option value="${esc(c)}">`).join('')}</datalist>
      <p class="muted">Defina as quantidades e o preço unitário por cor — os preços podem ser diferentes por cor.</p>
      <div class="table-wrap grade-table-wrap"><table class="data-table grade-table-full" data-grade-table></table></div>
      <p class="release-order-grade-summary">Total de cores: <b data-total-colors>0</b> · Total de peças: <b data-total-pieces>0</b></p>
    </section>

    <div class="release-order-columns">
      <section class="release-order-card">
        <h3><span class="step-badge">3</span> Condições comerciais</h3>
        <div class="release-order-fields">
          <label>Condições de pagamento<input name="payment_terms" value="${esc(customer?.payment_terms || sheet.payment_terms || '30 dias')}"></label>
          <label>Valor total da encomenda<input data-total-value readonly value="0,00 €"></label>
        </div>
        <label class="full">Observações (opcional)<textarea name="notes" placeholder="Notas, observações ou instruções especiais…"></textarea></label>
      </section>
      <aside class="release-order-summary-card">
        <h3>Resumo da ordem</h3>
        <div><span>Total de peças</span><b data-summary-pieces>0</b></div>
        <div><span>N.º de cores</span><b data-summary-colors>0</b></div>
        <div><span>N.º de tamanhos</span><b data-summary-sizes>0</b></div>
        <div class="total"><span>Valor total da encomenda</span><b data-summary-value>0,00 €</b></div>
      </aside>
    </div>

    <p class="release-order-info-banner">ℹ Ao criar, os artigos (por cor e tamanho) são criados automaticamente no TextileFlow e ligados ao Primavera.</p>
    <div data-release-preview></div>
    <footer class="release-order-footer">
      <button type="button" class="btn" data-cancel-release>Cancelar</button>
      <button type="button" class="btn primary" data-submit-release>Criar Ordem de Fabrico</button>
    </footer>
  </div>`;

  const root = container.querySelector('.release-order-page');
  const table = root.querySelector('[data-grade-table]');
  const previewRoot = root.querySelector('[data-release-preview]');
  let previewTimer;
  let previewSequence = 0;

  const loadPreview = async () => {
    const quantity = Math.max(1, updateTotals());
    const sequence = ++previewSequence;
    previewRoot.innerHTML = '<div class="loading">A calcular consumos e disponibilidade…</div>';
    try {
      const preview = await get(`/costing/sheets/${sheet.id}/production-preview?quantity=${encodeURIComponent(quantity)}`);
      if (sequence !== previewSequence) return;
      previewRoot.innerHTML = releaseRequirements(preview, lines, quantity, Boolean(sheet.customer_id || customer));
    } catch (error) {
      if (sequence !== previewSequence) return;
      previewRoot.innerHTML = `<div class="cost-preview-error"><b>Não foi possível calcular.</b><span>${esc(error.message)}</span></div>`;
    }
  };
  const schedulePreview = () => { clearTimeout(previewTimer); previewTimer = setTimeout(loadPreview, 300); };

  function renderGrid() {
    table.innerHTML = gradeTableMarkup(gradeState);
    updateTotals();
  }

  function updateTotals() {
    const colTotals = gradeState.sizes.map(() => 0);
    let grandQty = 0;
    let grandValue = 0;
    gradeState.rows.forEach(row => {
      let rowQty = 0;
      gradeState.sizes.forEach((size, idx) => {
        const qty = Math.max(0, Number(row.qty[size]) || 0);
        rowQty += qty;
        colTotals[idx] += qty;
      });
      grandQty += rowQty;
      grandValue += rowQty * (Number(row.price) || 0);
      const cell = root.querySelector(`[data-row-total="${row.id}"]`);
      if (cell) cell.textContent = number(rowQty);
    });
    root.querySelectorAll('[data-col-total]').forEach((cell, idx) => { cell.textContent = number(colTotals[idx] || 0); });
    const grandCell = root.querySelector('[data-grand-total]');
    if (grandCell) grandCell.textContent = number(grandQty);
    const colorsUsed = gradeState.rows.filter(row => gradeState.sizes.some(size => (Number(row.qty[size]) || 0) > 0)).length;
    root.querySelector('[data-total-colors]').textContent = number(colorsUsed);
    root.querySelector('[data-total-pieces]').textContent = number(grandQty);
    root.querySelector('[data-summary-pieces]').textContent = number(grandQty);
    root.querySelector('[data-summary-colors]').textContent = number(colorsUsed);
    root.querySelector('[data-summary-sizes]').textContent = number(gradeState.sizes.length);
    root.querySelector('[data-summary-value]').textContent = money(grandValue);
    root.querySelector('[data-total-value]').value = money(grandValue);
    return grandQty;
  }

  renderGrid();

  root.addEventListener('input', event => {
    const qtyInput = event.target.closest('[data-qty-input]');
    if (qtyInput) {
      const row = gradeState.rows.find(r => r.id === qtyInput.dataset.row);
      if (row) { row.qty[qtyInput.dataset.size] = Number(qtyInput.value) || 0; updateTotals(); schedulePreview(); }
      return;
    }
    const priceInput = event.target.closest('[data-price-input]');
    if (priceInput) {
      const row = gradeState.rows.find(r => r.id === priceInput.dataset.row);
      if (row) { row.price = Number(priceInput.value) || 0; updateTotals(); }
      return;
    }
    const colorInput = event.target.closest('[data-color-input]');
    if (colorInput) {
      const row = gradeState.rows.find(r => r.id === colorInput.dataset.row);
      if (row) {
        row.color = colorInput.value;
        colorInput.previousElementSibling.style.background = colorSwatch(row.color);
      }
    }
  });

  root.addEventListener('click', event => {
    if (event.target.closest('[data-add-color]')) {
      const input = root.querySelector('[data-new-color]');
      const value = input.value.trim();
      if (!value) { toast('Indique o nome da cor.', 'error'); return; }
      if (gradeState.rows.some(row => row.color.toLocaleLowerCase('pt') === value.toLocaleLowerCase('pt'))) { toast('Essa cor já está na grelha.', 'error'); return; }
      gradeState.rows.push({ id: uid(), color: value, price: sheet.selling_price || 0, qty: {} });
      input.value = '';
      renderGrid();
      return;
    }
    if (event.target.closest('[data-add-size]')) {
      const input = root.querySelector('[data-new-size]');
      const value = input.value.trim();
      if (!value) { toast('Indique o tamanho.', 'error'); return; }
      if (gradeState.sizes.some(size => size.toLocaleLowerCase('pt') === value.toLocaleLowerCase('pt'))) { toast('Esse tamanho já está na grelha.', 'error'); return; }
      gradeState.sizes.push(value);
      input.value = '';
      renderGrid();
      return;
    }
    const removeColor = event.target.closest('[data-remove-color]');
    if (removeColor) {
      if (gradeState.rows.length <= 1) { toast('A grelha precisa de pelo menos uma cor.', 'error'); return; }
      gradeState.rows = gradeState.rows.filter(row => row.id !== removeColor.dataset.removeColor);
      renderGrid(); schedulePreview();
      return;
    }
    const removeSize = event.target.closest('[data-remove-size]');
    if (removeSize) {
      if (gradeState.sizes.length <= 1) { toast('A grelha precisa de pelo menos um tamanho.', 'error'); return; }
      const size = removeSize.dataset.removeSize;
      gradeState.sizes = gradeState.sizes.filter(item => item !== size);
      gradeState.rows.forEach(row => { delete row.qty[size]; });
      renderGrid(); schedulePreview();
      return;
    }
    if (event.target.closest('[data-back-release]') || event.target.closest('[data-cancel-release]')) {
      afterRelease();
      return;
    }
    if (event.target.closest('[data-submit-release]')) {
      submit(event.target.closest('[data-submit-release]'));
    }
  });

  async function submit(button) {
    const grade = [];
    let missingColor = false;
    gradeState.rows.forEach(row => {
      const color = (row.color || '').trim();
      gradeState.sizes.forEach(size => {
        const quantity = Number(row.qty[size]) || 0;
        if (quantity <= 0) return;
        if (!color) { missingColor = true; return; }
        grade.push({ color, size, quantity, unit_price: row.price > 0 ? row.price : null });
      });
    });
    if (missingColor) { toast('Todas as linhas com quantidade têm de ter uma cor.', 'error'); return; }
    if (!grade.length) { toast('Adicione pelo menos uma quantidade na grelha de cores e tamanhos.', 'error'); return; }
    const orderNo = root.querySelector('input[name="order_no"]').value.trim();
    if (!orderNo) { toast('Indique o número da ordem de fabrico.', 'error'); return; }
    if (!sheet.customer_id && !customer) { toast('Esta proposta não tem cliente associado.', 'error'); return; }
    button.disabled = true;
    button.textContent = 'A criar…';
    try {
      const result = await post(`/costing/sheets/${sheet.id}/release`, {
        grade,
        order_no: orderNo,
        customer_id: sheet.customer_id || customer.id,
        delivery_date: root.querySelector('input[name="delivery_date"]').value || null,
        reserve_stock: true,
        idempotency_key: idempotencyKey,
      });
      toast(result.already_released ? 'Esta proposta já estava ligada à produção.' : `Ordem ${result.production_order?.order_no || ''} criada. ${(result.fabric_purchase_orders || []).length ? 'Encomenda de malha: ' + result.fabric_purchase_orders.map(row => row.order_no).join(', ') + '.' : 'Malha coberta por stock.'}`);
      await afterRelease();
    } catch (error) {
      button.disabled = false;
      button.textContent = 'Criar Ordem de Fabrico';
      toast(error.message, 'error');
    }
  }

  await loadPreview();
}
