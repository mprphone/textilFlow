import { crudUpdate, get } from '../api.js';
import { badge, date, datetime, esc, money, number } from '../format.js?v=20260819-5';
import { fieldsCard, fieldsMarkup, mergeCustomData, readForm } from '../forms.js?v=20260824-1';
import { state } from '../state.js';
import { pageHeader, toast } from '../ui.js?v=20260821-19';

const TF_TYPE_LABELS = {
  unclassified: 'Não classificado', finished: 'Produto acabado', raw_material: 'Matéria-prima',
  semi_finished: 'Semiacabado', accessory: 'Acessório', packaging: 'Embalagem', consumable: 'Consumível',
};
const TF_TYPE_OPTIONS = Object.entries(TF_TYPE_LABELS).filter(([value]) => value !== 'finished').map(([value, label]) => ({ value, label }));

function rowsOrEmpty(rows, cols, message) {
  return rows.length ? rows.join('') : `<tr><td colspan="${cols}" class="muted">${esc(message)}</td></tr>`;
}

function historyTable(headers, rows, emptyText) {
  return `<div class="table-wrap"><table class="data-table"><thead><tr>${headers.map(label => `<th>${label}</th>`).join('')}</tr></thead><tbody>${rowsOrEmpty(rows, headers.length, emptyText)}</tbody></table></div>`;
}

function materialFieldGroups(material) {
  const identification = [
    { key: 'code', label: 'Código', required: true },
    { key: 'name', label: 'Descrição', required: true },
    { key: 'tf_type', label: 'Tipo de artigo TextilFlow', type: 'select', options: TF_TYPE_OPTIONS },
    { key: 'family', label: 'Família' }, { key: 'subfamily', label: 'Subfamília' },
    { key: 'unit', label: 'Unidade', default: 'UN' }, { key: 'vat_code', label: 'IVA', default: '23' },
    { key: 'warehouse', label: 'Armazém' }, { key: 'item_type', label: 'Tipo artigo (Primavera)', default: 'M' },
    { key: 'active', label: 'Estado', type: 'select', options: [{ value: 'true', label: 'Ativo' }, { value: 'false', label: 'Inativo' }], default: 'true' },
  ];
  const textile = [
    { key: 'composition', label: 'Composição' }, { key: 'color', label: 'Cor' },
    { key: 'barcode', label: 'Código de barras' },
    { key: 'width_m', label: 'Largura (m)', type: 'number' }, { key: 'gsm', label: 'Gramagem (g/m²)', type: 'number' },
    { key: 'brand', label: 'Marca' },
  ];
  const costing = [
    { key: 'unit_cost', label: 'Custo médio', type: 'number', default: 0 },
    { key: 'lead_time_days', label: 'Prazo (dias)', type: 'number', default: 0 },
  ];
  const notes = [{ key: 'notes', label: 'Observações', type: 'textarea', full: true }];
  const image = [{ key: 'custom__image_url', label: 'Imagem (URL)', type: 'url', full: true, default: material.custom_data?.image_url || '' }];
  return { identification, textile, costing, notes, image, allFields: [...identification, ...textile, ...costing, ...notes, ...image] };
}

function generalTabHtml(material) {
  const { identification, textile, costing, notes, image } = materialFieldGroups(material);
  const values = { ...material, active: material.active ? 'true' : 'false' };
  const imageUrl = material.custom_data?.image_url;
  return `<form data-material-form>
    <div class="grid-2" style="margin-top:0">
      ${fieldsCard('Identificação', identification, values, `Primavera: ${material.sync_status === 'synced' ? 'sincronizado' : 'só local'}${material.primavera_id ? ` · ${material.primavera_id}` : ''}`)}
      <div class="card">
        <div class="card-header"><h2>Imagem</h2></div>
        <div class="form-grid">${fieldsMarkup(image, values)}</div>
        <div class="style-image-preview">${imageUrl ? `<img src="${esc(imageUrl)}" alt="">` : '<span class="style-image-placeholder">◈</span>'}</div>
      </div>
    </div>
    <div class="grid-2">
      ${fieldsCard('Têxtil', textile, values)}
      ${fieldsCard('Custos e prazos', costing, values)}
    </div>
    ${fieldsCard('Notas', notes, values)}
    <div class="card style-save-bar">
      <div><strong>Atualizar dados do artigo</strong><p class="muted">As alterações aplicam-se de imediato à ficha e às listagens.</p></div>
      <button type="submit" class="btn primary">Guardar alterações</button>
    </div>
  </form>`;
}

function purchasingTabHtml(data) {
  return `
    <section class="dossier-block"><h3>Fornecedores</h3>
      ${historyTable(
        ['Fornecedor', 'Prazo', 'Último preço', 'Última compra', 'Notas'],
        (data.suppliers || []).map(row => `<tr>
          <td><b>${esc(row.name)}</b>${row.preferred ? ' <small>preferencial</small>' : ''}<div class="table-subline">${esc(row.code || '')}${row.payment_terms ? ` · ${esc(row.payment_terms)}` : ''}</div></td>
          <td>${row.lead_time_days ? `${number(row.lead_time_days)} dias` : '—'}</td>
          <td>${row.last_price ? money(row.last_price) : '—'}</td>
          <td>${esc(row.last_order_no || '—')}<div class="table-subline">${date(row.last_order_date)}</div></td>
          <td>${esc(row.notes || '—')}</td>
        </tr>`),
        'Ainda não há fornecedor associado a este artigo.',
      )}
    </section>
    <section class="dossier-block"><h3>Compras</h3>
      ${historyTable(
        ['Documento', 'Data', 'Fornecedor', 'Qtd', 'Preço', 'Entrega', 'Estado'],
        (data.purchases || []).map(row => `<tr>
          <td><b>${esc(row.order_no)}</b></td><td>${date(row.order_date)}</td><td>${esc(row.supplier_name)}</td>
          <td>${number(row.received_quantity)} / ${number(row.quantity)}</td><td>${money(row.unit_cost)}</td>
          <td>${date(row.expected_date)}${row.lead_days != null ? `<div class="table-subline">${number(row.lead_days)} dias</div>` : ''}</td>
          <td>${badge(row.status)}</td>
        </tr>`),
        'Sem encomendas a fornecedor para este artigo.',
      )}
    </section>
    <section class="dossier-block"><h3>Últimos preços</h3>
      ${historyTable(
        ['Data', 'Origem', 'Fornecedor', 'Preço'],
        (data.prices || []).map(row => `<tr><td>${date(row.date)}</td><td>${esc(row.source || '')}</td><td>${esc(row.supplier_name || '—')}</td><td>${money(row.unit_price)}</td></tr>`),
        'Ainda não há histórico de preço.',
      )}
    </section>`;
}

function stockTabHtml(data) {
  return `
    <section class="dossier-block"><h3>Lotes em armazém</h3>
      ${historyTable(
        ['Lote', 'Entrada', 'Fornecedor', 'Local', 'Qtd', 'Custo'],
        (data.lots || []).map(row => `<tr><td><b>${esc(row.lot_no)}</b></td><td>${date(row.received_date)}</td><td>${esc(row.supplier_name)}</td><td>${esc(row.location || '—')}</td><td>${number(row.quantity)}</td><td>${money(row.unit_cost)}</td></tr>`),
        'Sem lotes em armazém.',
      )}
    </section>
    <section class="dossier-block"><h3>Movimentos</h3>
      ${historyTable(
        ['Quando', 'Movimento', 'Qtd', 'Ref. / OF'],
        (data.movements || []).map(row => `<tr><td>${datetime(row.movement_time)}</td><td>${badge(row.movement_type)}</td><td>${number(row.quantity)}</td><td>${esc(row.reference || row.order_no || row.lot_no || '—')}</td></tr>`),
        'Sem movimentos registados.',
      )}
    </section>`;
}

function usageTabHtml(data) {
  return `<section class="dossier-block"><h3>Onde é usado</h3><p class="muted">Fichas técnicas (BOM) que incluem este artigo.</p>
    ${historyTable(
      ['Artigo', 'Quantidade', 'Unidade', 'Desperdício'],
      (data.used_in || []).map(row => `<tr><td><b>${esc(row.style_reference)}</b><div class="table-subline">${esc(row.style_description)}</div></td><td>${number(row.quantity)}</td><td>${esc(row.unit)}</td><td>${number(row.waste_pct)}%</td></tr>`),
      'Este artigo ainda não está ligado a nenhuma ficha técnica.',
    )}</section>`;
}

function documentsTabHtml(data) {
  return `<section class="dossier-block"><h3>Documentos ERP</h3>
    ${historyTable(
      ['Documento', 'Tipo', 'Fornecedor', 'Preço'],
      (data.documents || []).map(row => `<tr><td><b>${esc(row.doc_no)}</b><div class="table-subline">${date(row.doc_date)}</div></td><td>${badge(row.doc_type)}</td><td>${esc(row.supplier_name)}</td><td>${money(row.unit_price)}</td></tr>`),
      'Sem requisições, guias ou faturas ligadas.',
    )}</section>
    ${(data.aliases || []).length ? `<section class="dossier-block"><h3>Como o fornecedor escreve</h3><p class="muted">${data.aliases.map(row => `${esc(row.source_name || row.source_code)} (${number(row.hits)})`).join(' · ')}</p></section>` : ''}`;
}

function renderTab(tab, data) {
  if (tab === 'purchasing') return purchasingTabHtml(data);
  if (tab === 'stock') return stockTabHtml(data);
  if (tab === 'usage') return usageTabHtml(data);
  if (tab === 'documents') return documentsTabHtml(data);
  return generalTabHtml(data.material);
}

export async function renderMaterialDetail(container, materialId, back, activeTab = 'general') {
  const data = await get(`/production/${state.companyId}/materials/${materialId}/history`);
  const material = data.material;
  const tabs = [['general', 'Geral'], ['purchasing', 'Compras & Fornecedores'], ['stock', 'Stock'], ['usage', 'Aplicação'], ['documents', 'Documentos']];
  container.innerHTML = pageHeader(material.code, material.name, '<button class="btn" data-back>← Voltar aos artigos</button>') + `
    <div class="detail-hero"><div class="product-image">${material.custom_data?.image_url ? `<img src="${esc(material.custom_data.image_url)}" alt="">` : '◈'}</div><div class="card detail-title">
      <div class="card-header"><div><h2>${esc(material.name)}</h2><p>${esc(TF_TYPE_LABELS[material.tf_type] || 'Não classificado')}</p></div>${badge(material.active ? 'ativo' : 'inativo')}</div>
      <div class="tag-list"><span class="tag">${esc(material.composition || 'Sem composição')}</span><span class="tag">${esc(material.color || 'Sem cor')}</span><span class="tag">${money(material.unit_cost)} / ${esc(material.unit)}</span></div>
    </div></div>
    <div class="tabs" style="margin-top:14px">${tabs.map(([key, label]) => `<button class="tab ${key === activeTab ? 'active' : ''}" data-detail-tab="${key}">${label}</button>`).join('')}</div>
    <div data-detail-content>${renderTab(activeTab, data)}</div>`;
  container.querySelector('[data-back]').addEventListener('click', back);
  container.querySelectorAll('[data-detail-tab]').forEach(button => button.addEventListener('click', () => renderMaterialDetail(container, materialId, back, button.dataset.detailTab)));
  container.querySelector('[data-material-form]')?.addEventListener('submit', async event => {
    event.preventDefault();
    const { allFields } = materialFieldGroups(material);
    let payload = readForm(event.currentTarget, allFields);
    payload.active = payload.active === 'true';
    payload = mergeCustomData(payload, material.custom_data);
    try {
      await crudUpdate('materials', materialId, payload);
      toast('Artigo guardado.');
      await renderMaterialDetail(container, materialId, back, 'general');
    } catch (error) { toast(error.message, 'error'); }
  });
}
