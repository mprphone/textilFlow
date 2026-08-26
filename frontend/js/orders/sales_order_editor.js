import { crudDelete, crudList, get, post } from '../api.js';
import { badge, date, esc, money, number } from '../format.js?v=20260826-3';
import { state } from '../state.js';
import { closeModal, confirmDelete, empty, openModal, pageHeader, toast } from '../ui.js?v=20260826-3';

const DEFAULT_SIZES = ['S', 'M', 'L', 'XL', 'XXL'];

const STATUS_LABELS = {
  draft: 'Rascunho', confirmed: 'Confirmada', in_production: 'Em produção',
  ready: 'Pronta', partially_shipped: 'Expedida parcialmente', shipped: 'Expedida', cancelled: 'Cancelada',
};
const EDITABLE_STATUS_LABELS = { draft: STATUS_LABELS.draft, confirmed: STATUS_LABELS.confirmed };

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

function orderMoney(value, currency = 'EUR') {
  try {
    return new Intl.NumberFormat('pt-PT', { style: 'currency', currency: currency || 'EUR' }).format(Number(value) || 0);
  } catch {
    return money(value);
  }
}

function gradeLabel(value, kind) {
  if (value && value !== '—') return value;
  return kind === 'size' ? 'Único' : 'Sem cor';
}

function gradeTableMarkup(gradeState, currency = 'EUR') {
  const { rows, sizes } = gradeState;
  if (!sizes.length) return '';
  return `<thead><tr>
      <th class="grade-color-heading">Cor</th><th class="grade-price-heading">Preço unitário<small>(por peça)</small></th>
      ${sizes.map(size => `<th class="grade-size-heading"><span>${esc(gradeLabel(size, 'size'))}</span><button type="button" class="grade-remove-size" data-icon="delete" data-remove-size="${esc(size)}" aria-label="Remover tamanho ${esc(size)}" title="Remover tamanho ${esc(size)}"></button></th>`).join('')}
      <th class="grade-total-heading">Total</th><th class="grade-action-heading"><span class="sr-only">Ações</span></th>
    </tr></thead>
    <tbody>${rows.length ? rows.map(row => `
      <tr data-grade-row="${row.id}">
        <td class="grade-color-cell"><span class="grade-swatch" style="background:${colorSwatch(row.color)}"></span><input type="text" data-color-input data-row="${row.id}" value="${esc(gradeLabel(row.color, 'color'))}" placeholder="Cor"></td>
        <td><div class="grade-price-cell"><input type="number" min="0" step="0.01" data-price-input data-row="${row.id}" value="${row.price || ''}" placeholder="0,00"><span>${esc(currency)}</span></div></td>
        ${sizes.map(size => `<td><input type="number" min="0" step="1" data-qty-input data-row="${row.id}" data-size="${esc(size)}" value="${row.qty[size] || ''}" placeholder="0"></td>`).join('')}
        <td class="grade-row-total" data-row-total="${row.id}">0</td>
        <td><button type="button" class="btn icon danger" data-icon="delete" data-remove-color="${row.id}" aria-label="Remover cor" title="Remover cor"></button></td>
      </tr>`).join('') : `<tr class="grade-empty-row"><td colspan="${sizes.length + 4}"><span data-icon="palette" aria-hidden="true"></span><b>Adicione a primeira cor</b><small>Use o campo acima para construir a grelha deste artigo.</small></td></tr>`}</tbody>
    <tfoot><tr><td colspan="2">Total por tamanho</td>${sizes.map(() => '<td data-col-total>0</td>').join('')}<td colspan="2" class="grade-grand-total"><small>Total do artigo</small><b data-grand-total>0</b></td></tr></tfoot>`;
}

function requirementsHtml(data) {
  if (!data.requirements.length) {
    return '<p class="muted requirement-empty">Este artigo ainda não tem ficha técnica (BOM) associada — não há necessidade de material a calcular.</p>';
  }
  const rows = data.requirements.map(row => `<tr class="${row.status === 'shortage' ? 'requirement-row-shortage' : ''}">
      <td><b>${esc(row.material_code)}</b><div class="table-subline">${esc(row.material_name)}</div></td>
      <td>${number(row.required_quantity)} ${esc(row.unit || '')}</td>
      <td>${number(row.available_quantity)} ${esc(row.unit || '')}</td>
      <td>${row.shortage_quantity > 0 ? `<b class="requirement-shortage">${number(row.shortage_quantity)} ${esc(row.unit || '')}</b>` : '<span class="requirement-ok">Coberto</span>'}</td>
      <td>${money(row.estimated_cost)}</td>
    </tr>`).join('');
  const totalCost = data.requirements.reduce((sum, row) => sum + (row.estimated_cost || 0), 0);
  const shortageCount = data.requirements.filter(row => row.status === 'shortage').length;
  return `<div class="requirement-panel">
    <div class="table-wrap"><table class="data-table"><thead><tr><th>Material</th><th>Necessário</th><th>Disponível</th><th>Em falta</th><th>Custo estimado</th></tr></thead><tbody>${rows}</tbody></table></div>
    <p class="requirement-summary">${shortageCount ? `<b class="requirement-shortage">${shortageCount} material(is) com falta de stock.</b>` : '<b class="requirement-ok">Stock cobre toda a necessidade.</b>'} Custo estimado de materiais: <b>${money(totalCost)}</b> para ${number(data.quantity)} peças.</p>
  </div>`;
}

function articleBlockHtml(block, styles) {
  const selectedStyle = styles.find(row => String(row.id) === String(block.styleId));
  return `<section class="card release-order-card release-order-article-card" data-article-block data-block-id="${block.id}">
    <div class="release-order-article-header">
      <div class="release-order-article-identity">
        <span class="step-badge">${String(block.index).padStart(2, '0')}</span>
        <div><select data-style-select aria-label="Modelo ou artigo">
          <option value="">Selecionar modelo / artigo…</option>
          ${styles.map(row => `<option value="${row.id}" ${String(row.id) === String(block.styleId) ? 'selected' : ''}>${esc(row.reference)} · ${esc(row.description)}</option>`).join('')}
        </select><small>Referência interna: <span data-style-reference>${esc(selectedStyle?.reference || 'por definir')}</span></small></div>
      </div>
      <div class="release-order-article-actions">
        <div class="release-order-article-metric"><small>Peças totais</small><b><span data-article-pieces>0</span> un.</b></div>
        <div class="release-order-article-metric"><small>Preço médio</small><b data-article-value>0,00 €</b></div>
        <button type="button" class="btn release-material-button" data-calc-requirements><span>Ver ficha de custo</span></button>
        <button type="button" class="btn icon" data-icon="copy" data-duplicate-article aria-label="Duplicar artigo" title="Duplicar artigo"></button>
        ${block.removable ? '<button type="button" class="btn icon danger" data-icon="delete" data-remove-article aria-label="Remover artigo" title="Remover artigo"></button>' : ''}
      </div>
    </div>
    <div class="release-grade-toolbar">
      <div></div>
      <div class="grade-add-row">
        <div class="grade-quick-add"><button type="button" class="btn small" data-toggle-color-add><span data-icon="add" aria-hidden="true"></span>Adicionar cor</button><div class="grade-inline-add" data-color-add-panel hidden><input type="text" data-new-color placeholder="Ex.: Preto"><button type="button" class="grade-add-btn" data-icon="check" data-add-color aria-label="Confirmar cor" title="Confirmar cor"></button></div></div>
        <div class="grade-quick-add"><button type="button" class="btn small" data-toggle-size-add><span data-icon="add" aria-hidden="true"></span>Adicionar tamanho</button><div class="grade-inline-add" data-size-add-panel hidden><input type="text" data-new-size placeholder="Ex.: 3XL"><button type="button" class="grade-add-btn" data-icon="check" data-add-size aria-label="Confirmar tamanho" title="Confirmar tamanho"></button></div></div>
      </div>
    </div>
    <div class="table-wrap grade-table-wrap"><table class="data-table grade-table-full" data-grade-table></table></div>
    <div data-requirements></div>
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
  const currency = root.querySelector('[name="currency"]')?.value || 'EUR';
  scope.querySelector('[data-article-pieces]').textContent = number(grandQty);
  scope.querySelector('[data-article-value]').textContent = orderMoney(grandQty ? grandValue / grandQty : 0, currency);
  return { qty: grandQty, value: grandValue };
}

function updateOrderTotals(root, blocks) {
  let qty = 0, value = 0;
  blocks.forEach(block => { const t = updateBlockTotals(root, block); qty += t.qty; value += t.value; });
  root.querySelector('[data-summary-pieces]').textContent = number(qty);
  root.querySelector('[data-summary-articles]').textContent = number(blocks.length);
  const currency = root.querySelector('[name="currency"]')?.value || 'EUR';
  const vatRate = Math.max(0, Number(root.dataset.vatRate) || 0);
  const vat = value * vatRate / 100;
  root.querySelectorAll('[data-summary-value],[data-order-total]').forEach(element => { element.textContent = orderMoney(value, currency); });
  root.querySelector('[data-summary-merchandise]').textContent = orderMoney(value, currency);
  root.querySelector('[data-summary-vat]').textContent = orderMoney(vat, currency);
  root.querySelector('[data-summary-vat-label]').textContent = `${number(vatRate)}%${root.dataset.vatLabel ? ` · ${root.dataset.vatLabel}` : ''}`;
}

function renderBlockGrid(root, block) {
  const scope = root.querySelector(`[data-article-block][data-block-id="${block.id}"]`);
  const table = scope.querySelector('[data-grade-table]');
  table.innerHTML = gradeTableMarkup(block.gradeState, root.querySelector('[name="currency"]')?.value || 'EUR');
}

function blockTotalQty(block) {
  return block.gradeState.rows.reduce((sum, row) => sum + block.gradeState.sizes.reduce((s, size) => s + (Number(row.qty[size]) || 0), 0), 0);
}

function orderCommunicationData(root, blocks, styles, customers) {
  const customerId = root.querySelector('[name="customer_id"]')?.value;
  const customer = customers.find(row => String(row.id) === String(customerId));
  const currency = root.querySelector('[name="currency"]')?.value || 'EUR';
  const articles = blocks.map(block => {
    const style = styles.find(row => String(row.id) === String(block.styleId));
    const rows = block.gradeState.rows.map(row => {
      const quantities = block.gradeState.sizes
        .map(size => ({ size: gradeLabel(size, 'size'), quantity: Number(row.qty[size]) || 0 }))
        .filter(item => item.quantity > 0);
      const quantity = quantities.reduce((sum, item) => sum + item.quantity, 0);
      return { color: gradeLabel(row.color, 'color'), price: Number(row.price) || 0, quantities, quantity };
    }).filter(row => row.quantity > 0);
    return {
      reference: style?.reference || 'Artigo por selecionar', description: style?.description || '', rows,
      quantity: rows.reduce((sum, row) => sum + row.quantity, 0),
      value: rows.reduce((sum, row) => sum + row.quantity * row.price, 0),
    };
  });
  return {
    customer, currency, articles,
    orderNo: root.querySelector('[name="order_no"]')?.value || 'Nova encomenda',
    customerPo: root.querySelector('[name="customer_po"]')?.value || '',
    orderDate: root.querySelector('[name="order_date"]')?.value || '',
    deliveryDate: root.querySelector('[name="delivery_date"]')?.value || '',
    notes: root.querySelector('[name="notes"]')?.value || '',
    quantity: articles.reduce((sum, article) => sum + article.quantity, 0),
    value: articles.reduce((sum, article) => sum + article.value, 0),
  };
}

function orderEmailText(data, message = '') {
  const articles = data.articles.map(article => {
    const variants = article.rows.flatMap(row => row.quantities.map(item => `${row.color} / ${item.size}: ${number(item.quantity)}`)).join(', ');
    return `- ${article.reference}${article.description ? ` · ${article.description}` : ''}: ${number(article.quantity)} peças${variants ? ` (${variants})` : ''}`;
  }).join('\n');
  return `${message.trim()}\n\nNota de encomenda ${data.orderNo}\nCliente: ${data.customer?.name || '—'}\nPO cliente: ${data.customerPo || '—'}\nData: ${data.orderDate ? date(data.orderDate) : '—'}\nEntrega: ${data.deliveryDate ? date(data.deliveryDate) : '—'}\n\nArtigos\n${articles || '- Sem quantidades registadas'}\n\nTotal: ${number(data.quantity)} peças · ${orderMoney(data.value, data.currency)}${data.notes ? `\n\nNotas: ${data.notes}` : ''}`.trim();
}

function orderEmailHtml(data, message = '') {
  const articleRows = data.articles.map(article => {
    const variants = article.rows.flatMap(row => row.quantities.map(item => `${row.color} / ${item.size}: ${number(item.quantity)}`)).join(' · ');
    return `<tr><td style="padding:12px;border-bottom:1px solid #e2e8f0"><b>${esc(article.reference)}</b><br><span style="color:#64748b">${esc(article.description)}</span>${variants ? `<br><small style="color:#64748b">${esc(variants)}</small>` : ''}</td><td style="padding:12px;border-bottom:1px solid #e2e8f0">${esc(number(article.quantity))}</td><td style="padding:12px;border-bottom:1px solid #e2e8f0;text-align:right"><b>${esc(orderMoney(article.value, data.currency))}</b></td></tr>`;
  }).join('');
  return `<div style="font-family:Arial,sans-serif;max-width:720px;color:#172033"><p>${esc(message).replace(/\n/g, '<br>')}</p><div style="margin:24px 0;padding:20px;border-radius:12px;background:#122548;color:#fff"><small style="letter-spacing:.12em">NOTA DE ENCOMENDA</small><h1 style="margin:6px 0 4px">${esc(data.orderNo)}</h1><span>${esc(data.customer?.name || '')}</span></div><table style="width:100%;border-collapse:collapse"><tr><td><small>PO CLIENTE</small><br><b>${esc(data.customerPo || '—')}</b></td><td><small>DATA</small><br><b>${esc(data.orderDate ? date(data.orderDate) : '—')}</b></td><td><small>ENTREGA</small><br><b>${esc(data.deliveryDate ? date(data.deliveryDate) : '—')}</b></td></tr></table><table style="width:100%;margin-top:24px;border-collapse:collapse"><thead><tr style="background:#f1f5f9"><th style="padding:10px;text-align:left">Artigo</th><th style="padding:10px;text-align:left">Peças</th><th style="padding:10px;text-align:right">Subtotal</th></tr></thead><tbody>${articleRows || '<tr><td colspan="3" style="padding:16px">Sem quantidades registadas.</td></tr>'}</tbody><tfoot><tr><td style="padding:16px 12px"><b>Total</b></td><td style="padding:16px 12px"><b>${esc(number(data.quantity))}</b></td><td style="padding:16px 12px;text-align:right;font-size:18px"><b>${esc(orderMoney(data.value, data.currency))}</b></td></tr></tfoot></table>${data.notes ? `<div style="margin-top:20px;padding:14px;background:#f8fafc"><b>Notas</b><p>${esc(data.notes).replace(/\n/g, '<br>')}</p></div>` : ''}</div>`;
}

function printValue(value, fallback = 'Por indicar') {
  const normalized = String(value ?? '').trim();
  return esc(normalized || fallback);
}

function orderPrintMarkup(root, blocks, styles, customers) {
  const data = orderCommunicationData(root, blocks, styles, customers);
  const customer = data.customer || {};
  const currency = data.currency || 'EUR';
  const status = root.querySelector('[name="status"]')?.value || 'draft';
  const paymentTerms = root.querySelector('[name="payment_terms"]')?.value || '';
  const incoterm = root.querySelector('[name="incoterm"]')?.value || '';
  const transportValue = root.querySelector('[name="transport"]')?.value || '';
  const deliveryAddress = root.querySelector('[name="delivery_address"]')?.value || '';
  const transportLabels = {
    customer: 'A cargo do cliente', factory: 'Organizado pela fábrica', carrier: 'Transportadora acordada',
  };
  const vatRate = Math.max(0, Number(root.dataset.vatRate) || 0);
  const vatValue = data.value * vatRate / 100;
  const totalValue = data.value + vatValue;
  const companyName = document.querySelector('[data-company-name], .company-card-name, #company-card-name')?.textContent?.trim() || 'TextileFlow';

  const articleMarkup = blocks.map((block, articleIndex) => {
    const style = styles.find(row => String(row.id) === String(block.styleId));
    const sizes = block.gradeState.sizes.length ? block.gradeState.sizes : ['Único'];
    const rows = block.gradeState.rows;
    const sizeTotals = sizes.map(size => rows.reduce((sum, row) => sum + (Number(row.qty[size]) || 0), 0));
    const articleQuantity = sizeTotals.reduce((sum, value) => sum + value, 0);
    const articleValue = rows.reduce((sum, row) => {
      const quantity = sizes.reduce((qty, size) => qty + (Number(row.qty[size]) || 0), 0);
      return sum + quantity * (Number(row.price) || 0);
    }, 0);
    const averagePrice = articleQuantity ? articleValue / articleQuantity : 0;
    const bodyRows = rows.length ? rows.map(row => {
      const rowTotal = sizes.reduce((sum, size) => sum + (Number(row.qty[size]) || 0), 0);
      return `<tr>
        <td class="print-grade-color"><span class="print-color-swatch" style="background:${colorSwatch(row.color)}"></span>${printValue(gradeLabel(row.color, 'color'))}</td>
        <td class="print-grade-price">${esc(orderMoney(Number(row.price) || 0, currency))}</td>
        ${sizes.map(size => `<td>${esc(number(Number(row.qty[size]) || 0))}</td>`).join('')}
        <td class="print-grade-total">${esc(number(rowTotal))}</td>
      </tr>`;
    }).join('') : `<tr><td colspan="${sizes.length + 3}" class="print-empty-grade">Sem cores ou quantidades registadas.</td></tr>`;
    return `<article class="print-order-article">
      <header class="print-article-header">
        <span class="print-article-number">${String(articleIndex + 1).padStart(2, '0')}</span>
        <div class="print-article-title"><b>${printValue(style?.reference, 'Artigo por selecionar')}</b><span>${printValue(style?.description, 'Sem descrição')}</span></div>
        <div class="print-article-stat"><span>Peças</span><b>${esc(number(articleQuantity))} un.</b></div>
        <div class="print-article-stat"><span>Preço médio</span><b>${esc(orderMoney(averagePrice, currency))}</b></div>
      </header>
      <table class="print-grade-table">
        <thead><tr><th>Cor</th><th>Preço / un.</th>${sizes.map(size => `<th>${printValue(gradeLabel(size, 'size'))}</th>`).join('')}<th>Total</th></tr></thead>
        <tbody>${bodyRows}</tbody>
        <tfoot><tr><th colspan="2">Total por tamanho</th>${sizeTotals.map(value => `<th>${esc(number(value))}</th>`).join('')}<th>${esc(number(articleQuantity))}</th></tr></tfoot>
      </table>
    </article>`;
  }).join('');

  return `<section class="sales-order-print-sheet" aria-label="Nota de encomenda para impressão">
    <header class="print-document-header">
      <div class="print-document-brand"><span>${printValue(companyName, 'TextileFlow')}</span><small>Documento comercial</small></div>
      <div class="print-document-title"><small>NOTA DE ENCOMENDA</small><h1>${printValue(data.orderNo, 'Nova encomenda')}</h1></div>
      <span class="print-document-status">${printValue(STATUS_LABELS[status] || status, 'Rascunho')}</span>
    </header>
    <section class="print-customer-strip">
      <div><span>Cliente</span><b>${printValue(customer.name, 'Por selecionar')}</b><small>${printValue(customer.tax_id || customer.vat_number || customer.nif, '')}</small></div>
      <div><span>PO / Encomenda do cliente</span><b>${printValue(data.customerPo)}</b></div>
      <div><span>Data da encomenda</span><b>${data.orderDate ? esc(date(data.orderDate)) : 'Por indicar'}</b></div>
      <div><span>Data de entrega</span><b>${data.deliveryDate ? esc(date(data.deliveryDate)) : 'Por indicar'}</b></div>
      <div class="print-total-highlight"><span>Valor total</span><b>${esc(orderMoney(totalValue, currency))}</b><small>${vatRate ? 'com IVA' : 'sem IVA'}</small></div>
    </section>
    <section class="print-document-section print-commercial-section">
      <h2><span>1</span>Dados comerciais</h2>
      <div class="print-commercial-grid">
        <div><span>Condição de pagamento</span><b>${printValue(paymentTerms)}</b></div>
        <div><span>Incoterm</span><b>${printValue(incoterm)}</b></div>
        <div><span>Transporte</span><b>${printValue(transportLabels[transportValue] || transportValue)}</b></div>
        <div><span>Moeda</span><b>${printValue(currency)}</b></div>
        <div class="print-wide-field"><span>Morada de entrega</span><b>${printValue(deliveryAddress)}</b></div>
        ${data.notes ? `<div class="print-wide-field print-notes"><span>Notas e instruções comerciais</span><p>${esc(data.notes).replace(/\n/g, '<br>')}</p></div>` : ''}
      </div>
    </section>
    <section class="print-document-section print-articles-section">
      <h2><span>2</span>Artigos da encomenda</h2>
      <div class="print-articles-list">${articleMarkup || '<p class="print-empty-grade">Sem artigos registados.</p>'}</div>
    </section>
    <footer class="print-order-summary">
      <div class="print-summary-title"><span>Resumo da encomenda</span><small>${printValue(data.orderNo, '')}</small></div>
      <div><span>N.º de artigos</span><b>${esc(number(blocks.length))}</b></div>
      <div><span>Total de peças</span><b>${esc(number(data.quantity))} un.</b></div>
      <div><span>Mercadoria (sem IVA)</span><b>${esc(orderMoney(data.value, currency))}</b></div>
      <div><span>IVA (${esc(number(vatRate))}%)</span><b>${esc(orderMoney(vatValue, currency))}</b></div>
      <div class="print-summary-total"><span>Valor total</span><b>${esc(orderMoney(totalValue, currency))}</b></div>
    </footer>
  </section>`;
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
        <td><span class="badge blue">${esc(STATUS_LABELS[row.status] || row.status)}</span></td>
        <td class="listing-actions"><div class="row-actions">
          ${['draft','confirmed'].includes(row.status) ? `<button class="btn icon" type="button" data-icon="edit" data-edit-order="${row.id}" aria-label="Editar" title="Editar"></button><button class="btn icon primary" type="button" data-icon="production" data-release-order="${row.id}" aria-label="Lançar em produção" title="Lançar em produção"></button><button class="btn icon danger" type="button" data-icon="delete" data-delete-order="${row.id}" aria-label="Eliminar" title="Eliminar"></button>` : ''}
        </div></td>
      </tr>`).join('') : `<tr><td colspan="7">${empty('Sem encomendas', 'Crie a primeira encomenda de cliente.')}</td></tr>`}</tbody></table></div></section>`;

  panel.querySelector('[data-new-order]').addEventListener('click', () => renderSalesOrderEditor(panel, null));
  panel.querySelectorAll('[data-edit-order]').forEach(button => button.addEventListener('click', () => renderSalesOrderEditor(panel, Number(button.dataset.editOrder))));
  panel.querySelectorAll('[data-release-order]').forEach(button => button.addEventListener('click', async () => {
    button.disabled = true;
    try {
      const result = await post(`/production/sales-orders/${button.dataset.releaseOrder}/release`, {});
      toast(`${result.created.length} ordem(ns) de fabrico criada(s).`);
      await renderSalesOrders(panel);
    } catch (error) { button.disabled = false; toast(error.message, 'error'); }
  }));
  panel.querySelectorAll('[data-delete-order]').forEach(button => button.addEventListener('click', async () => {
    if (!confirmDelete('esta encomenda')) return;
    try { await crudDelete('sales-orders', Number(button.dataset.deleteOrder), state.companyId); toast('Encomenda eliminada.'); await renderSalesOrders(panel); }
    catch (error) { toast(error.message, 'error'); }
  }));
}

export async function renderSalesOrderEditor(panel, orderId) {
  const [customers, styles, paymentTerms, costSheets, autoOrderNo] = await Promise.all([
    crudList('customers', state.companyId),
    crudList('styles', state.companyId),
    crudList('payment-terms', state.companyId).catch(() => []),
    crudList('cost-sheets', state.companyId).catch(() => []),
    orderId ? Promise.resolve('') : get(`/production/${state.companyId}/next-number?key=sales_order&prefix=${encodeURIComponent(`ENC-${new Date().getFullYear()}-`)}&width=5`).then(r => r.number).catch(() => ''),
  ]);
  let order = { order_no: autoOrderNo, customer_id: '', customer_po: '', order_date: new Date().toISOString().slice(0, 10), delivery_date: '', status: 'confirmed', currency: 'EUR', notes: '' };
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
        const color = variant?.color || 'Sem cor';
        const size = variant?.size || 'Único';
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
  const initialCustomer = customers.find(row => String(row.id) === String(order.customer_id));
  const commercial = order.custom_data || {};
  const linkedSheetId = commercial.cost_sheet_id || commercial.approved_cost_sheet_id;
  const linkedSheet = costSheets.find(row => String(row.id) === String(linkedSheetId));
  const proposalReference = commercial.proposal_reference || linkedSheet?.custom_data?.quote_no || '';
  const paymentTermsValue = commercial.payment_terms || initialCustomer?.payment_terms || initialCustomer?.payment_term_code || '';
  const deliveryAddress = commercial.delivery_address || [initialCustomer?.address, [initialCustomer?.postal_code, initialCustomer?.city].filter(Boolean).join(' '), initialCustomer?.country].filter(Boolean).join(', ');
  const vatRate = Number(commercial.vat_rate ?? 0) || 0;
  const vatLabel = commercial.vat_label || 'Exportação';

  panel.innerHTML = `<div class="release-order-page" data-vat-rate="${vatRate}" data-vat-label="${esc(vatLabel)}">
    <header class="release-order-header">
      <button type="button" class="btn icon release-order-back" data-icon="back" data-back-order aria-label="Voltar às encomendas sem guardar" title="Voltar às encomendas sem guardar"></button>
      <div class="release-order-heading">
        <span class="release-order-eyebrow">Nota de Encomenda</span>
        <div><h1>${esc(order.order_no || 'Nova encomenda')}</h1><span class="release-order-status-chip" data-order-status>${esc(STATUS_LABELS[order.status] || order.status)}</span></div>
        <p>Cliente: <b data-order-customer-name>${esc(initialCustomer?.name || 'Por selecionar')}</b><span aria-hidden="true">|</span><span>Proposta origem: <b>${esc(proposalReference || 'Sem proposta')}</b></span></p>
      </div>
      <div class="release-order-actions">
        <button type="button" class="btn release-order-output" data-print-order><span data-icon="print" aria-hidden="true"></span><span>PDF / Imprimir</span></button>
        <button type="button" class="btn release-order-output" data-email-order><span data-icon="mail" aria-hidden="true"></span><span>Enviar por email</span></button>
        <button type="button" class="btn release-save-button" data-submit-order><span data-icon="save" aria-hidden="true"></span>${orderId ? 'Guardar' : 'Criar encomenda'}</button>
        <button type="button" class="btn primary release-production-button" data-release-order-editor><span data-icon="production" aria-hidden="true"></span>Lançar em Produção</button>
      </div>
    </header>

    <section class="release-order-facts" aria-label="Resumo comercial">
      <div><span data-icon="inbox" aria-hidden="true"></span><small>PO / Encomenda cliente</small><b data-order-po>${esc(order.customer_po || 'Por indicar')}</b></div>
      <div><span data-icon="clock" aria-hidden="true"></span><small>Data da encomenda</small><b data-order-date>${order.order_date ? date(order.order_date) : '—'}</b></div>
      <div><span data-icon="clock" aria-hidden="true"></span><small>Data de entrega</small><b data-order-delivery>${order.delivery_date ? date(order.delivery_date) : '—'}</b></div>
      <div><small>Estado</small><b class="release-fact-status" data-order-fact-status>${esc(STATUS_LABELS[order.status] || order.status)}</b></div>
      <div><span data-icon="euro" aria-hidden="true"></span><small>Moeda</small><b data-order-currency>${esc(order.currency || 'EUR')}</b></div>
      <div class="release-order-fact-total"><small>Valor total (sem IVA)</small><b data-order-total>0,00 €</b></div>
    </section>

    <section class="card release-order-card">
      <div class="card-header release-order-section-heading"><span class="release-section-number">1</span><h2>Dados comerciais</h2></div>
      <div class="release-order-fields">
        <input type="hidden" name="order_no" value="${esc(order.order_no || '')}"><select name="status" hidden>${Object.entries(EDITABLE_STATUS_LABELS).map(([value, label]) => `<option value="${value}" ${value === order.status ? 'selected' : ''}>${esc(label)}</option>`).join('')}</select>
        <label class="field-customer">Cliente *<select name="customer_id" required><option value="">Selecionar cliente…</option>${customers.map(row => `<option value="${row.id}" ${String(row.id) === String(order.customer_id) ? 'selected' : ''}>${esc(row.name)}</option>`).join('')}</select></label>
        <label class="field-customer-po">Referência da encomenda do cliente<input name="customer_po" value="${esc(order.customer_po || '')}" placeholder="PO do cliente"></label>
        <label class="field-order-date">Data da encomenda *<input type="date" name="order_date" value="${order.order_date || ''}"></label>
        <label class="field-delivery-date">Data de entrega *<input type="date" name="delivery_date" value="${order.delivery_date || ''}"></label>
        <label class="field-currency">Moeda *<select name="currency">${['EUR','USD','GBP','CHF'].map(value => `<option ${value === (order.currency || 'EUR') ? 'selected' : ''}>${value}</option>`).join('')}</select></label>
        <label class="field-payment">Condição de pagamento<select name="payment_terms"><option value="">Por definir</option>${paymentTermsValue && !paymentTerms.some(row => [row.code,row.name].includes(paymentTermsValue)) ? `<option selected>${esc(paymentTermsValue)}</option>` : ''}${paymentTerms.map(row => `<option value="${esc(row.name || row.code)}" ${[row.code,row.name].includes(paymentTermsValue) ? 'selected' : ''}>${esc(row.name || row.code)}</option>`).join('')}</select></label>
        <label class="field-incoterm">Incoterm<select name="incoterm">${['EXW','FCA','FOB','CIF','DAP','DDP'].map(value => `<option ${value === (commercial.incoterm || 'DAP') ? 'selected' : ''}>${value}</option>`).join('')}</select></label>
        <label class="field-transport">Transporte<select name="transport"><option value="customer" ${commercial.transport === 'customer' || !commercial.transport ? 'selected' : ''}>A cargo do cliente</option><option value="factory" ${commercial.transport === 'factory' ? 'selected' : ''}>Organizado pela fábrica</option><option value="carrier" ${commercial.transport === 'carrier' ? 'selected' : ''}>Transportadora acordada</option></select></label>
        <label class="field-delivery-address">Morada de entrega<input name="delivery_address" value="${esc(deliveryAddress)}" placeholder="Morada completa de entrega"></label>
        <label class="full field-notes">Notas e instruções comerciais<textarea name="notes" placeholder="Condições acordadas, instruções de embalagem, observações de entrega…">${esc(order.notes || '')}</textarea></label>
      </div>
    </section>

    <section class="card release-order-articles-shell"><div class="card-header release-order-section-heading"><span class="release-section-number">2</span><h2>Artigos da encomenda</h2></div><div data-articles-list></div><button type="button" class="btn release-order-add-article" data-add-article><span data-icon="add" aria-hidden="true"></span>Adicionar artigo</button></section>

    <aside class="card release-order-summary-card">
      <div class="release-summary-heading"><span data-icon="document" aria-hidden="true"></span><h3>Resumo da encomenda</h3></div>
      <div class="release-summary-metric"><span>N.º de artigos</span><b data-summary-articles>0</b></div>
      <div class="release-summary-metric"><span>Total de peças</span><b><span data-summary-pieces>0</span> un.</b></div>
      <div class="release-summary-metric"><span>Valor mercadoria (sem IVA)</span><b data-summary-merchandise>0,00 €</b></div>
      <div class="release-summary-metric"><span>IVA <small data-summary-vat-label></small></span><b data-summary-vat>0,00 €</b></div>
      <div class="release-summary-metric total"><span>Valor total (sem IVA)</span><b data-summary-value>0,00 €</b></div>
    </aside>

    <div class="sales-order-print-host" data-order-print-host aria-hidden="true"></div>
  </div>`;

  const root = panel.querySelector('.release-order-page');
  const articlesList = root.querySelector('[data-articles-list]');

  function paintArticles() {
    articlesList.innerHTML = blocks.map(block => articleBlockHtml(block, styles)).join('');
    blocks.forEach(block => renderBlockGrid(root, block));
    updateOrderTotals(root, blocks);
  }
  paintArticles();

  function refreshHeaderMeta() {
    const customerId = root.querySelector('[name="customer_id"]')?.value;
    const customer = customers.find(row => String(row.id) === String(customerId));
    const customerPo = root.querySelector('[name="customer_po"]')?.value.trim();
    const status = root.querySelector('[name="status"]')?.value;
    const orderDate = root.querySelector('[name="order_date"]')?.value;
    const deliveryDate = root.querySelector('[name="delivery_date"]')?.value;
    const currency = root.querySelector('[name="currency"]')?.value || 'EUR';
    root.querySelector('[data-order-customer-name]').textContent = customer?.name || 'Por selecionar';
    root.querySelector('[data-order-po]').textContent = customerPo || 'Por indicar';
    root.querySelector('[data-order-status]').textContent = STATUS_LABELS[status] || status || 'Sem estado';
    root.querySelector('[data-order-fact-status]').textContent = STATUS_LABELS[status] || status || 'Sem estado';
    root.querySelector('[data-order-date]').textContent = orderDate ? date(orderDate) : '—';
    root.querySelector('[data-order-delivery]').textContent = deliveryDate ? date(deliveryDate) : '—';
    root.querySelector('[data-order-currency]').textContent = currency;
  }

  async function openOrderEmailComposer() {
    const data = orderCommunicationData(root, blocks, styles, customers);
    let accounts = [];
    try {
      const response = await get(`/mailbox/${state.companyId}/accounts`);
      accounts = (response.items || []).filter(account => account.can_send);
    } catch { /* O cliente de email continua disponível como alternativa. */ }
    const hasSmtp = accounts.length > 0;
    const recipient = data.customer?.email || '';
    const subject = `Nota de encomenda ${data.orderNo}${data.customerPo ? ` · PO ${data.customerPo}` : ''}`;
    openModal('Enviar nota de encomenda', `<form class="order-email-form" data-order-email-form>
      <div class="order-email-intro"><span data-icon="mail" aria-hidden="true"></span><div><b>${hasSmtp ? 'Envio direto pelo TextileFlow' : 'Preparar mensagem no seu email'}</b><p>${hasSmtp ? 'A nota segue no corpo do email com o resumo comercial atualizado.' : 'Não existe uma conta SMTP pronta para envio. Será aberto o programa de email do dispositivo.'}</p></div></div>
      ${hasSmtp ? `<label class="field">Conta de envio<select name="account_id">${accounts.map(account => `<option value="${account.id}">${esc(account.label || account.email)} · ${esc(account.email)}</option>`).join('')}</select></label>` : ''}
      <div class="form-grid two"><label class="field">Destinatário *<input type="email" name="to" required value="${esc(recipient)}" placeholder="cliente@empresa.pt"></label><label class="field">Assunto *<input name="subject" required value="${esc(subject)}"></label></div>
      <label class="field">Mensagem<textarea name="message" rows="6">Exmos. Senhores,

Segue a nota de encomenda ${esc(data.orderNo)} para vossa confirmação.

Com os melhores cumprimentos,</textarea></label>
      <div class="order-email-note"><span data-icon="print" aria-hidden="true"></span><span>Para anexar um ficheiro, use primeiro <b>PDF / Imprimir</b>, guarde o PDF e anexe-o à mensagem. O resumo completo já segue no corpo do email.</span></div>
      <div class="form-footer"><button type="button" class="btn" data-close-order-email>Cancelar</button><button type="submit" class="btn primary" data-send-order-email><span data-icon="mail" aria-hidden="true"></span>${hasSmtp ? 'Enviar agora' : 'Abrir no email'}</button></div>
    </form>`, `${data.customer?.name || 'Cliente por selecionar'} · ${data.orderNo}`);
    const form = document.querySelector('[data-order-email-form]');
    form.querySelector('[data-close-order-email]').addEventListener('click', closeModal);
    form.addEventListener('submit', async event => {
      event.preventDefault();
      const button = form.querySelector('[data-send-order-email]');
      const to = form.elements.to.value.trim();
      const currentSubject = form.elements.subject.value.trim();
      const message = form.elements.message.value.trim();
      if (!to || !currentSubject) { toast('Indique o destinatário e o assunto.', 'error'); return; }
      const currentData = orderCommunicationData(root, blocks, styles, customers);
      if (!hasSmtp) {
        location.href = `mailto:${encodeURIComponent(to)}?subject=${encodeURIComponent(currentSubject)}&body=${encodeURIComponent(orderEmailText(currentData, message))}`;
        closeModal();
        return;
      }
      button.disabled = true;
      button.textContent = 'A enviar…';
      try {
        await post(`/mailbox/${state.companyId}/accounts/${form.elements.account_id.value}/send`, {
          to, subject: currentSubject, body: orderEmailText(currentData, message), html: orderEmailHtml(currentData, message),
        });
        closeModal();
        toast(`Nota de encomenda enviada para ${to}.`);
      } catch (error) {
        button.disabled = false;
        button.innerHTML = '<span data-icon="mail" aria-hidden="true"></span>Enviar agora';
        toast(error.message, 'error');
      }
    });
  }

  function findBlock(el) {
    const scope = el.closest('[data-article-block]');
    return scope ? blocks.find(b => b.id === scope.dataset.blockId) : null;
  }

  root.addEventListener('input', async event => {
    if (event.target.matches('[name="customer_id"]')) {
      const customer = customers.find(row => String(row.id) === String(event.target.value));
      const payment = customer?.payment_terms || customer?.payment_term_code || '';
      const paymentSelect = root.querySelector('[name="payment_terms"]');
      if (payment && ![...paymentSelect.options].some(option => option.value === payment)) paymentSelect.add(new Option(payment, payment));
      paymentSelect.value = payment;
      root.querySelector('[name="delivery_address"]').value = [customer?.address, [customer?.postal_code, customer?.city].filter(Boolean).join(' '), customer?.country].filter(Boolean).join(', ');
    }
    if (event.target.matches('[name="customer_id"],[name="customer_po"],[name="order_date"],[name="delivery_date"],[name="status"],[name="currency"]')) refreshHeaderMeta();
    if (event.target.matches('[name="currency"]')) {
      blocks.forEach(block => renderBlockGrid(root, block));
      updateOrderTotals(root, blocks);
      return;
    }
    const styleSelect = event.target.closest('[data-style-select]');
    if (styleSelect) {
      const block = findBlock(styleSelect);
      if (block) {
        block.styleId = styleSelect.value ? Number(styleSelect.value) : '';
        const style = styles.find(row => String(row.id) === String(block.styleId));
        styleSelect.closest('[data-article-block]')?.querySelector('[data-style-reference]')?.replaceChildren(document.createTextNode(style?.reference || 'por definir'));
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

  function addColor(block) {
    const scope = root.querySelector(`[data-article-block][data-block-id="${block.id}"]`);
    const input = scope.querySelector('[data-new-color]');
    const value = input.value.trim();
    if (!value) { toast('Indique o nome da cor.', 'error'); return; }
    if (block.gradeState.rows.some(row => row.color.toLocaleLowerCase('pt') === value.toLocaleLowerCase('pt'))) { toast('Essa cor já está na grelha.', 'error'); return; }
    block.gradeState.rows.push({ id: uid(), color: value, price: 0, qty: {} });
    input.value = '';
    scope.querySelector('[data-color-add-panel]').hidden = true;
    scope.querySelector('[data-toggle-color-add]').hidden = false;
    renderBlockGrid(root, block); updateOrderTotals(root, blocks);
  }

  function addSize(block) {
    const scope = root.querySelector(`[data-article-block][data-block-id="${block.id}"]`);
    const input = scope.querySelector('[data-new-size]');
    const value = input.value.trim();
    if (!value) { toast('Indique o tamanho.', 'error'); return; }
    if (block.gradeState.sizes.some(size => size.toLocaleLowerCase('pt') === value.toLocaleLowerCase('pt'))) { toast('Esse tamanho já está na grelha.', 'error'); return; }
    block.gradeState.sizes.push(value);
    input.value = '';
    scope.querySelector('[data-size-add-panel]').hidden = true;
    scope.querySelector('[data-toggle-size-add]').hidden = false;
    renderBlockGrid(root, block); updateOrderTotals(root, blocks);
  }

  root.addEventListener('keydown', event => {
    if (event.key !== 'Enter') return;
    const newColor = event.target.closest('[data-new-color]');
    const newSize = event.target.closest('[data-new-size]');
    if (newColor) { event.preventDefault(); const block = findBlock(newColor); if (block) addColor(block); }
    else if (newSize) { event.preventDefault(); const block = findBlock(newSize); if (block) addSize(block); }
  });

  root.addEventListener('click', async event => {
    if (event.target.closest('[data-back-order]') || event.target.closest('[data-cancel-order]')) {
      await renderSalesOrders(panel);
      return;
    }
    if (event.target.closest('[data-print-order]')) {
      refreshHeaderMeta();
      const previousTitle = document.title;
      document.title = `Nota de encomenda ${root.querySelector('[name="order_no"]')?.value || ''}`.trim();
      const printHost = root.querySelector('[data-order-print-host]');
      printHost.innerHTML = orderPrintMarkup(root, blocks, styles, customers);
      printHost.setAttribute('aria-hidden', 'false');
      const chrome = [...document.querySelectorAll('#app-shell > .topbar, #app-shell > .sidebar, .module-tabs, .tabs')];
      const chromeDisplay = chrome.map(element => [element, element.style.getPropertyValue('display'), element.style.getPropertyPriority('display')]);
      chrome.forEach(element => element.style.setProperty('display', 'none', 'important'));
      document.body.classList.add('printing-sales-order');
      try { window.print(); }
      finally {
        document.body.classList.remove('printing-sales-order');
        chromeDisplay.forEach(([element, value, priority]) => {
          if (value) element.style.setProperty('display', value, priority);
          else element.style.removeProperty('display');
        });
        printHost.replaceChildren();
        printHost.setAttribute('aria-hidden', 'true');
        document.title = previousTitle;
      }
      return;
    }
    if (event.target.closest('[data-email-order]')) {
      await openOrderEmailComposer();
      return;
    }
    const releaseButton = event.target.closest('[data-release-order-editor]');
    if (releaseButton) {
      await submit(releaseButton, true);
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
    const duplicateArticle = event.target.closest('[data-duplicate-article]');
    if (duplicateArticle) {
      const source = findBlock(duplicateArticle);
      const sourceIndex = blocks.findIndex(item => item.id === source?.id);
      if (sourceIndex >= 0) {
        blocks.splice(sourceIndex + 1, 0, {
          ...source, id: uid(), removable: true, lineIdByVariant: {},
          gradeState: { sizes: [...source.gradeState.sizes], rows: source.gradeState.rows.map(row => ({ ...row, id: uid(), qty: { ...row.qty } })) },
        });
        blocks.forEach((item, index) => { item.index = index + 1; });
        paintArticles();
        toast('Artigo duplicado.');
      }
      return;
    }
    const block = findBlock(event.target);
    if (!block) {
      if (event.target.closest('[data-submit-order]')) await submit(event.target.closest('[data-submit-order]'));
      return;
    }
    const colorToggle = event.target.closest('[data-toggle-color-add]');
    if (colorToggle) {
      colorToggle.hidden = true;
      const panel = colorToggle.nextElementSibling;
      panel.hidden = false;
      panel.querySelector('input').focus();
      return;
    }
    const sizeToggle = event.target.closest('[data-toggle-size-add]');
    if (sizeToggle) {
      sizeToggle.hidden = true;
      const panel = sizeToggle.nextElementSibling;
      panel.hidden = false;
      panel.querySelector('input').focus();
      return;
    }
    if (event.target.closest('[data-add-color]')) { addColor(block); return; }
    if (event.target.closest('[data-add-size]')) { addSize(block); return; }
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
      return;
    }
    const calcButton = event.target.closest('[data-calc-requirements]');
    if (calcButton) {
      if (!block.styleId) { toast('Escolha primeiro o modelo/artigo.', 'error'); return; }
      const totalQty = blockTotalQty(block);
      if (totalQty <= 0) { toast('Indique quantidades na grelha antes de calcular.', 'error'); return; }
      const scope = root.querySelector(`[data-article-block][data-block-id="${block.id}"]`);
      const requirementsPanel = scope.querySelector('[data-requirements]');
      requirementsPanel.innerHTML = '<div class="loading">A calcular necessidade de material…</div>';
      try {
        const data = await get(`/products/styles/${block.styleId}/material-requirements?quantity=${totalQty}`);
        requirementsPanel.innerHTML = requirementsHtml(data);
      } catch (error) {
        requirementsPanel.innerHTML = `<p class="muted requirement-empty">${esc(error.message)}</p>`;
      }
    }
  });

  async function submit(button, releaseAfter = false) {
    const orderNo = root.querySelector('input[name="order_no"]').value.trim();
    const customerId = Number(root.querySelector('select[name="customer_id"]').value || 0);
    if (!orderNo) { toast('Número interno em falta — recarregue a página.', 'error'); return; }
    if (!customerId) { toast('Escolha o cliente.', 'error'); return; }
    for (const block of blocks) {
      if (!block.styleId) { toast(`Escolha o modelo/artigo do artigo ${block.index}.`, 'error'); return; }
    }
    button.disabled = true;
    button.textContent = releaseAfter ? 'A preparar produção…' : 'A guardar…';
    try {
      const headerPayload = {
        company_id: state.companyId,
        customer_id: customerId,
        order_no: orderNo,
        customer_po: root.querySelector('input[name="customer_po"]').value || null,
        order_date: root.querySelector('input[name="order_date"]').value || null,
        delivery_date: root.querySelector('input[name="delivery_date"]').value || null,
        status: root.querySelector('select[name="status"]').value,
        currency: root.querySelector('[name="currency"]').value || 'EUR',
        notes: root.querySelector('textarea[name="notes"]').value || null,
        custom_data: {
          payment_terms: root.querySelector('[name="payment_terms"]').value || null,
          incoterm: root.querySelector('[name="incoterm"]').value || null,
          transport: root.querySelector('[name="transport"]').value || null,
          delivery_address: root.querySelector('[name="delivery_address"]').value || null,
          vat_rate: Number(root.dataset.vatRate) || 0,
          vat_label: root.dataset.vatLabel || null,
        },
      };
      const items = [];
      for (const block of blocks) {
        for (const row of block.gradeState.rows) {
          const color = (row.color || '').trim();
          for (const size of block.gradeState.sizes) {
            const quantity = Number(row.qty[size]) || 0;
            if (quantity <= 0) continue;
            if (!color) { throw new Error(`Todas as linhas com quantidade têm de ter uma cor (artigo ${block.index}).`); }
            items.push({ style_id: block.styleId, color, size, quantity, unit_price: row.price || 0 });
          }
        }
      }
      if (!items.length) throw new Error('Indique pelo menos uma quantidade na grade.');
      const saved = await post('/production/sales-orders/save', { id: orderId || null, company_id: state.companyId, header: headerPayload, items });
      if (releaseAfter) {
        const result = await post(`/production/sales-orders/${saved.order.id}/release`, {});
        toast(`${result.created.length} ordem(ns) de fabrico criada(s).`);
      } else {
        toast(orderId ? 'Encomenda e grade atualizadas.' : 'Encomenda criada. Pode agora lançá-la em produção.');
      }
      await renderSalesOrders(panel);
    } catch (error) {
      button.disabled = false;
      button.textContent = releaseAfter ? 'Lançar em Produção' : (orderId ? 'Guardar alterações' : 'Criar encomenda');
      toast(error.message, 'error');
    }
  }
}
