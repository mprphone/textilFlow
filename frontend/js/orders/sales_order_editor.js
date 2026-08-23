import { crudCreate, crudDelete, crudList, crudUpdate, get, post } from '../api.js';
import { badge, date, esc, money, number } from '../format.js?v=20260819-5';
import { state } from '../state.js';
import { confirmDelete, empty, pageHeader, toast } from '../ui.js?v=20260821-19';
import { prepareFromSales } from '../pages/commercial_docs.js?v=20260822-33';

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

function articleBlockHtml(block, styles) {
  return `<section class="release-order-card" data-article-block data-block-id="${block.id}">
    <div class="release-order-card-head">
      <h3><span class="step-badge">${block.index}</span>
        <select data-style-select>
          <option value="">Selecionar modelo / artigo…</option>
          ${styles.map(row => `<option value="${row.id}" ${String(row.id) === String(block.styleId) ? 'selected' : ''}>${esc(row.reference)} · ${esc(row.description)}</option>`).join('')}
        </select>
      </h3>
      ${block.removable ? '<button type="button" class="btn small danger" data-remove-article>Remover artigo</button>' : ''}
    </div>
    <div class="release-order-grade-actions">
      <label>Nova cor<input type="text" data-new-color placeholder="Ex.: Preto"></label>
      <button type="button" class="btn small" data-add-color>+ Adicionar cor</button>
      <label>Novo tamanho<input type="text" data-new-size placeholder="Ex.: 3XL"></label>
      <button type="button" class="btn small" data-add-size>+ Tamanho</button>
    </div>
    <div class="table-wrap grade-table-wrap"><table class="data-table grade-table-full" data-grade-table></table></div>
    <p class="release-order-grade-summary">Total de cores: <b data-total-colors>0</b> · Total de peças: <b data-total-pieces>0</b> · Subtotal: <b data-total-value>0,00 €</b></p>
  </section>`;
}

function updateBlockTotals(root, block) {
  const scope = root.querySelector(`[data-article-block][data-block-id="${block.id}"]`);
  if (!scope) return { qty: 0, value: 0 };
  const { gradeState } = block;
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
    const cell = scope.querySelector(`[data-row-total="${row.id}"]`);
    if (cell) cell.textContent = number(rowQty);
  });
  scope.querySelectorAll('[data-col-total]').forEach((cell, idx) => { cell.textContent = number(colTotals[idx] || 0); });
  const grandCell = scope.querySelector('[data-grand-total]');
  if (grandCell) grandCell.textContent = number(grandQty);
  const colorsUsed = gradeState.rows.filter(row => gradeState.sizes.some(size => (Number(row.qty[size]) || 0) > 0)).length;
  scope.querySelector('[data-total-colors]').textContent = number(colorsUsed);
  scope.querySelector('[data-total-pieces]').textContent = number(grandQty);
  scope.querySelector('[data-total-value]').textContent = money(grandValue);
  return { qty: grandQty, value: grandValue };
}

function updateOrderTotals(root, blocks) {
  let qty = 0, value = 0;
  blocks.forEach(block => { const t = updateBlockTotals(root, block); qty += t.qty; value += t.value; });
  root.querySelector('[data-summary-pieces]').textContent = number(qty);
  root.querySelector('[data-summary-articles]').textContent = number(blocks.length);
  root.querySelector('[data-summary-value]').textContent = money(value);
}

function renderBlockGrid(root, block) {
  const scope = root.querySelector(`[data-article-block][data-block-id="${block.id}"]`);
  const table = scope.querySelector('[data-grade-table]');
  table.innerHTML = gradeTableMarkup(block.gradeState);
}

async function newArticleBlock(index, styleId = '') {
  let knownColors = [];
  let knownSizes = [];
  if (styleId) {
    const variants = await crudList('style-variants', state.companyId, `style_id=${styleId}`).catch(() => []);
    knownColors = [...new Set(variants.map(row => row.color).filter(Boolean))];
    knownSizes = [...new Set(variants.map(row => row.size).filter(Boolean))];
  }
  return {
    id: uid(), index, styleId, removable: true,
    gradeState: { sizes: knownSizes.length ? knownSizes : [...DEFAULT_SIZES], rows: [] },
    lineIdByVariant: {},
  };
}

export async function renderSalesOrders(panel) {
  const [rows, customers] = await Promise.all([
    crudList('sales-orders', state.companyId),
    crudList('customers', state.companyId).catch(() => []),
  ]);
  const customerName = id => customers.find(row => String(row.id) === String(id))?.name || '—';
  panel.innerHTML = pageHeader('Encomendas de cliente', 'Prazos, PO, estado, artigos e grade por cor/tamanho.', '<button class="btn primary" data-new-order>+ Nova encomenda</button>') + `
    <section class="listing-panel"><div class="table-wrap listing-table"><table class="data-table" aria-label="Encomendas"><thead><tr>
      <th>Encomenda</th><th>PO cliente</th><th>Cliente</th><th>Data</th><th>Entrega</th><th>Estado</th><th></th>
    </tr></thead><tbody>${rows.length ? rows.map(row => `<tr>
        <td><b>${esc(row.order_no)}</b></td>
        <td>${esc(row.customer_po || '—')}</td>
        <td>${esc(customerName(row.customer_id))}</td>
        <td>${date(row.order_date)}</td>
        <td>${date(row.delivery_date)}</td>
        <td>${badge(row.status)}</td>
        <td class="listing-actions"><div class="row-actions">
          <button class="btn small primary" type="button" data-erp-so="sales_invoice" data-id="${row.id}">Fatura</button>
          <button class="btn small" type="button" data-erp-so="sales_credit" data-id="${row.id}">NC</button>
          <button class="btn small" type="button" data-erp-so="sales_debit" data-id="${row.id}">ND</button>
          <button class="btn small" type="button" data-erp-so="sales_delivery" data-id="${row.id}">Guia</button>
          <button class="btn icon" type="button" data-edit-order="${row.id}" aria-label="Editar">✎</button>
          <button class="btn icon danger" type="button" data-delete-order="${row.id}" aria-label="Eliminar">×</button>
        </div></td>
      </tr>`).join('') : `<tr><td colspan="7">${empty('Sem encomendas', 'Crie a primeira encomenda de cliente.')}</td></tr>`}</tbody></table></div></section>`;

  panel.querySelector('[data-new-order]').addEventListener('click', () => renderSalesOrderEditor(panel, null));
  panel.querySelectorAll('[data-edit-order]').forEach(button => button.addEventListener('click', () => renderSalesOrderEditor(panel, Number(button.dataset.editOrder))));
  panel.querySelectorAll('[data-delete-order]').forEach(button => button.addEventListener('click', async () => {
    if (!confirmDelete('esta encomenda')) return;
    try { await crudDelete('sales-orders', Number(button.dataset.deleteOrder), state.companyId); toast('Encomenda eliminada.'); await renderSalesOrders(panel); }
    catch (error) { toast(error.message, 'error'); }
  }));
  panel.querySelectorAll('[data-erp-so]').forEach(button => button.addEventListener('click', async () => {
    try { const saved = await prepareFromSales(Number(button.dataset.id), button.dataset.erpSo); toast(`${saved.doc_no} preparado para o Primavera.`); }
    catch (error) { toast(error.message, 'error'); }
  }));
}

export async function renderSalesOrderEditor(panel, orderId) {
  const [customers, styles] = await Promise.all([
    crudList('customers', state.companyId),
    crudList('styles', state.companyId),
  ]);
  let order = { order_no: '', customer_id: '', customer_po: '', order_date: new Date().toISOString().slice(0, 10), delivery_date: '', status: 'confirmed', currency: 'EUR', notes: '' };
  const blocks = [];
  if (orderId) {
    const [orderDetail, lines] = await Promise.all([
      get(`/crud/sales-orders/${orderId}?company_id=${state.companyId}`),
      crudList('sales-order-lines', state.companyId, `sales_order_id=${orderId}`),
    ]);
    order = orderDetail;
    const byStyle = new Map();
    for (const line of lines) {
      if (!byStyle.has(line.style_id)) byStyle.set(line.style_id, []);
      byStyle.get(line.style_id).push(line);
    }
    let index = 1;
    for (const [styleId, styleLines] of byStyle) {
      const variants = await crudList('style-variants', state.companyId, `style_id=${styleId}`).catch(() => []);
      const variantById = new Map(variants.map(row => [row.id, row]));
      const rowsByColor = new Map();
      const sizesSet = new Set();
      const lineIdByVariant = {};
      styleLines.forEach(line => {
        const variant = line.variant_id ? variantById.get(line.variant_id) : null;
        const color = variant?.color || '—';
        const size = variant?.size || '—';
        sizesSet.add(size);
        if (!rowsByColor.has(color)) rowsByColor.set(color, { id: uid(), color, price: line.unit_price || 0, qty: {} });
        rowsByColor.get(color).qty[size] = line.quantity;
        if (line.variant_id) lineIdByVariant[line.variant_id] = line.id;
      });
      blocks.push({
        id: uid(), index: index++, styleId, removable: true,
        gradeState: { sizes: sizesSet.size ? [...sizesSet] : [...DEFAULT_SIZES], rows: [...rowsByColor.values()] },
        lineIdByVariant,
      });
    }
  }
  if (!blocks.length) blocks.push(await newArticleBlock(1));
  blocks.forEach((block, idx) => { block.index = idx + 1; });

  panel.innerHTML = `<div class="release-order-page">
    <header class="release-order-header">
      <button type="button" class="btn icon" data-back-order aria-label="Voltar">←</button>
      <div><h2>${orderId ? `Editar encomenda ${esc(order.order_no)}` : 'Nova encomenda'}</h2><p>Dados da encomenda e grade cor × tamanho por artigo</p></div>
      <div class="release-order-actions">
        <button type="button" class="btn" data-cancel-order>Cancelar</button>
        <button type="button" class="btn primary" data-submit-order>${orderId ? 'Guardar encomenda' : 'Criar encomenda'}</button>
      </div>
    </header>

    <section class="release-order-card">
      <h3><span class="step-badge">1</span> Dados principais</h3>
      <div class="release-order-fields">
        <label>Cliente *<select name="customer_id" required>${customers.map(row => `<option value="${row.id}" ${String(row.id) === String(order.customer_id) ? 'selected' : ''}>${esc(row.name)}</option>`).join('')}</select></label>
        <label>Número interno *<input name="order_no" value="${esc(order.order_no || '')}" required></label>
        <label>PO cliente<input name="customer_po" value="${esc(order.customer_po || '')}"></label>
        <label>Data<input type="date" name="order_date" value="${order.order_date || ''}"></label>
        <label>Entrega<input type="date" name="delivery_date" value="${order.delivery_date || ''}"></label>
        <label>Estado<select name="status">${['draft', 'confirmed', 'in_production', 'ready', 'shipped', 'cancelled'].map(value => `<option value="${value}" ${value === order.status ? 'selected' : ''}>${esc(value)}</option>`).join('')}</select></label>
        <label>Moeda<input name="currency" value="${esc(order.currency || 'EUR')}"></label>
        <label class="full">Notas<textarea name="notes">${esc(order.notes || '')}</textarea></label>
      </div>
    </section>

    <div data-articles-list></div>
    <button type="button" class="btn" data-add-article>+ Adicionar artigo</button>

    <aside class="release-order-summary-card">
      <h3>Resumo da encomenda</h3>
      <div><span>Total de peças</span><b data-summary-pieces>0</b></div>
      <div><span>N.º de artigos</span><b data-summary-articles>0</b></div>
      <div class="total"><span>Valor total</span><b data-summary-value>0,00 €</b></div>
    </aside>

    <footer class="release-order-footer">
      <button type="button" class="btn" data-cancel-order>Cancelar</button>
      <button type="button" class="btn primary" data-submit-order>${orderId ? 'Guardar encomenda' : 'Criar encomenda'}</button>
    </footer>
  </div>`;

  const root = panel.querySelector('.release-order-page');
  const articlesList = root.querySelector('[data-articles-list]');

  function paintArticles() {
    articlesList.innerHTML = blocks.map(block => articleBlockHtml(block, styles)).join('');
    blocks.forEach(block => renderBlockGrid(root, block));
    updateOrderTotals(root, blocks);
  }
  paintArticles();

  function findBlock(el) {
    const scope = el.closest('[data-article-block]');
    return scope ? blocks.find(b => b.id === scope.dataset.blockId) : null;
  }

  root.addEventListener('input', async event => {
    const styleSelect = event.target.closest('[data-style-select]');
    if (styleSelect) {
      const block = findBlock(styleSelect);
      if (block) {
        block.styleId = styleSelect.value ? Number(styleSelect.value) : '';
        if (block.styleId && !block.gradeState.rows.length) {
          const variants = await crudList('style-variants', state.companyId, `style_id=${block.styleId}`).catch(() => []);
          const knownColors = [...new Set(variants.map(row => row.color).filter(Boolean))];
          const knownSizes = [...new Set(variants.map(row => row.size).filter(Boolean))];
          if (knownSizes.length) block.gradeState.sizes = knownSizes;
          block.gradeState.rows = knownColors.map(color => ({ id: uid(), color, price: 0, qty: {} }));
          renderBlockGrid(root, block);
          updateOrderTotals(root, blocks);
        }
      }
      return;
    }
    const qtyInput = event.target.closest('[data-qty-input]');
    if (qtyInput) {
      const block = findBlock(qtyInput);
      const row = block?.gradeState.rows.find(r => r.id === qtyInput.dataset.row);
      if (row) { row.qty[qtyInput.dataset.size] = Number(qtyInput.value) || 0; updateOrderTotals(root, blocks); }
      return;
    }
    const priceInput = event.target.closest('[data-price-input]');
    if (priceInput) {
      const block = findBlock(priceInput);
      const row = block?.gradeState.rows.find(r => r.id === priceInput.dataset.row);
      if (row) { row.price = Number(priceInput.value) || 0; updateOrderTotals(root, blocks); }
      return;
    }
    const colorInput = event.target.closest('[data-color-input]');
    if (colorInput) {
      const block = findBlock(colorInput);
      const row = block?.gradeState.rows.find(r => r.id === colorInput.dataset.row);
      if (row) { row.color = colorInput.value; colorInput.previousElementSibling.style.background = colorSwatch(row.color); }
    }
  });

  root.addEventListener('click', async event => {
    if (event.target.closest('[data-back-order]') || event.target.closest('[data-cancel-order]')) {
      await renderSalesOrders(panel);
      return;
    }
    if (event.target.closest('[data-add-article]')) {
      blocks.push(await newArticleBlock(blocks.length + 1));
      paintArticles();
      return;
    }
    const removeArticle = event.target.closest('[data-remove-article]');
    if (removeArticle) {
      const block = findBlock(removeArticle);
      if (blocks.length <= 1) { toast('A encomenda precisa de pelo menos um artigo.', 'error'); return; }
      const idx = blocks.findIndex(b => b.id === block.id);
      if (idx >= 0) blocks.splice(idx, 1);
      blocks.forEach((b, i) => { b.index = i + 1; });
      paintArticles();
      return;
    }
    const block = findBlock(event.target);
    if (!block) {
      if (event.target.closest('[data-submit-order]')) await submit(event.target.closest('[data-submit-order]'));
      return;
    }
    if (event.target.closest('[data-add-color]')) {
      const scope = root.querySelector(`[data-article-block][data-block-id="${block.id}"]`);
      const input = scope.querySelector('[data-new-color]');
      const value = input.value.trim();
      if (!value) { toast('Indique o nome da cor.', 'error'); return; }
      if (block.gradeState.rows.some(row => row.color.toLocaleLowerCase('pt') === value.toLocaleLowerCase('pt'))) { toast('Essa cor já está na grelha.', 'error'); return; }
      block.gradeState.rows.push({ id: uid(), color: value, price: 0, qty: {} });
      input.value = '';
      renderBlockGrid(root, block); updateOrderTotals(root, blocks);
      return;
    }
    if (event.target.closest('[data-add-size]')) {
      const scope = root.querySelector(`[data-article-block][data-block-id="${block.id}"]`);
      const input = scope.querySelector('[data-new-size]');
      const value = input.value.trim();
      if (!value) { toast('Indique o tamanho.', 'error'); return; }
      if (block.gradeState.sizes.some(size => size.toLocaleLowerCase('pt') === value.toLocaleLowerCase('pt'))) { toast('Esse tamanho já está na grelha.', 'error'); return; }
      block.gradeState.sizes.push(value);
      input.value = '';
      renderBlockGrid(root, block); updateOrderTotals(root, blocks);
      return;
    }
    const removeColor = event.target.closest('[data-remove-color]');
    if (removeColor) {
      if (block.gradeState.rows.length <= 1) { toast('A grelha precisa de pelo menos uma cor.', 'error'); return; }
      block.gradeState.rows = block.gradeState.rows.filter(row => row.id !== removeColor.dataset.removeColor);
      renderBlockGrid(root, block); updateOrderTotals(root, blocks);
      return;
    }
    const removeSize = event.target.closest('[data-remove-size]');
    if (removeSize) {
      if (block.gradeState.sizes.length <= 1) { toast('A grelha precisa de pelo menos um tamanho.', 'error'); return; }
      const size = removeSize.dataset.removeSize;
      block.gradeState.sizes = block.gradeState.sizes.filter(item => item !== size);
      block.gradeState.rows.forEach(row => { delete row.qty[size]; });
      renderBlockGrid(root, block); updateOrderTotals(root, blocks);
    }
  });

  async function submit(button) {
    const orderNo = root.querySelector('input[name="order_no"]').value.trim();
    const customerId = Number(root.querySelector('select[name="customer_id"]').value || 0);
    if (!orderNo) { toast('Indique o número interno da encomenda.', 'error'); return; }
    if (!customerId) { toast('Escolha o cliente.', 'error'); return; }
    for (const block of blocks) {
      if (!block.styleId) { toast(`Escolha o modelo/artigo do artigo ${block.index}.`, 'error'); return; }
    }
    button.disabled = true;
    button.textContent = 'A guardar…';
    try {
      const headerPayload = {
        company_id: state.companyId,
        customer_id: customerId,
        order_no: orderNo,
        customer_po: root.querySelector('input[name="customer_po"]').value || null,
        order_date: root.querySelector('input[name="order_date"]').value || null,
        delivery_date: root.querySelector('input[name="delivery_date"]').value || null,
        status: root.querySelector('select[name="status"]').value,
        currency: root.querySelector('input[name="currency"]').value || 'EUR',
        notes: root.querySelector('textarea[name="notes"]').value || null,
      };
      const savedOrder = orderId ? await crudUpdate('sales-orders', orderId, headerPayload) : await crudCreate('sales-orders', headerPayload);
      const salesOrderId = savedOrder.id || orderId;

      for (const block of blocks) {
        const usedVariantIds = new Set();
        for (const row of block.gradeState.rows) {
          const color = (row.color || '').trim();
          for (const size of block.gradeState.sizes) {
            const quantity = Number(row.qty[size]) || 0;
            if (quantity <= 0) continue;
            if (!color) { throw new Error(`Todas as linhas com quantidade têm de ter uma cor (artigo ${block.index}).`); }
            const variant = await post(`/products/styles/${block.styleId}/variants`, { color, size });
            usedVariantIds.add(variant.id);
            const linePayload = {
              company_id: state.companyId,
              sales_order_id: salesOrderId, style_id: block.styleId, variant_id: variant.id,
              description: `${color} · ${size}`, quantity, unit_price: row.price || 0,
              delivery_date: headerPayload.delivery_date,
            };
            const existingLineId = block.lineIdByVariant[variant.id];
            if (existingLineId) await crudUpdate('sales-order-lines', existingLineId, linePayload);
            else { const savedLine = await crudCreate('sales-order-lines', linePayload); block.lineIdByVariant[variant.id] = savedLine.id; }
          }
        }
        for (const [variantId, lineId] of Object.entries(block.lineIdByVariant)) {
          if (!usedVariantIds.has(Number(variantId))) await crudDelete('sales-order-lines', lineId, state.companyId);
        }
      }
      toast(orderId ? 'Encomenda atualizada.' : 'Encomenda criada.');
      await renderSalesOrders(panel);
    } catch (error) {
      button.disabled = false;
      button.textContent = orderId ? 'Guardar encomenda' : 'Criar encomenda';
      toast(error.message, 'error');
    }
  }
}
