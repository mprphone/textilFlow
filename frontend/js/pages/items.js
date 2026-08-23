import { render as renderStylesPage } from './styles.js';
import { renderEntityPage } from '../entity.js?v=20260823-1';
import { badge, esc, money } from '../format.js?v=20260821-22';
import { post } from '../api.js';
import { state } from '../state.js';
import { toast } from '../ui.js?v=20260821-19';

const TF_TYPE_LABELS = {
  unclassified: 'Não classificado', raw_material: 'Matéria-prima', semi_finished: 'Semiacabado',
  accessory: 'Acessório', packaging: 'Embalagem', consumable: 'Consumível',
};
const TYPE_TABS = [
  ['all', 'Todos'], ['finished', 'Produtos acabados'], ['raw_material', 'Matérias-primas'],
  ['semi_finished', 'Semiacabados'], ['accessory', 'Acessórios'], ['packaging', 'Embalagens'],
  ['consumable', 'Consumíveis'],
];

function isShadow(row) {
  const source = (row.custom_data || {}).source;
  return source === 'style' || source === 'variant';
}

function materialsConfig(activeType) {
  const tfOptions = Object.entries(TF_TYPE_LABELS).map(([value, label]) => ({ value, label }));
  return {
    resource: 'materials', title: 'Artigos', singular: 'artigo', newLabel: 'Novo artigo',
    subtitle: 'Tabela única de artigos (Base/Items do Primavera). Produtos acabados vivem em Tabelas → Artigos → Produtos acabados.',
    extraActions: '<button class="btn" type="button" data-sync-pri="items">Puxar do Primavera</button>',
    query: activeType !== 'all' ? `tf_type=${activeType}` : '',
    filterRows: row => !isShadow(row),
    fields: [
      { key: 'code', label: 'Código', required: true, section: 'Identificação' },
      { key: 'name', label: 'Descrição', required: true, section: 'Identificação' },
      { key: 'tf_type', label: 'Tipo de artigo TextilFlow', type: 'select', options: tfOptions,
        default: activeType !== 'all' ? activeType : 'unclassified', section: 'Identificação',
        help: 'Classificação interna do TextileFlow — não depende do campo Tipo do Primavera.' },
      { key: 'unit', label: 'Unidade', default: 'UN', section: 'Identificação' },
      { key: 'barcode', label: 'Cód. barras', section: 'Identificação' },
      { key: 'composition', label: 'Composição', section: 'Têxtil' },
      { key: 'color', label: 'Cor', section: 'Têxtil' },
      { key: 'width_m', label: 'Largura (m)', type: 'number', section: 'Têxtil' },
      { key: 'gsm', label: 'Gramagem (g/m²)', type: 'number', section: 'Têxtil' },
      { key: 'family', label: 'Família', section: 'Classificação Primavera' },
      { key: 'subfamily', label: 'Subfamília', section: 'Classificação Primavera' },
      { key: 'brand', label: 'Marca', section: 'Classificação Primavera' },
      { key: 'vat_code', label: 'IVA', default: '23', section: 'Classificação Primavera' },
      { key: 'warehouse', label: 'Armazém', section: 'Classificação Primavera' },
      { key: 'item_type', label: 'Tipo artigo (Primavera)', default: 'M', section: 'Classificação Primavera' },
      { key: 'unit_cost', label: 'Custo médio', type: 'number', section: 'Custos e prazos' },
      { key: 'lead_time_days', label: 'Prazo (dias)', type: 'number', default: 0, section: 'Custos e prazos' },
      { key: 'notes', label: 'Anotações', type: 'textarea', full: true, section: 'Notas' },
      { key: 'active', label: 'Ativo', type: 'checkbox', default: true, section: 'Notas' },
    ],
    columns: [
      { key: 'code', label: 'Artigo', render: r => `<b>${esc(r.code)}</b>` },
      { key: 'name', label: 'Descrição' },
      { key: 'tf_type', label: 'Tipo', render: r => badge(TF_TYPE_LABELS[r.tf_type] || 'Não classificado') },
      { key: 'unit', label: 'Un.' }, { key: 'family', label: 'Família' },
      { key: 'unit_cost', label: 'Custo', render: r => money(r.unit_cost) },
      { key: 'sync_status', label: 'Primavera', render: r => badge(r.sync_status || 'local') },
      { key: 'active', label: 'Estado', render: r => badge(r.active ? 'ativo' : 'inativo') },
    ],
  };
}

export async function render(container, activeType = 'all') {
  container.innerHTML = `<div class="sub-cats">${TYPE_TABS.map(([key, label]) =>
    `<button type="button" class="sub-cat ${key === activeType ? 'active' : ''}" data-item-type="${key}">${esc(label)}</button>`
  ).join('')}</div><div data-item-panel></div>`;
  container.querySelectorAll('[data-item-type]').forEach(button =>
    button.addEventListener('click', () => render(container, button.dataset.itemType)));
  const panel = container.querySelector('[data-item-panel]');
  if (activeType === 'finished') { await renderStylesPage(panel); return; }
  const config = materialsConfig(activeType);
  await renderEntityPage(panel, config);
  panel.querySelectorAll('[data-sync-pri]').forEach(button => {
    button.addEventListener('click', async () => {
      try {
        toast('A puxar a tabela do Primavera…');
        await post(`/integrations/${state.companyId}/primavera/sync`, { resources: ['items'] });
        toast('Sincronizado.');
        await render(container, activeType);
      } catch (error) { toast(error.message, 'error'); }
    });
  });
}
