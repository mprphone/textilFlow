import { get, post, put } from '../api.js';
import { options } from '../data.js';
import { badge, date, esc, money, number } from '../format.js?v=20260819-5';
import { CIVA, f4Field, openF4 } from '../primavera_lookup.js?v=20260821-10';
import { recordModal } from '../quick_create.js?v=20260820-5';
import { state } from '../state.js';
import { pageHeader, setHeading, toast } from '../ui.js?v=20260820-5';

const CONVERT_LABEL = {
  purchase_invoice:'Fatura de compra',
  supplier_transport:'Guia ao fornecedor',
  stock_receipt:'Entrada de stock',
  fabric_issue:'Saída de malha',
  purchase_credit:'Nota de crédito',
  purchase_debit:'Nota de débito',
  sales_invoice:'Fatura de venda',
  sales_credit:'Nota de crédito',
  sales_debit:'Nota de débito',
};

let listState = { family: '', doc_type: '', series: '', query: '' };

function erpName() {
  return state.companies.find(row => Number(row.id) === Number(state.companyId))?.erp_label || 'Primavera';
}

function typesInFamily(catalog, family) {
  const types = catalog.types || catalog.legacy || [];
  if (!family) return types;
  return types.filter(item => (item.families || []).includes(family));
}

export async function render(container) {
  const catalog = await get(`/erp/${state.companyId}/documents/types`);
  const params = new URLSearchParams();
  if (listState.family) params.set('family', listState.family);
  if (listState.doc_type) params.set('doc_type', listState.doc_type);
  if (listState.series) params.set('series', listState.series);
  const qs = params.toString();
  const rows = await get(`/erp/${state.companyId}/documents${qs ? `?${qs}` : ''}`);
  const visibleTypes = typesInFamily(catalog, listState.family);
  const query = (listState.query || '').trim().toLowerCase();
  const filtered = rows.filter(row => !query || `${row.doc_no} ${row.erp_code} ${row.series} ${row.partner_name} ${row.type_label}`.toLowerCase().includes(query));
  const queued = filtered.filter(row => ['queued','pending','failed','prepared','alert'].includes(row.primavera_status)).length;
  const system = catalog.label || erpName();
  container.innerHTML = pageHeader(
    `Documentos · ${system}`,
    `Família, depois tipo de documento e série — o hábito do ${system}.`,
    `<a class="btn" href="#/erp-capture">Ler foto / PDF</a><button class="btn" data-from-purchase>A partir da OC</button><button class="btn" data-from-sales>A partir da encomenda</button><button class="btn primary" data-new-doc>+ Novo</button>`
  ) + `
    <div class="tabs pri-families">${(catalog.families || []).map(item => `<button class="tab ${item.id===listState.family?'active':''}" data-family="${item.id}">${esc(item.label)}</button>`).join('')}</div>
    <div class="pri-docbar">
      <label>Documento<select data-doc-type><option value="">Todos os tipos</option>${visibleTypes.map(item => `<option value="${esc(item.id)}" ${listState.doc_type===item.id?'selected':''}>${esc(item.code || item.id)} · ${esc(item.label)}</option>`).join('')}</select></label>
      <label>Série<select data-series><option value="">Todas</option>${(catalog.series || ['A','1']).map(item => `<option value="${esc(item)}" ${listState.series===item?'selected':''}>${esc(item)}</option>`).join('')}</select></label>
      <label>Procurar<input data-query value="${esc(listState.query)}" placeholder="N.º, entidade…"></label>
      <span class="pri-docbar-meta">${filtered.length} docs · ${queued} na ${esc(catalog.queue || 'fila')}</span>
    </div>
    <div class="table-wrap"><table class="data-table"><thead><tr><th>Documento</th><th>Série</th><th>Número</th><th>Entidade</th><th>Data</th><th>Total</th><th>Estado</th><th>${esc(system)}</th><th></th></tr></thead>
    <tbody>${filtered.map(row => `<tr class="track-row" data-open-doc="${row.id}">
      <td><b>${esc(row.erp_code || '')}</b><div class="muted">${esc(row.type_label || '')}</div></td>
      <td>${esc(row.series || '—')}</td>
      <td><b>${esc(row.doc_no)}</b></td>
      <td>${esc(row.partner_name || '—')}</td>
      <td>${date(row.doc_date)}</td>
      <td>${money(row.total)}</td>
      <td>${badge(row.status)}</td>
      <td>${esc(erpStateLabel(row))}</td>
      <td class="listing-actions"><div class="row-actions erp-actions">
        ${row.can_prepare ? `<button class="btn small primary" data-erp-act="prepare" data-id="${row.id}">Enviar para o Primavera</button>` : ''}
        ${!row.official ? (row.can_convert || []).map(kind => `<button class="btn small" data-erp-act="convert" data-kind="${kind}" data-id="${row.id}">${esc(CONVERT_LABEL[kind] || kind)}</button>`).join('') : ''}
      </div></td>
    </tr>`).join('') || `<tr><td colspan="9"><div class="empty"><strong>Sem documentos nesta vista</strong>Escolha tipo e série como no ${esc(system)}.</div></td></tr>`}</tbody></table></div>`;
  container.querySelectorAll('[data-family]').forEach(button => button.addEventListener('click', () => { listState = { ...listState, family: button.dataset.family, doc_type: '' }; render(container); }));
  container.querySelector('[data-doc-type]')?.addEventListener('change', event => { listState.doc_type = event.target.value; render(container); });
  container.querySelector('[data-series]')?.addEventListener('change', event => { listState.series = event.target.value; render(container); });
  container.querySelector('[data-query]')?.addEventListener('keydown', event => { if (event.key === 'Enter') { listState.query = event.target.value; render(container); } });
  container.querySelector('[data-new-doc]').addEventListener('click', () => openCreate(container, catalog));
  container.querySelector('[data-from-purchase]').addEventListener('click', () => openFromPurchase(container, catalog));
  container.querySelector('[data-from-sales]').addEventListener('click', () => openFromSales(container, catalog));
  container.querySelectorAll('[data-open-doc]').forEach(row => row.addEventListener('click', event => {
    if (event.target.closest('[data-erp-act]')) return;
    location.hash = `#/erp-doc/${row.dataset.openDoc}`;
  }));
  container.querySelectorAll('[data-erp-act]').forEach(button => button.addEventListener('click', async event => {
    event.stopPropagation();
    try {
      if (button.dataset.erpAct === 'prepare') {
        await post(`/erp/${state.companyId}/documents/${button.dataset.id}/prepare`);
        toast('Exportado para o Primavera. Termine a emissão nos documentos oficiais.');
      } else {
        const saved = await post(`/erp/${state.companyId}/documents/${button.dataset.id}/convert`, {doc_type: button.dataset.kind, prepare: false});
        if (!toastStockAlerts(saved)) toast('Documento criado em rascunho.');
      }
      await render(container);
    } catch (error) { toast(error.message, 'error'); }
  }));
}

function toastStockAlerts(saved) {
  const alerts = saved?.extra?.fabric_alerts || [];
  if (!alerts.length) return false;
  alerts.forEach(row => toast(row.detail || row.title));
  return true;
}
  if (!row.official) return 'Interno · TextileFlow';
  if (row.locked) return 'Bloqueado · enviado ao Primavera';
  if (row.primavera_done || row.primavera_status === 'sent') return 'Finalizado no Primavera';
  if (row.primavera_queued || ['queued','pending','prepared'].includes(row.primavera_status)) return 'Enviado · a finalizar no Primavera';
  if (row.primavera_status === 'failed' || row.primavera_status === 'alert') return 'Envio falhou';
  return 'Rascunho TextileFlow';
}

function currentRole() {
  const company = state.companies.find(row => Number(row.id) === Number(state.companyId)) || {};
  return company.role || '';
}

function isAdmin() {
  return currentRole() === 'admin';
}

function emptyLine() {
  return {code:'', description:'', warehouse:'', lot:'', vat_code:'23', unit:'UN', quantity:'', unit_price:'', discount_pct:'', barcode:'', material_id:null};
}

function vatRate(code) {
  return (CIVA.find(item => item.code === String(code)) || {rate:23}).rate;
}

function lineAmount(line) {
  const qty = Number(line.quantity || 0);
  const price = Number(line.unit_price != null ? line.unit_price : (line.unit_cost || 0));
  const disc = Number(line.discount_pct || 0);
  return qty * price * (1 - disc / 100);
}

function bindF4(root, catalog, ctx, handlers) {
  const fire = (kind, input) => {
    if (root.closest('.is-locked')) {
      toast('Documento bloqueado. Um administrador tem de desbloquear e justificar.', 'error');
      return;
    }
    openF4({
      kind, catalog, side: ctx.side,
      onPick: row => handlers[kind]?.(row, input),
    });
  };
  root.addEventListener('dblclick', event => {
    const field = event.target.closest('[data-f4-field]');
    if (!field || !root.contains(field)) return;
    fire(field.dataset.f4Field, field);
  });
  root.addEventListener('keydown', event => {
    const field = event.target.closest('[data-f4-field]');
    if (!field || !root.contains(field)) return;
    if (event.key === 'F4' || (event.altKey && event.key === 'ArrowDown')) {
      event.preventDefault();
      fire(field.dataset.f4Field, field);
    }
  });
}

function collectEditor(container) {
  const line = row => ({
    material_id: Number(row.dataset.materialId) || null,
    code: row.querySelector('[data-f4-field="code"]')?.value,
    warehouse: row.querySelector('[data-f4-field="warehouse"]')?.value,
    lot: row.querySelector('[data-col="lot"]')?.value,
    description: row.querySelector('[data-col="description"]')?.value,
    vat_code: row.querySelector('[data-f4-field="vat_code"]')?.value,
    unit_price: Number(row.querySelector('[data-col="unit_price"]')?.value || 0),
    discount_pct: Number(row.querySelector('[data-col="discount_pct"]')?.value || 0),
    unit: row.querySelector('[data-f4-field="unit"]')?.value,
    quantity: Number(row.querySelector('[data-col="quantity"]')?.value || 0),
    barcode: row.querySelector('[data-col="barcode"]')?.value,
  });
  const lines = [...container.querySelectorAll('tbody[data-lines] tr')].map(line).filter(item => item.code || item.quantity);
  const header = container.querySelector('.pri-fields');
  return {
    doc_type: container.querySelector('[name="doc_type"]')?.dataset.docType || container.querySelector('[name="doc_type"]')?.value,
    erp_code: header.querySelector('[data-f4-field="erp_code"]')?.value,
    series: header.querySelector('[data-f4-field="series"]')?.value,
    customer_id: Number(container.querySelector('[name="entity"]')?.dataset.customerId) || undefined,
    supplier_id: Number(container.querySelector('[name="entity"]')?.dataset.supplierId) || undefined,
    doc_date: header.querySelector('[name="doc_date"]')?.value,
    due_date: header.querySelector('[name="due_date"]')?.value,
    your_ref: header.querySelector('[name="your_ref"]')?.value,
    warehouse: header.querySelector('[data-f4-field="warehouse"]')?.value,
    commercial_discount: Number(header.querySelector('[name="commercial_discount"]')?.value || 0),
    additional_discount: Number(header.querySelector('[name="additional_discount"]')?.value || 0),
    notes: header.querySelector('[name="notes"]')?.value,
    lines,
  };
}

function paintTotals(container) {
  const payload = collectEditor(container);
  let merc = 0;
  let vat = 0;
  payload.lines.forEach(line => {
    const net = lineAmount(line);
    merc += net;
    vat += net * vatRate(line.vat_code) / 100;
  });
  const disc = Number(payload.commercial_discount || 0) + Number(payload.additional_discount || 0);
  const after = merc * (1 - disc / 100);
  const vatAdj = vat * (1 - disc / 100);
  container.querySelector('[data-tot-merc]').textContent = money(merc);
  container.querySelector('[data-tot-disc]').textContent = money(merc - after);
  container.querySelector('[data-tot-iva]').textContent = money(vatAdj);
  container.querySelector('[data-tot-sub]').textContent = money(after);
  container.querySelector('[data-tot-total]').textContent = money(after + vatAdj);
}

function printSheet(doc, container, {autoPrint = true} = {}) {
  const payload = collectEditor(container);
  const company = state.companies.find(row => Number(row.id) === Number(state.companyId)) || {};
  const issuer = doc.issuer || {};
  const partner = doc.partner || {};
  const name = issuer.name || company.legal_name || company.name || 'TextileFlow';
  const nif = issuer.tax_id || company.tax_id || '';
  const addr = [issuer.address || company.address, issuer.postal_code || company.postal_code, issuer.city || company.city].filter(Boolean).join(' · ');
  const logo = company.logo || '';
  const title = doc.type_label || 'Documento interno';
  const lines = (payload.lines || []).filter(line => line.code || line.quantity);
  const merc = lines.reduce((sum, line) => sum + lineAmount(line), 0);
  const vat = lines.reduce((sum, line) => sum + lineAmount(line) * vatRate(line.vat_code) / 100, 0);
  const rows = lines.map(line => `<tr>
    <td>${esc(line.code || '')}</td>
    <td>${esc(line.description || '')}</td>
    <td>${esc(line.warehouse || '')}</td>
    <td class="num">${number(line.quantity)}</td>
    <td>${esc(String(line.unit || 'UN').toUpperCase())}</td>
    <td class="num">${money(line.unit_price || line.unit_cost || 0)}</td>
    <td class="num">${money(lineAmount(line))}</td>
  </tr>`).join('') || '<tr><td colspan="7">Sem linhas</td></tr>';
  const html = `<!doctype html><html lang="pt-PT"><head><meta charset="utf-8"><title>${esc(title)} ${esc(doc.doc_no || '')}</title>
    <style>
      body{font:12px/1.45 Tahoma,Segoe UI,sans-serif;color:#1a2433;margin:18mm;background:#fff}
      header{display:flex;justify-content:space-between;gap:16px;border-bottom:2px solid #1a3f73;padding-bottom:12px}
      .brand{display:flex;gap:10px;align-items:center}
      .brand img{max-height:44px;max-width:110px}
      .brand b{display:block;font-size:16px}
      .brand small{display:block;color:#5b6b80}
      .doc{text-align:right}
      .doc b{display:block;font-size:18px}
      .meta{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:14px 0}
      .meta div{border:1px solid #c9d4e0;padding:8px 10px;background:#f7fafc}
      .meta span{display:block;font-size:10px;color:#5c738c;text-transform:uppercase}
      table{width:100%;border-collapse:collapse} th,td{border:1px solid #c9d4e0;padding:6px 7px}
      th{background:#e8eef5;font-size:10px;text-align:left} td.num,th.num{text-align:right}
      .totals{margin-left:auto;width:240px;margin-top:12px}
      .totals div{display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid #edf2f8}
      .totals .grand{font-weight:800;border:0;padding-top:8px}
      footer{margin-top:28px;font-size:10px;color:#5c738c}
    </style></head><body>
    <header>
      <div class="brand">${logo ? `<img src="${esc(logo)}" alt="">` : ''}<div><b>${esc(name)}</b>${nif ? `<small>NIF ${esc(nif)}</small>` : ''}${addr ? `<small>${esc(addr)}</small>` : ''}</div></div>
      <div class="doc"><b>${esc(title)}</b><span>${esc(doc.erp_code || '')} ${esc(payload.series || doc.series || '')} · ${esc(doc.doc_no || '')}</span><span>${esc(payload.doc_date || doc.doc_date || '')}</span></div>
    </header>
    <div class="meta">
      <div><span>Entidade</span><b>${esc(partner.name || container.querySelector('[name="entity_name"]')?.value || '—')}</b><small>${esc(partner.tax_id || container.querySelector('[name="tax_id"]')?.value || '')}</small></div>
      <div><span>Referência / observações</span><b>${esc(payload.your_ref || '—')}</b><small>${esc(payload.notes || '')}</small></div>
    </div>
    <table><thead><tr><th>Artigo</th><th>Descrição</th><th>Arm.</th><th class="num">Qtd.</th><th>UN</th><th class="num">Pr. unit.</th><th class="num">Total</th></tr></thead><tbody>${rows}</tbody></table>
    <div class="totals">
      <div><span>Mercadorias</span><b>${money(merc)}</b></div>
      <div><span>IVA</span><b>${money(vat)}</b></div>
      <div class="grand"><span>Total</span><b>${money(merc + vat)}</b></div>
    </div>
    <footer>Documento interno TextileFlow. Não substitui fatura, guia ou nota fiscal do Primavera.</footer>
    ${autoPrint ? '<script>window.onload=function(){window.focus();window.print();}</script>' : ''}
  </body></html>`;
  const win = window.open('', 'tf-internal-print', 'noopener,noreferrer,width=900,height=1100');
  if (!win) { toast('Permita janelas pop-up para imprimir.', 'error'); return; }
  win.document.write(html);
  win.document.close();
}

function lineRowHtml(line, index) {
  const price = line.unit_price != null ? line.unit_price : (line.unit_cost != null ? line.unit_cost : '');
  const total = lineAmount(line);
  const codeField = f4Field('code', line.code || '', {width:'110px'});
  const whField = f4Field('warehouse', line.warehouse || '', {width:'72px'});
  const vatField = f4Field('vat_code', line.vat_code || '23', {width:'64px'});
  const unitField = f4Field('unit', line.unit || 'UN', {width:'56px'});
  return `<tr data-line="${index}" data-material-id="${line.material_id || ''}">
    <td>${codeField}</td>
    <td>${whField}</td>
    <td><input data-col="lot" value="${esc(line.lot || '')}"></td>
    <td><input data-col="description" value="${esc(line.description || '')}"></td>
    <td>${vatField}</td>
    <td class="num">${number(vatRate(line.vat_code || '23'))}</td>
    <td><input data-col="unit_price" class="num" type="number" step="0.0001" value="${esc(price)}"></td>
    <td><input data-col="discount_pct" class="num" type="number" step="0.01" value="${esc(line.discount_pct || 0)}"></td>
    <td>${unitField}</td>
    <td><input data-col="quantity" class="num" type="number" step="0.0001" value="${esc(line.quantity || '')}"></td>
    <td class="num" data-col-total>${money(total)}</td>
    <td><input data-col="barcode" value="${esc(line.barcode || '')}"></td>
  </tr>`;
}

function applyItem(row, item) {
  row.dataset.materialId = item.id || '';
  const f4 = name => row.querySelector(`[data-f4-field="${name}"]`);
  if (f4('code')) f4('code').value = item.code || '';
  const desc = row.querySelector('[data-col="description"]');
  if (desc) desc.value = item.name || item.description || '';
  if (f4('unit')) f4('unit').value = String(item.unit || 'UN').toUpperCase();
  if (f4('vat_code')) f4('vat_code').value = item.vat_code || '23';
  if (f4('warehouse')) f4('warehouse').value = item.warehouse || '';
  const bar = row.querySelector('[data-col="barcode"]');
  if (bar) bar.value = item.barcode || '';
  const price = row.querySelector('[data-col="unit_price"]');
  if (price && item.unit_cost != null && !price.value) price.value = item.unit_cost;
}

export async function renderDocument(container) {
  const id = Number((location.hash.match(/erp-doc\/(\d+)/) || [])[1]);
  if (!id) { location.hash = '#/erp-docs'; return; }
  const [doc, catalog] = await Promise.all([
    get(`/erp/${state.companyId}/documents/${id}`),
    get(`/erp/${state.companyId}/documents/types`),
  ]);
  const extra = doc.extra || {};
  const system = catalog.label || erpName();
  setHeading(`Editor de vendas · ${doc.erp_code || ''} ${doc.series || ''}`, `${doc.doc_no} · ${date(doc.doc_date)}`);
  const side = doc.side || 'sales';
  const partner = doc.partner || {};
  const lines = [...(doc.lines || []), emptyLine(), emptyLine()];
  const types = catalog.types || [];
  const typeMeta = types.find(item => item.id === doc.doc_type) || {};
  const official = Boolean(doc.official ?? typeMeta.official ?? true);
  const locked = Boolean(doc.locked);
  const done = Boolean(doc.primavera_done || doc.primavera_status === 'sent');
  const queued = Boolean(doc.primavera_queued);
  const saveLabel = official ? 'Guardar rascunho' : 'Guardar';
  const erpBanner = official
    ? (locked ? '<span class="pri-erp-state is-locked">Bloqueado</span>'
      : done ? '<span class="pri-erp-state is-done">Finalizado no Primavera</span>'
      : queued ? '<span class="pri-erp-state is-queued">Enviado · a finalizar no Primavera</span>'
      : '<span class="pri-erp-state">Rascunho TextileFlow</span>')
    : '';
  const sendBtn = official && !locked && doc.can_prepare ? '<button type="button" class="is-send" data-erp-act="prepare"><i></i>Enviar para o Primavera</button>' : '';
  const unlockBtn = locked && isAdmin() ? '<button type="button" data-unlock-doc class="pri-tb-unlock"><i></i>Desbloquear</button>' : '';
  const unlockHint = locked && !isAdmin() ? '<span class="pri-erp-state is-locked">Só um administrador pode desbloquear</span>' : '';
  const lastUnlock = doc.unlock_reason ? ` Desbloqueado por ${doc.unlocked_by || 'admin'}: ${doc.unlock_reason}` : '';
  const officialNote = locked
    ? `Documento bloqueado depois do envio ao Primavera.${isAdmin() ? ' Desbloqueie e justifique para alterar.' : ' Peça a um administrador para desbloquear, com justificação.'}`
    : done ? 'Documento oficial concluído no Primavera. Aqui fica só o rasto do envio.'
    : queued ? 'Já foi exportado. A numeração e o ATCUD ficam no Primavera.'
    : 'Rascunho. Enviar para o Primavera; a fatura definitiva emite-se lá.';
  const convertBtns = !official ? (doc.can_convert || []).map(kind => {
    const label = esc(CONVERT_LABEL[kind] || kind);
    return `<button type="button" data-erp-act="convert" data-kind="${kind}"><i></i>${label}</button>`;
  }).join('') : '';
  const internalTools = official ? '' : `
        <button type="button" data-new-editor class="pri-tb-new"><i></i>Novo</button>
        <button type="button" data-print-doc class="pri-tb-print"><i></i>Imprimir</button>
        <button type="button" data-print-layout class="pri-tb-print"><i></i>Layout</button>
        <button type="button" data-send-internal class="is-send"><i></i>Enviar</button>`;
  const tabs = official
    ? `<div class="pri-tabs"><button class="active" type="button">Geral</button></div>`
    : `<div class="pri-tabs">
        <button class="active" type="button" data-pri-tab="geral">Geral</button>
        <button type="button" data-pri-tab="print">Impressão</button>
        <button type="button" disabled>Observações</button>
      </div>`;
  const docField = f4Field('erp_code', doc.erp_code || typeMeta.code || '');
  const entityField = f4Field('entidade', partner.code || '');
  const seriesField = f4Field('series', doc.series || 'A');
  const warehouseField = f4Field('warehouse', extra.warehouse || '');
  const payField = f4Field('condpag', partner.payment_term_code || extra.payment_term || '');
  const lineRows = lines.map((line, index) => lineRowHtml(line, index)).join('');
  const docNo = esc(doc.doc_no || '—');
  const docCode = esc(doc.erp_code || typeMeta.code || '');
  container.innerHTML = `
    <section class="pri-win ${official ? 'is-official' : 'is-internal'}${done ? ' is-done' : ''}${locked ? ' is-locked' : ''}">
      <input type="hidden" name="doc_type" data-doc-type="${esc(doc.doc_type)}" value="${esc(doc.doc_type)}">
      <div class="pri-caption">
        <strong>${official ? 'Rascunho para o Primavera' : 'Documento interno'}</strong>
        <span>${docCode} ${esc(doc.series || 'A')} · ${docNo}</span>
        <em>${esc(erpStateLabel(doc))}</em>
      </div>
      <div class="pri-toolbar">
        ${!locked ? `<button type="button" data-save-doc class="pri-tb-save"><i></i>${saveLabel}</button>` : ''}
        ${internalTools}
        ${sendBtn}
        ${unlockBtn}
        ${unlockHint}
        ${erpBanner}
        ${convertBtns}
        <span class="pri-tb-sep"></span>
        <a href="#/erp-docs" class="pri-tb-find"><i></i>Procurar</a>
        <a href="#/erp-docs" class="pri-cancel"><i></i>Fechar</a>
      </div>
      ${tabs}
      <div class="pri-head" data-pri-panel="geral">
        <div class="pri-fields">
          <div class="pri-row">
            <label>Documento</label><div class="pri-ctl">${docField}</div>
            <label>Série</label><div class="pri-ctl">${seriesField}</div>
            <label>N.º</label><div class="pri-ctl"><input value="${docNo}" readonly></div>
          </div>
          <div class="pri-row pri-row-entity">
            <label>Entidade</label>
            <div class="pri-ctl pri-ctl-code">${entityField}</div>
            <div class="pri-ctl pri-ctl-grow"><input name="entity_name" value="${esc(partner.name || '')}" readonly class="pri-name"></div>
          </div>
          <div class="pri-row">
            <label>Data Doc.</label><div class="pri-ctl"><input name="doc_date" type="date" value="${esc(String(doc.doc_date || '').slice(0,10))}"></div>
            <label>Data Venc.</label><div class="pri-ctl"><input name="due_date" type="date" value="${esc(String(extra.due_date || doc.doc_date || '').slice(0,10))}"></div>
            <label>Cond. Pag.</label><div class="pri-ctl">${payField}</div>
          </div>
          <div class="pri-row">
            <label>Armazém</label><div class="pri-ctl">${warehouseField}</div>
            <label>Contribuinte</label><div class="pri-ctl"><input name="tax_id" value="${esc(partner.tax_id || '')}" readonly></div>
            <label>V/Refer.</label><div class="pri-ctl"><input name="your_ref" value="${esc(extra.your_ref || '')}"></div>
          </div>
          <div class="pri-row pri-row-two">
            <label>Desc. Com.</label><div class="pri-ctl"><input name="commercial_discount" type="number" step="0.01" value="${esc(extra.commercial_discount || 0)}"></div>
            <label>Desc. Adic.</label><div class="pri-ctl"><input name="additional_discount" type="number" step="0.01" value="${esc(extra.additional_discount || 0)}"></div>
          </div>
          <div class="pri-row pri-row-notes">
            <label>Observações</label>
            <div class="pri-ctl pri-ctl-grow"><input name="notes" value="${esc(doc.notes || '')}"></div>
          </div>
          ${official
            ? `<p class="pri-emit">${esc(officialNote)}${locked ? '' : esc(lastUnlock)}</p>`
            : `<p class="pri-emit">Documento interno: imprima, envie e arquive aqui. O Primavera não trata este tipo.</p>`}
        </div>
        <aside class="pri-totals">
          <div><span>Merc./Serv.</span><b data-tot-merc>${money(doc.net_total)}</b></div>
          <div><span>Descontos</span><b data-tot-disc>0,00 €</b></div>
          <div><span>IVA</span><b data-tot-iva>${money(doc.vat_amount)}</b></div>
          <div><span>Outros</span><b>0,00 €</b></div>
          <div><span>Sub-Total</span><b data-tot-sub>${money(doc.net_total)}</b></div>
          <div><span>Acerto</span><b>0,00 €</b></div>
          <div class="pri-grand"><span>Total ${esc(doc.currency || 'EUR')}</span><b data-tot-total>${money(doc.gross_total)}</b></div>
        </aside>
      </div>
      <div class="pri-grid-wrap" data-pri-panel="geral">
        <table class="pri-grid">
          <thead><tr>
            <th>Artigo</th><th>Arm.</th><th>Lote</th><th>Descrição</th><th>CIVA</th><th>IVA</th>
            <th>Pr. Unit.</th><th>Desc.</th><th>UN</th><th>Qtd.</th><th>Total Líq.</th><th>Cód. Barras</th>
          </tr></thead>
          <tbody data-lines>${lineRows}</tbody>
        </table>
      </div>
      ${official ? '' : '<div class="pri-print-panel hidden" data-pri-panel="print"><p class="pri-emit">Pré-visualização do documento interno. Use Layout ou Imprimir na barra.</p><button type="button" class="btn" data-print-layout>Abrir layout de impressão</button></div>'}
      <div class="pri-statusbar"><span>${docCode} ${esc(doc.series || '')} ${docNo}</span><span>${esc(erpStateLabel(doc))}</span></div>
    </section>`;

  const entityInput = container.querySelector('[data-f4-field="entidade"]');
  if (entityInput) {
    entityInput.dataset.customerId = doc.customer_id || '';
    entityInput.dataset.supplierId = doc.supplier_id || '';
    entityInput.setAttribute('name', 'entity');
  }

  const refreshLineVat = row => {
    const code = row.querySelector('[data-f4-field="vat_code"]')?.value || '23';
    const cells = row.querySelectorAll('td.num');
    if (cells[0]) cells[0].textContent = number(vatRate(code));
    row.querySelector('[data-col-total]').textContent = money(lineAmount({
      quantity: row.querySelector('[data-col="quantity"]')?.value,
      unit_price: row.querySelector('[data-col="unit_price"]')?.value,
      discount_pct: row.querySelector('[data-col="discount_pct"]')?.value,
    }));
  };

  container.querySelector('[data-lines]').addEventListener('input', event => {
    const row = event.target.closest('tr');
    if (row) refreshLineVat(row);
    paintTotals(container);
  });

  const ctx = { side };
  bindF4(container, catalog, ctx, {
    erp_code: row => {
      container.querySelector('[data-f4-field="erp_code"]').value = row.code;
      container.querySelector('[name="doc_type"]').dataset.docType = row.id;
      container.querySelector('[name="doc_type"]').value = row.id;
      if (row.series) container.querySelector('[data-f4-field="series"]').value = row.series;
      if (row.side) ctx.side = row.side;
    },
    entidade: row => {
      entityInput.value = row.code;
      entityInput.dataset.customerId = ctx.side === 'sales' ? row.id : '';
      entityInput.dataset.supplierId = ctx.side === 'purchase' ? row.id : '';
      container.querySelector('[name="entity_name"]').value = row.name || '';
      container.querySelector('[name="tax_id"]').value = row.tax_id || '';
      if (row.payment_term_code) container.querySelector('[data-f4-field="condpag"]').value = row.payment_term_code;
    },
    series: row => { container.querySelector('[data-f4-field="series"]').value = row.code; },
    warehouse: (row, input) => { (input || container.querySelector('[data-f4-field="warehouse"]')).value = row.code; },
    condpag: row => { container.querySelector('[data-f4-field="condpag"]').value = row.code; },
    code: (row, input) => {
      const tr = input?.closest('tr');
      if (tr) applyItem(tr, row);
      paintTotals(container);
    },
    vat_code: (row, input) => {
      const field = input?.closest('span')?.querySelector('input') || input;
      if (field) field.value = row.code;
      const tr = field?.closest('tr');
      if (tr) refreshLineVat(tr);
      paintTotals(container);
    },
    unit: (row, input) => {
      const field = input?.closest('span')?.querySelector('input') || input;
      if (field) field.value = row.code;
    },
  });

  const ensureEmptyRow = () => {
    const body = container.querySelector('[data-lines]');
    const last = body.querySelector('tr:last-child [data-f4-field="code"]');
    if (last?.value) body.insertAdjacentHTML('beforeend', lineRowHtml(emptyLine(), body.children.length));
  };
  container.querySelector('[data-lines]').addEventListener('focusout', ensureEmptyRow);

  container.querySelector('[data-unlock-doc]')?.addEventListener('click', () => {
    recordModal({
      title: 'Desbloquear documento',
      subtitle: 'Fica registado o administrador e o motivo. Sem justificação não desbloqueia.',
      fields: [
        {key:'reason', label:'Justificação', type:'textarea', required:true, placeholder:'Ex.: correção de quantidade pedida pelo cliente', help:'Mínimo de 8 caracteres.'},
      ],
      save: payload => post(`/erp/${state.companyId}/documents/${doc.id}/unlock`, {reason: payload.reason}),
      onSaved: () => renderDocument(container),
    });
  });
  container.querySelector('[data-save-doc]')?.addEventListener('click', async () => {
    try {
      const payload = collectEditor(container);
      if (side === 'sales') payload.supplier_id = null;
      else payload.customer_id = null;
      await put(`/erp/${state.companyId}/documents/${doc.id}`, payload);
      toast(official ? 'Rascunho guardado no TextileFlow.' : 'Documento interno guardado.');
      await renderDocument(container);
    } catch (error) { toast(error.message, 'error'); }
  });
  container.addEventListener('keydown', event => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
      event.preventDefault();
      container.querySelector('[data-save-doc]')?.click();
    }
  });
  container.querySelector('[data-new-editor]')?.addEventListener('click', () => openCreate(container, catalog));
  container.querySelector('[data-print-doc]')?.addEventListener('click', () => printSheet(doc, container, {autoPrint: true}));
  container.querySelectorAll('[data-print-layout]').forEach(button => button.addEventListener('click', () => printSheet(doc, container, {autoPrint: false})));
  container.querySelector('[data-send-internal]')?.addEventListener('click', async () => {
    try {
      const payload = collectEditor(container);
      if (side === 'sales') payload.supplier_id = null;
      else payload.customer_id = null;
      await put(`/erp/${state.companyId}/documents/${doc.id}`, payload);
      printSheet(doc, container, {autoPrint: false});
      const email = doc.partner?.email;
      if (email) {
        const subject = encodeURIComponent(`${doc.type_label || 'Documento'} ${doc.doc_no || ''}`);
        const body = encodeURIComponent(`Segue ${doc.type_label || 'documento interno'} ${doc.doc_no || ''} de ${doc.issuer?.name || 'TextileFlow'}.`);
        location.href = `mailto:${email}?subject=${subject}&body=${body}`;
      } else {
        toast('Layout aberto. A entidade não tem email — envie o PDF ou a impressão.');
      }
    } catch (error) { toast(error.message, 'error'); }
  });
  container.querySelectorAll('[data-pri-tab]').forEach(button => button.addEventListener('click', () => {
    container.querySelectorAll('[data-pri-tab]').forEach(item => item.classList.toggle('active', item === button));
    container.querySelectorAll('[data-pri-panel]').forEach(panel => {
      panel.classList.toggle('hidden', panel.dataset.priPanel !== button.dataset.priTab);
    });
  }));
  container.querySelectorAll('[data-erp-act]').forEach(button => button.addEventListener('click', async () => {
    try {
      await put(`/erp/${state.companyId}/documents/${doc.id}`, collectEditor(container));
      if (button.dataset.erpAct === 'prepare') {
        await post(`/erp/${state.companyId}/documents/${doc.id}/prepare`);
        toast('Exportado para o Primavera. Termine a emissão nos documentos oficiais.');
      } else {
        const saved = await post(`/erp/${state.companyId}/documents/${doc.id}/convert`, {doc_type: button.dataset.kind, prepare: false});
        if (!toastStockAlerts(saved)) toast('Documento criado em rascunho.');
      }
      await renderDocument(container);
    } catch (error) { toast(error.message, 'error'); }
  }));
  paintTotals(container);
}

async function openCreate(container, catalog) {
  const types = catalog?.types || catalog?.legacy || [];
  const familyTypes = typesInFamily(catalog || {types}, listState.family);
  const list = (familyTypes.length ? familyTypes : types);
  const first = list[0] || types[0] || {id:'sales_invoice', side:'sales', code:'FA', default_series:'A'};
  const meta = types.find(item => item.id === (listState.doc_type || first.id)) || first;
  try {
    const saved = await post(`/erp/${state.companyId}/documents`, {
      doc_type: meta.id,
      series: listState.series || meta.default_series || 'A',
      lines: [],
      prepare: false,
    });
    location.hash = `#/erp-doc/${saved.id}`;
  } catch (error) { toast(error.message, 'error'); }
}

async function openFromPurchase(container, catalog) {
  const types = (catalog?.types || []).filter(item => item.side === 'purchase');
  recordModal({
    title: 'A partir da ordem de compra',
    values: {doc_type:'requisition', series: listState.series || 'A', prepare:false},
    fields: [
      {key:'order_id', label:'Ordem de compra', type:'select', required:true, options:await options('purchase-orders','order_no')},
      {key:'doc_type', label:'Documento', type:'select', options: types.length ? types.map(item=>({value:item.id, label:`${item.code} · ${item.label}`})) : [
        {value:'requisition', label:'ECF · Encomenda a fornecedor'},
        {value:'supplier_transport', label:'VGT · Guia de fornecedor'},
        {value:'stock_receipt', label:'COM · Entrada de existências'},
        {value:'purchase_invoice', label:'VFA · Fatura de compra'},
      ]},
      {key:'series', label:'Série'},
      {key:'prepare', label:`Preparar já para o ${catalog?.label || erpName()}`, type:'checkbox'},
    ],
    save: payload => post(`/erp/${state.companyId}/documents/from-purchase/${payload.order_id}`, {doc_type: payload.doc_type, series: payload.series, prepare: payload.prepare}),
    onSaved: () => render(container),
  });
}

async function openFromSales(container, catalog) {
  const types = (catalog?.types || []).filter(item => item.side === 'sales');
  recordModal({
    title: 'A partir da encomenda de cliente',
    values: {doc_type:'sales_invoice', series: listState.series || 'A', prepare:false},
    fields: [
      {key:'order_id', label:'Encomenda', type:'select', required:true, options:await options('sales-orders','order_no')},
      {key:'doc_type', label:'Documento', type:'select', options: types.length ? types.map(item=>({value:item.id, label:`${item.code} · ${item.label}`})) : [
        {value:'sales_invoice', label:'FA · Fatura'},
        {value:'sales_delivery', label:'GT · Guia de transporte'},
        {value:'sales_credit', label:'NC · Nota de crédito'},
        {value:'sales_debit', label:'ND · Nota de débito'},
      ]},
      {key:'series', label:'Série'},
      {key:'prepare', label:`Preparar já para o ${catalog?.label || erpName()}`, type:'checkbox'},
    ],
    save: payload => post(`/erp/${state.companyId}/documents/from-sales/${payload.order_id}`, {doc_type: payload.doc_type, series: payload.series, prepare: payload.prepare}),
    onSaved: () => render(container),
  });
}

export async function prepareFromPurchase(orderId, docType = 'requisition') {
  return post(`/erp/${state.companyId}/documents/from-purchase/${orderId}`, {doc_type: docType, prepare: true});
}

export async function prepareFromSales(orderId, docType = 'sales_invoice') {
  return post(`/erp/${state.companyId}/documents/from-sales/${orderId}`, {doc_type: docType, prepare: true});
}

export async function renderCapture(container) {
  const [status, suppliers, materials] = await Promise.all([
    get(`/erp/${state.companyId}/capture/status`),
    options('suppliers','name'),
    options('materials', row => `${row.code} · ${row.name}`),
  ]);
  let preview = null;
  const paint = () => {
    container.innerHTML = pageHeader('Ler fatura', 'Fotografe ou carregue o PDF. O Gemini lê; vocês ligam os artigos uma vez e o programa aprende.', '<a class="btn" href="#/erp-docs">Ver documentos</a>') + `
      <div class="integration-grid">
        <section class="card">
          <div class="card-header"><h2>Gemini</h2><span>${status.gemini_configured?'Chave gravada':'Sem chave'}</span></div>
          ${status.gemini_configured?'<p class="muted">Tire foto à fatura do fornecedor ou escolha um PDF. A leitura corre no servidor; a chave não sai para o ecrã.</p>':`
            <form id="gemini-key-form" class="form-grid">
              <div class="field full"><label>Chave API Gemini<input name="api_key" type="password" autocomplete="off" placeholder="AIza…"></label><small class="muted">Obtém-se em Google AI Studio. Fica cifrada no servidor desta empresa.</small></div>
              <div class="form-footer"><button class="btn primary" type="submit">Guardar chave</button></div>
            </form>`}
          <div class="capture-drop">
            <input id="erp-file" type="file" accept="image/*,application/pdf" capture="environment">
            <label class="btn primary" for="erp-file">Fotografar ou escolher ficheiro</label>
            <p class="muted">JPEG, PNG ou PDF. A foto é reduzida antes de enviar.</p>
          </div>
        </section>
        <section class="card" data-preview>
          ${previewMarkup(preview, suppliers, materials)}
        </section>
      </div>`;
    container.querySelector('#gemini-key-form')?.addEventListener('submit', async event => {
      event.preventDefault();
      try {
        await put(`/erp/${state.companyId}/capture/key`, {api_key: event.currentTarget.api_key.value});
        toast('Chave Gemini guardada.');
        await renderCapture(container);
      } catch (error) { toast(error.message, 'error'); }
    });
    container.querySelector('#erp-file')?.addEventListener('change', async event => {
      const file = event.target.files?.[0];
      if (!file) return;
      try {
        toast('A ler o documento…');
        const packed = await packFile(file);
        preview = await post(`/erp/${state.companyId}/capture/read`, packed);
        paint();
      } catch (error) { toast(error.message, 'error'); }
    });
    container.querySelector('[data-confirm-capture]')?.addEventListener('click', async () => {
      try {
        const payload = readPreview(container, preview);
        const saved = await post(`/erp/${state.companyId}/capture/confirm`, payload);
        const extra = (saved.follow_on || []).map(item => item.doc_no).filter(Boolean);
        toast(`${saved.doc_no} criado${extra.length ? ` e ${extra.join(', ')}` : ''} preparado para o Primavera. Os artigos ligados ficam na memória.`);
        location.hash = '#/erp-docs';
      } catch (error) { toast(error.message, 'error'); }
    });
  };
  paint();
}

function previewMarkup(preview, suppliers, materials) {
  if (!preview) return `<div class="empty"><strong>À espera do documento</strong>A primeira vez tem de ligar cada linha ao artigo TextileFlow. Nas seguintes o programa reconhece sozinho.</div>`;
  const supplierOptions = [`<option value="">Fornecedor…</option>`, ...suppliers.map(item=>`<option value="${item.value}" ${String(item.value)===String(preview.supplier_id||'')?'selected':''}>${esc(item.label)}</option>`)].join('');
  const materialOptions = (selected) => [`<option value="">Artigo TextileFlow…</option>`, ...materials.map(item=>`<option value="${item.value}" ${String(item.value)===String(selected||'')?'selected':''}>${esc(item.label)}</option>`)].join('');
  return `<div class="card-header"><h2>${esc(preview.number||'Documento lido')}</h2><span>${preview.unmatched?preview.unmatched+' linhas por ligar':preview.learned+' linhas reconhecidas'}</span></div>
    <div class="form-grid">
      <div class="field"><label>Fornecedor<select data-cap-supplier>${supplierOptions}</select></label></div>
      <div class="field"><label>Data<input data-cap-date type="date" value="${esc(String(preview.date||'').slice(0,10))}"></label></div>
      <div class="field"><label>Total<input value="${esc(preview.total)}" readonly></label></div>
    </div>
    <p class="muted">${esc(preview.supplier_name||'')} ${esc(preview.supplier_tax_id||'')}</p>
    <div class="table-wrap"><table class="data-table"><thead><tr><th>No documento</th><th>Qtd</th><th>Preço</th><th>Artigo TextileFlow</th></tr></thead><tbody>
      ${(preview.lines||[]).map((line,index)=>`<tr>
        <td><b>${esc(line.source_code||'—')}</b><div class="muted">${esc(line.source_name||'')}</div>${line.learned?'<span class="badge green">Aprendido</span>':''}</td>
        <td>${number(line.quantity)}</td>
        <td>${money(line.unit_cost)}</td>
        <td><select data-cap-material="${index}">${materialOptions(line.material_id)}</select></td>
      </tr>`).join('')}
    </tbody></table></div>
    <div class="form-footer"><button class="btn primary" data-confirm-capture>Guardar e preparar Primavera</button></div>`;
}

function readPreview(container, preview) {
  const lines = (preview.lines||[]).map((line, index) => ({
    ...line,
    material_id: Number(container.querySelector(`[data-cap-material="${index}"]`)?.value||'') || null,
  }));
  return {
    ...preview,
    supplier_id: Number(container.querySelector('[data-cap-supplier]')?.value||'') || null,
    date: container.querySelector('[data-cap-date]')?.value || preview.date,
    lines,
    prepare: true,
  };
}

function packFile(file) {
  return new Promise((resolve, reject) => {
    if (file.type.startsWith('image/')) {
      const image = new Image();
      const url = URL.createObjectURL(file);
      image.onload = () => {
        const canvas = document.createElement('canvas');
        const scale = Math.min(1, 1600 / Math.max(image.width, image.height));
        canvas.width = Math.max(1, image.width * scale);
        canvas.height = Math.max(1, image.height * scale);
        canvas.getContext('2d').drawImage(image, 0, 0, canvas.width, canvas.height);
        const data = canvas.toDataURL('image/jpeg', 0.72).split(',')[1];
        URL.revokeObjectURL(url);
        resolve({mime:'image/jpeg', data});
      };
      image.onerror = () => reject(new Error('Não foi possível ler a fotografia.'));
      image.src = url;
      return;
    }
    const reader = new FileReader();
    reader.onload = () => resolve({mime: file.type || 'application/pdf', data: String(reader.result).split(',')[1]});
    reader.onerror = () => reject(new Error('Não foi possível ler o ficheiro.'));
    reader.readAsDataURL(file);
  });
}

export async function renderAliases(container) {
  const rows = await get(`/erp/${state.companyId}/aliases`);
  container.innerHTML = pageHeader('Artigos aprendidos', 'Cada ligação que confirmam numa fatura fica aqui. Na próxima leitura o ERP reconhece sozinho.', '<a class="btn primary" href="#/erp-capture">Ler nova fatura</a>') + `
    <div class="table-wrap"><table class="data-table"><thead><tr><th>No documento do fornecedor</th><th>Fornecedor</th><th>Artigo TextileFlow</th><th>Vezes</th></tr></thead>
    <tbody>${rows.map(row=>`<tr><td><b>${esc(row.source_code||'—')}</b><div class="muted">${esc(row.source_name||'')}</div></td><td>${esc(row.supplier)}</td><td>${esc(row.material)}</td><td>${row.hits}</td></tr>`).join('')||'<tr><td colspan="4"><div class="empty"><strong>Ainda não aprendeu artigos</strong>Leia uma fatura e ligue as linhas. Essa memória fica para as seguintes.</div></td></tr>'}</tbody></table></div>`;
}
