import { render as renderStylesPage } from './styles.js';
import { renderMaterialDetail } from './material_detail.js';
import { renderEntityPage } from '../entity.js?v=20260824-41';
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

function materialsConfig(activeType, panel) {
  const tfOptions = Object.entries(TF_TYPE_LABELS).map(([value, label]) => ({ value, label }));
  return {
    resource: 'materials', title: 'Artigos', singular: 'artigo', newLabel: 'Novo artigo',
    subtitle: 'Tabela única de artigos (Base/Items do Primavera). Produtos acabados vivem em Tabelas → Artigos → Produtos acabados.',
    extraActions: '<button class="btn" type="button" data-sync-pri="items">Puxar do Primavera</button>',
    query: activeType !== 'all' ? `tf_type=${activeType}` : '',
    filterRows: row => !isShadow(row),
    rowActions: row => `<button class="btn icon primary" type="button" data-icon="eye" data-open-material="${row.id}" aria-label="Abrir ficha" title="Abrir ficha"></button>`,
    onAction: (event, rows) => {
      const button = event.target.closest('[data-open-material]');
      if (!button) return;
      const row = rows.find(item => item.id === Number(button.dataset.openMaterial));
      if (row) renderMaterialDetail(panel, row.id, () => renderEntityPage(panel, materialsConfig(activeType, panel)));
    },
    formSubtitle: row => row
      ? 'Edição rápida do essencial. Composição, custos, fornecedores e mais editam-se na ficha completa ("Abrir ficha").'
      : 'Crie o artigo com o essencial — o resto preenche-se depois na ficha completa.',
    fields: [
      { key: 'code', label: 'Código', required: true },
      { key: 'name', label: 'Descrição', required: true },
      { key: 'tf_type', label: 'Tipo de artigo TextilFlow', type: 'select', options: tfOptions,
        default: activeType !== 'all' ? activeType : 'unclassified',
        help: 'Classificação interna do TextileFlow — não depende do campo Tipo do Primavera.' },
      { key: 'unit', label: 'Unidade', default: 'UN' },
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
  const config = materialsConfig(activeType, panel);
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
