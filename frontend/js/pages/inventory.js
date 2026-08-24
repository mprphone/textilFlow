import { get, patch, post } from '../api.js';
import { options } from '../data.js';
import { renderEntityTabs } from '../entity.js?v=20260819-9';
import { badge, date, datetime, esc, humanize, money, number } from '../format.js?v=20260819-5';
import { loadOrderDossier } from '../production/dossier.js?v=20260824-2';
import { recordModal } from '../quick_create.js?v=20260821-19';
import { stageLabel } from '../production/cycle.js?v=20260822-20';
import { state } from '../state.js';
import { loading, openModal, pageHeader, toast } from '../ui.js?v=20260820-5';
import { prepareFromPurchase, startSupplierOrder } from './commercial_docs.js?v=20260822-33';

function reload(container) {
  return render(container, container.dataset.stockView || 'mp');
}

async function erpPurchaseAction(event) {
  const button = event.target.closest('[data-erp-po]');
  if (!button) return;
  const id = Number(button.dataset.id);
  if (!id) return;
  try {
    const saved = await prepareFromPurchase(id, button.dataset.erpPo);
    toast(`${saved.doc_no} preparado para o Primavera.`);
  } catch (error) { toast(error.message, 'error'); }
}

function bindStockPage(container) {
  if (container.dataset.stockBound) return;
  container.dataset.stockBound = '1';
  container.addEventListener('click', async event => {
    const sync = event.target.closest('[data-sync-pri]');
    if (sync) {
      try {
        toast('A puxar tabelas do Primavera…');
        const result = await post(`/integrations/${state.companyId}/primavera/sync`, {resources:[sync.dataset.syncPri]});
        const row = (result.results || [])[0] || {};
        toast(`Sincronizado: ${row.created || 0} novos, ${row.updated || 0} actualizados.`);
        await reload(container);
      } catch (error) { toast(error.message, 'error'); }
      return;
    }
    if (event.target.closest('[data-encomenda]')) {
      try {
        toast('A abrir encomenda no ERP…');
        await startSupplierOrder();
      } catch (error) { toast(error.message, 'error'); }
      return;
    }
    const item = event.target.closest('[data-open-item]');
    if (item) {
      await openItemHistory(item.dataset.openItem || item.dataset.code);
      return;
    }
    const req = event.target.closest('[data-requisitar]');
    if (!req) return;
    try {
      toast('A abrir requisição no ERP…');
      await startSupplierOrder({
        material_id: Number(req.dataset.materialId) || null,
        supplier_id: Number(req.dataset.supplierId) || null,
        code: req.dataset.code,
        name: req.dataset.name,
        quantity: Number(req.dataset.qty) || 1,
        unit_price: Number(req.dataset.price) || 0,
        unit: req.dataset.unit,
        warehouse: req.dataset.warehouse,
        vat_code: req.dataset.vat,
      });
    } catch (error) { toast(error.message, 'error'); }
  });
}

function orderQty(row) {
  const available = Number(row.available) || 0;
  const requested = Number(row.requested) || 0;
  if (requested > available) return requested - Math.max(0, available);
  if (available <= 0) return Math.max(requested, 1);
  return 0;
}

async function board() {
  return get(`/production/${state.companyId}/stock-board`);
}

function emptyRow(cols, title, text) {
  return `<tr><td colspan="${cols}"><div class="empty"><strong>${esc(title)}</strong>${esc(text)}</div></td></tr>`;
}

async function renderMp(container) {
  const data = await board();
  const items = data.raw_items || [];
  const pri = data.primavera || {};
  const totals = items.reduce((sum, row) => ({
    value: sum.value + (Number(row.on_hand) || 0) * (Number(row.unit_price) || 0),
    on_hand: sum.on_hand + (Number(row.on_hand) || 0),
    reserved: sum.reserved + (Number(row.reserved) || 0),
    available: sum.available + (Number(row.available) || 0),
    requested: sum.requested + (Number(row.requested) || 0),
  }), {value: 0, on_hand: 0, reserved: 0, available: 0, requested: 0});
  container.innerHTML = pageHeader(
    'Stock de matérias-primas',
    'Só artigos com stock ou necessidade. O cadastro único está em Tabelas → Artigos.',
    '<button class="btn primary" data-encomenda>Encomenda</button><button class="btn" data-sync-pri="items">Puxar artigos do Primavera</button>',
    'compact',
  ) + `
    <section class="listing-panel"><div class="table-wrap listing-table"><table class="data-table stock-table">
      <thead>
        <tr class="stock-group"><th colspan="2">Artigo</th><th colspan="2">Preço</th><th colspan="4">Quantidades</th><th></th></tr>
        <tr>
          <th>Artigo</th>
          <th>Descrição</th>
          <th class="num">P. uni</th>
          <th>Und</th>
          <th class="num">Qt armazém</th>
          <th class="num">Qt reservada</th>
          <th class="num">Qt disponível</th>
          <th class="num">Qt requisitada</th>
          <th></th>
        </tr>
      </thead>
      <tbody>${items.length ? items.map(row => {
        const qty = orderQty(row);
        return `<tr class="${pri.ok && !row.in_primavera ? 'is-warning' : ''}${qty ? ' is-shortage' : ''}">
        <td class="stock-code"><button type="button" class="stock-item-link" data-open-item="${row.material_id || ''}" data-code="${esc(row.code)}">${esc(row.code)}</button></td>
        <td class="stock-name"><button type="button" class="stock-item-link stock-item-name" data-open-item="${row.material_id || ''}" data-code="${esc(row.code)}">${esc(row.name)}</button></td>
        <td class="num">${money(row.unit_price)}</td>
        <td>${esc(row.unit)}</td>
        <td class="num">${number(row.on_hand)}</td>
        <td class="num">${number(row.reserved)}</td>
        <td class="num">${number(row.available)}</td>
        <td class="num">${number(row.requested)}</td>
        <td class="listing-actions">${qty ? `<button class="btn small primary" data-requisitar data-material-id="${row.material_id || ''}" data-supplier-id="${row.supplier_id || ''}" data-code="${esc(row.code)}" data-name="${esc(row.name)}" data-qty="${qty}" data-price="${row.unit_price || 0}" data-unit="${esc(row.unit)}" data-warehouse="${esc(row.warehouse || '')}" data-vat="${esc(row.vat_code || '23')}">Requisitar</button>` : ''}</td>
      </tr>`;
      }).join('') : emptyRow(9, 'Sem artigos', 'Puxe os artigos do Primavera ou receba uma compra.')}</tbody>
      ${items.length ? `<tfoot><tr>
        <td colspan="2"><b>Total</b> · ${number(items.length)} artigos · ${money(totals.value)}</td>
        <td class="num"></td>
        <td></td>
        <td class="num">${number(totals.on_hand)}</td>
        <td class="num">${number(totals.reserved)}</td>
        <td class="num">${number(totals.available)}</td>
        <td class="num">${number(totals.requested)}</td>
        <td></td>
      </tr></tfoot>` : ''}
    </table></div></section>
    ${primaveraBlock(pri)}`;
  bindStockPage(container);
}

async function renderWip(container) {
  const data = await board();
  const rows = data.wip || [];
  container.innerHTML = pageHeader(
    'Stock em fabrico',
    'Peças ainda na fábrica. O código do artigo é o mesmo de Tabelas → Artigos.',
    '<a class="btn" href="#/stock-mp">Matérias-primas</a><a class="btn" href="#/stock-fg">Produtos acabados</a>',
    'compact',
  ) + `
    <section class="listing-panel"><div class="table-wrap listing-table"><table class="data-table stock-table"><thead><tr><th>OF</th><th>Artigo</th><th>Descrição</th><th>Fase</th><th>Local</th><th class="num">Em aberto</th><th class="num">MP reservada</th><th></th></tr></thead>
      <tbody>${rows.length ? rows.map(row => `<tr>
        <td class="stock-code">${esc(row.order_no)}</td>
        <td class="stock-code">${esc(row.article_code || '')}</td>
        <td class="stock-name">${esc(row.article_name || row.article || '—')}</td>
        <td>${badge(stageLabel(row.stage))}</td>
        <td>${esc(row.location)}</td>
        <td class="num">${number(row.in_progress)} / ${number(row.quantity)}</td>
        <td class="num">${number(row.reserved_mp)}</td>
        <td class="listing-actions"><button class="btn small" data-open-of="${row.id}">Ver OF</button></td>
      </tr>`).join('') : emptyRow(8, 'Nada em fabrico', 'Quando uma OF arranca, as peças saem do stock de MP e entram aqui até serem embaladas.')}</tbody>
      ${rows.length ? `<tfoot><tr><td colspan="5"><b>Total</b> · ${number(rows.length)} OF</td><td class="num">${number(data.wip_pieces)}</td><td class="num">${number(rows.reduce((sum, row) => sum + (Number(row.reserved_mp) || 0), 0))}</td><td></td></tr></tfoot>` : ''}
    </table></div></section>`;
  container.querySelectorAll('[data-open-of]').forEach(button => button.addEventListener('click', () => loadOrderDossier(Number(button.dataset.openOf))));
}

async function renderFg(container) {
  const data = await board();
  const rows = data.finished || [];
  container.innerHTML = pageHeader(
    'Stock de produtos acabados',
    'OF já revistas e embaladas, à espera de expedição. A saída confirma-se no menu Embalagem / Expedição.',
    '<a class="btn" href="#/embalagem">Embalagem</a><a class="btn primary" href="#/shipping">Expedição</a>',
    'compact',
  ) + `
    <section class="listing-panel"><div class="table-wrap listing-table"><table class="data-table stock-table"><thead><tr><th>OF</th><th>Artigo</th><th>Descrição</th><th>Fase</th><th class="num">Embalado</th><th>Local</th><th></th></tr></thead>
      <tbody>${rows.length ? rows.map(row => `<tr>
        <td class="stock-code">${esc(row.order_no)}</td>
        <td class="stock-code">${esc(row.article_code || '')}</td>
        <td class="stock-name">${esc(row.article_name || row.article || '—')}</td>
        <td>${badge(stageLabel(row.stage))}</td>
        <td class="num">${number(row.packed)}</td>
        <td>${esc(row.location)}</td>
        <td class="listing-actions"><button class="btn small" data-open-of="${row.id}">Ver OF</button></td>
      </tr>`).join('') : emptyRow(7, 'Sem produto acabado em armazém', 'Depois da embalagem a OF aparece aqui até sair para o cliente.')}</tbody>
      ${rows.length ? `<tfoot><tr><td colspan="4"><b>Total</b> · ${number(rows.length)} OF</td><td class="num">${number(data.finished_pieces)}</td><td colspan="2"></td></tr></tfoot>` : ''}
    </table></div></section>`;
  container.querySelectorAll('[data-open-of]').forEach(button => button.addEventListener('click', () => loadOrderDossier(Number(button.dataset.openOf))));
}

async function renderPacking(container) {
  const data = await board();
  const rows = data.packing || [];
  container.innerHTML = pageHeader(
    'Embalagem',
    'Só aparecem peças que chegaram à revista e têm controlo de qualidade aprovado.',
    '<a class="btn" href="#/stock-wip">Stock em fabrico</a><a class="btn" href="#/stock-fg">Produto acabado</a><a class="btn primary" href="#/shipping">Expedição</a>',
    'compact',
  ) + `
    <section class="listing-panel"><div class="table-wrap listing-table"><table class="data-table stock-table"><thead><tr><th>OF</th><th>Artigo</th><th>Descrição</th><th class="num">Por embalar</th><th class="num">Já embalado</th><th></th></tr></thead><tbody>
      ${rows.length ? rows.map((row,index) => `<tr><td class="stock-code">${esc(row.order_no)}</td><td class="stock-code">${esc(row.article_code || '')}</td><td>${esc(row.article_name || '—')}${row.variant ? `<small class="table-subline">${esc(row.variant)}</small>` : ''}</td><td class="num"><b>${number(row.available_to_pack)}</b></td><td class="num">${number(row.packed_total)}</td><td class="listing-actions"><button class="btn small primary" data-pack-index="${index}">Registar embalagem</button><button class="btn small" data-open-of="${row.id}">Ver OF</button></td></tr>`).join('') : emptyRow(6, 'Nada por embalar', 'As peças aprovadas na revista aparecerão aqui.')}
    </tbody></table></div></section>`;
  container.querySelectorAll('[data-open-of]').forEach(button => button.addEventListener('click', () => loadOrderDossier(Number(button.dataset.openOf))));
  container.querySelectorAll('[data-pack-index]').forEach(button => button.addEventListener('click', () => {
    const row = rows[Number(button.dataset.packIndex)];
    recordModal({
      title: `Embalagem · ${row.order_no}`,
      values: { quantity: row.available_to_pack, package_type: 'box', packaging_unit_cost: 0 },
      fields: [
        { key: 'quantity', label: `Quantidade (máx. ${number(row.available_to_pack)})`, type: 'number', required: true, section: 'Produto acabado' },
        ...(row.batch_options?.length ? [{ key: 'batch_id', label: 'Lote produtivo', type: 'select', required: true, options: row.batch_options, help: 'Mantém a rastreabilidade até à caixa e à expedição.', section: 'Produto acabado' }] : []),
        { key: 'package_code', label: 'Código da caixa/palete', help: 'Em branco: numeração automática', section: 'Unidade logística' },
        { key: 'package_type', label: 'Tipo', type: 'select', options:[{value:'box',label:'Caixa'},{value:'pallet',label:'Palete'},{value:'bundle',label:'Volume'}], section: 'Unidade logística' },
        { key: 'packaging_unit_cost', label: 'Custo embalagem / unidade (€)', type: 'number', default:0, section: 'Custo real' },
        { key: 'notes', label: 'Notas', type: 'textarea', full:true },
      ],
      save: payload => post(`/production/orders/${row.id}/pack`, {...payload, variant_id:row.variant_id}),
      onSaved: async () => { toast('Embalagem registada em produto acabado.'); await renderPacking(container); },
    });
  }));
}

async function articleTabs() {
  return [
    {label:'Artigos',config:{resource:'materials',title:'Artigos (Primavera)',subtitle:'Código artigo, unidade, IVA, família e armazém — os mesmos campos de Base/Items.',singular:'artigo',newLabel:'Novo artigo',extraActions:'<button class="btn" data-sync-pri="items">Puxar artigos do Primavera</button>',fields:async()=>[
      {key:'code',label:'Artigo',required:true,help:'Mesmo código do Primavera'},{key:'name',label:'Descrição',required:true},{key:'item_type',label:'Tipo artigo',default:'M',help:'M mercadoria, S serviço'},
      {key:'category',label:'Categoria interna',type:'select',options:['fabric','thread','trim','label','packaging','chemical','other'],default:'fabric'},
      {key:'unit',label:'Unidade',default:'UN'},{key:'vat_code',label:'IVA / Cód. IVA',default:'23'},{key:'barcode',label:'Cód. barras'},
      {key:'family',label:'Família'},{key:'subfamily',label:'Subfamília'},{key:'brand',label:'Marca'},{key:'warehouse',label:'Armazém default'},
      {key:'supplier_id',label:'Fornecedor',type:'select',options:await options('suppliers','name')},{key:'unit_cost',label:'PC médio',type:'number',default:0},{key:'last_cost',label:'PC último',type:'number',default:0},
      {key:'composition',label:'Composição'},{key:'color',label:'Cor'},{key:'width_m',label:'Largura (m)',type:'number'},{key:'gsm',label:'Gramagem',type:'number'},
      {key:'minimum_stock',label:'Stock mínimo',type:'number',default:0},{key:'lead_time_days',label:'Lead time',type:'number',default:0},{key:'active',label:'Activo',type:'checkbox',default:true},
    ],columns:[{key:'code',label:'Artigo',render:r=>`<b>${esc(r.code)}</b>`},{key:'name',label:'Descrição'},{key:'unit',label:'Un.'},{key:'vat_code',label:'IVA'},{key:'family',label:'Família'},{key:'warehouse',label:'Armazém'},{key:'unit_cost',label:'PC médio',render:r=>money(r.unit_cost)},{key:'sync_status',label:'Sync',render:r=>badge(r.sync_status||'local')},{key:'active',label:'Estado',render:r=>badge(r.active?'activo':'inactivo')}]}},
    {label:'Armazéns',config:{resource:'warehouses',title:'Armazéns',subtitle:'Códigos de armazém iguais ao Primavera (Base/Warehouses).',singular:'armazém',newLabel:'Novo armazém',extraActions:'<button class="btn" data-sync-pri="warehouses">Puxar armazéns</button>',fields:[
      {key:'code',label:'Código',required:true},{key:'name',label:'Descrição',required:true},{key:'location',label:'Localização'},{key:'active',label:'Activo',type:'checkbox',default:true},
    ],columns:[{key:'code',label:'Armazém'},{key:'name',label:'Descrição'},{key:'location',label:'Local'},{key:'active',label:'Estado',render:r=>badge(r.active?'activo':'inactivo')}]}},
  ];
}

async function purchaseTabs() {
  return [
    {label:'Compras',config:{resource:'purchase-orders',title:'Ordens de compra',subtitle:'Fornecedores, prazos, receções e valor. Os botões preparam o documento para o Primavera.',singular:'ordem de compra',newLabel:'Nova compra',fields:async()=>[
      {key:'supplier_id',label:'Fornecedor',type:'select',required:true,options:await options('suppliers','name')},{key:'order_no',label:'Número',required:true},{key:'order_date',label:'Data',type:'date'},{key:'expected_date',label:'Entrega prevista',type:'date'},
      {key:'status',label:'Estado',type:'select',options:['draft','sent','partial','received','cancelled'],default:'draft'},{key:'total',label:'Total',type:'number',default:0},{key:'notes',label:'Notas',type:'textarea',full:true},
    ],rowActions:r=>`<button class="btn small primary" data-erp-po="requisition" data-id="${r.id}">Requisição</button><button class="btn small" data-erp-po="purchase_invoice" data-id="${r.id}">Fatura compra</button><button class="btn small" data-erp-po="supplier_transport" data-id="${r.id}">Guia</button><button class="btn small" data-erp-po="stock_receipt" data-id="${r.id}">Entrada</button>`,onAction:erpPurchaseAction,columns:[{key:'order_no',label:'OC',render:r=>`<b>${esc(r.order_no)}</b>`},{key:'supplier_id',label:'Fornecedor'},{key:'order_date',label:'Data',render:r=>date(r.order_date)},{key:'expected_date',label:'Entrega',render:r=>date(r.expected_date)},{key:'total',label:'Total',render:r=>money(r.total)},{key:'status',label:'Estado',render:r=>badge(r.status)}]}},
    {label:'Linhas de compra',config:{resource:'purchase-order-lines',title:'Linhas de compra',subtitle:'Materiais, quantidades, preços e receções.',singular:'linha de compra',newLabel:'Nova linha',fields:async()=>[
      {key:'purchase_order_id',label:'Ordem de compra',type:'select',required:true,options:await options('purchase-orders','order_no')},{key:'material_id',label:'Material',type:'select',required:true,options:await options('materials',r=>`${r.code} · ${r.name}`)},
      {key:'quantity',label:'Quantidade',type:'number',required:true},{key:'unit_cost',label:'Custo unitário',type:'number',default:0},{key:'received_quantity',label:'Recebido',type:'number',default:0},
    ],columns:[{key:'purchase_order_id',label:'OC'},{key:'material_id',label:'Material'},{key:'quantity',label:'Encomendado',render:r=>number(r.quantity)},{key:'received_quantity',label:'Recebido',render:r=>number(r.received_quantity)},{key:'unit_cost',label:'Custo',render:r=>money(r.unit_cost)}]}},
  ];
}

function historyTable(headers, rows, emptyText) {
  const body = rows.length
    ? rows.join('')
    : `<tr><td colspan="${headers.length}" class="muted">${esc(emptyText)}</td></tr>`;
  return `<div class="table-wrap"><table class="data-table"><thead><tr>${headers.map(label => `<th>${label}</th>`).join('')}</tr></thead><tbody>${body}</tbody></table></div>`;
}

function historyHtml(data) {
  const item = data.material || {};
  const summary = data.summary || {};
  const suppliers = data.suppliers || [];
  const purchases = data.purchases || [];
  const prices = data.prices || [];
  const documents = data.documents || [];
  const lots = data.lots || [];
  const movements = data.movements || [];
  const aliases = data.aliases || [];
  return `<div class="item-history">
    <p class="dossier-meta">${esc(item.code)} · ${esc(item.name)} · ${esc(item.unit)}${item.composition ? ` · ${esc(item.composition)}` : ''}${item.warehouse ? ` · armazém ${esc(item.warehouse)}` : ''}</p>
    <div class="dossier-kpis">
      <div><span>Último preço</span><strong>${money(summary.last_price)}</strong></div>
      <div><span>Média recente</span><strong>${money(summary.average_price)}</strong></div>
      <div><span>Prazo</span><strong>${summary.lead_time_days ? `${number(summary.lead_time_days)} dias` : '—'}</strong></div>
      <div><span>Em armazém</span><strong>${number(summary.on_hand)} ${esc(item.unit || '')}</strong></div>
      <div><span>Fornecedores</span><strong>${number(summary.suppliers)}</strong></div>
    </div>
    <section class="dossier-block"><h3>Onde comprámos</h3>
      ${historyTable(
        ['Fornecedor', 'Prazo', 'Último preço', 'Última compra', 'Notas'],
        suppliers.map(row => `<tr>
          <td><b>${esc(row.name)}</b>${row.preferred ? ' <small>preferencial</small>' : ''}<div class="table-subline">${esc(row.code)}${row.payment_terms ? ` · ${esc(row.payment_terms)}` : ''}</div></td>
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
        purchases.map(row => `<tr>
          <td><b>${esc(row.order_no)}</b></td>
          <td>${date(row.order_date)}</td>
          <td>${esc(row.supplier_name)}</td>
          <td>${number(row.received_quantity)} / ${number(row.quantity)} ${esc(item.unit || '')}</td>
          <td>${money(row.unit_cost)}</td>
          <td>${date(row.expected_date)}${row.lead_days != null ? `<div class="table-subline">${number(row.lead_days)} dias</div>` : ''}</td>
          <td>${badge(row.status)}</td>
        </tr>`),
        'Sem encomendas a fornecedor para este artigo.',
      )}
    </section>
    <div class="dossier-grid">
      <section class="dossier-block"><h3>Últimos preços</h3>
        ${historyTable(
          ['Data', 'Origem', 'Fornecedor', 'Preço'],
          prices.map(row => `<tr>
            <td>${date(row.date)}</td>
            <td>${esc(humanize(row.source))}<div class="table-subline">${esc(row.reference || '')}</div></td>
            <td>${esc(row.supplier_name || '—')}</td>
            <td>${money(row.unit_price)}</td>
          </tr>`),
          'Ainda não há histórico de preço.',
        )}
      </section>
      <section class="dossier-block"><h3>Documentos ERP</h3>
        ${historyTable(
          ['Documento', 'Tipo', 'Fornecedor', 'Preço'],
          documents.map(row => `<tr>
            <td><b>${esc(row.doc_no)}</b><div class="table-subline">${date(row.doc_date)}</div></td>
            <td>${badge(row.doc_type)}</td>
            <td>${esc(row.supplier_name)}</td>
            <td>${money(row.unit_price)}</td>
          </tr>`),
          'Sem requisições, guias ou faturas ligadas.',
        )}
      </section>
    </div>
    <section class="dossier-block"><h3>Lotes e movimentos</h3>
      ${historyTable(
        ['Lote', 'Entrada', 'Fornecedor', 'Local', 'Qtd', 'Custo'],
        lots.map(row => `<tr>
          <td><b>${esc(row.lot_no)}</b></td>
          <td>${date(row.received_date)}</td>
          <td>${esc(row.supplier_name)}</td>
          <td>${esc(row.location || '—')}</td>
          <td>${number(row.quantity)}</td>
          <td>${money(row.unit_cost)}</td>
        </tr>`),
        'Sem lotes em armazém.',
      )}
      ${movements.length ? historyTable(
        ['Quando', 'Movimento', 'Qtd', 'Ref. / OF'],
        movements.map(row => `<tr>
          <td>${datetime(row.movement_time)}</td>
          <td>${badge(row.movement_type)}</td>
          <td>${number(row.quantity)}</td>
          <td>${esc(row.reference || row.order_no || row.lot_no || '—')}</td>
        </tr>`),
        '',
      ) : ''}
    </section>
    ${aliases.length ? `<section class="dossier-block"><h3>Como o fornecedor escreve</h3>
      <p class="muted">${aliases.map(row => `${esc(row.source_name || row.source_code)} (${number(row.hits)})`).join(' · ')}</p>
    </section>` : ''}
    <section class="dossier-block"><h3>Anotações</h3>
      <textarea data-item-notes rows="4" placeholder="Prazos combinados, qualidade, mínimo de encomenda, contactos…">${esc(item.notes || '')}</textarea>
      <div class="actions u-mt-2"><button class="btn primary" type="button" data-save-notes>Gravar anotações</button></div>
    </section>
  </div>`;
}

async function openItemHistory(key) {
  if (!key) return;
  openModal('Historial do artigo', loading('A carregar compras, preços e fornecedores…'), String(key));
  try {
    const data = await get(`/production/${state.companyId}/materials/${encodeURIComponent(key)}/history`);
    const item = data.material || {};
    openModal(item.code || 'Artigo', historyHtml(data), item.name || '');
    document.querySelector('[data-save-notes]')?.addEventListener('click', async () => {
      try {
        await patch(`/production/${state.companyId}/materials/${item.id}/notes`, {
          notes: document.querySelector('[data-item-notes]')?.value || '',
        });
        toast('Anotações gravadas no artigo.');
      } catch (error) { toast(error.message, 'error'); }
    });
  } catch (error) {
    toast(error.message, 'error');
  }
}

async function renderPurchases(container) {
  container.innerHTML = pageHeader('Compras', 'Encomendas a fornecedores. A receção entra no stock de matérias-primas.', '<a class="btn" href="#/stock-mp">Stock MP</a>', 'compact') + '<div data-purchase-tabs></div>';
  await renderEntityTabs(container.querySelector('[data-purchase-tabs]'), await purchaseTabs());
}

async function renderCatalog(container) {
  container.innerHTML = pageHeader('Artigos', 'Cadastro de artigos e armazéns, iguais ao Primavera.', '<button class="btn" data-sync-pri="items">Puxar artigos do Primavera</button>', 'compact') + '<div data-catalog-tabs></div>';
  await renderEntityTabs(container.querySelector('[data-catalog-tabs]'), await articleTabs());
  bindStockPage(container);
}

function primaveraBlock(pri) {
  if (pri.ok) {
    const items = pri.items || [];
    return `<section class="card u-mt-4"><div class="card-header"><h2>Stock Primavera</h2><span>${number(pri.count)} linhas · ${esc(pri.path || '')}</span></div>
      ${items.length ? `<div class="table-wrap"><table class="data-table"><thead><tr><th>Artigo</th><th>Armazém</th><th>Stock</th><th>Reservado</th><th>Disponível</th></tr></thead>
      <tbody>${items.map(row => `<tr><td><b>${esc(row.item)}</b></td><td>${esc(row.warehouse)}</td><td>${number(row.quantity)}</td><td>${number(row.reserved)}</td><td>${number(row.available)}</td></tr>`).join('')}</tbody></table></div>` : '<p class="muted">A Web API não devolveu linhas de stock.</p>'}
    </section>`;
  }
  return `<section class="card u-mt-4"><div class="card-header"><h2>Stock Primavera</h2><span>Não ligado</span></div>
    <p class="muted">${esc(pri.error || 'Configure a Web API em ERP → Ligação Primavera.')} Enquanto não houver ligação, a listagem usa os artigos já sincronizados.</p>
  </section>`;
}

export async function render(container, view = 'mp') {
  container.dataset.stockView = view;
  if (view === 'wip') return renderWip(container);
  if (view === 'packing') return renderPacking(container);
  if (view === 'fg') return renderFg(container);
  if (view === 'purchases') return renderPurchases(container);
  if (view === 'catalog') return renderCatalog(container);
  return renderMp(container);
}
