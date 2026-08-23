import { post } from '../api.js';
import { renderEntityPage } from '../entity.js?v=20260819-9';
import { badge, esc, money } from '../format.js?v=20260821-22';
import { state } from '../state.js';
import { toast } from '../ui.js?v=20260821-19';
import { openSupplierDossier } from './supplier_dossier.js?v=20260823-3';
import { render as renderItems } from './items.js?v=20260823-1';

const supplierFicheActions = {
  rowActions: row => `<button class="btn icon" type="button" data-supplier-ficha="${row.id}" title="Abrir ficha completa">👁</button>`,
  onAction: event => {
    const button = event.target.closest('[data-supplier-ficha]');
    if (button) openSupplierDossier(Number(button.dataset.supplierFicha));
  },
};

const address = [
  { key:'address', label:'Morada', type:'textarea', full:true },
  { key:'postal_code', label:'Cód. postal' },
  { key:'city', label:'Localidade' },
  { key:'country', label:'País', default:'PT' },
];

function syncHint() {
  return 'Alterações gravam no TextileFlow e, se a Web API estiver ligada, são enviadas ao Primavera (criar = POST, alterar = PUT).';
}

function configs() {
  return {
    customers: {
      resource:'customers', title:'Clientes', subtitle:'Tabela Base/Customers do Primavera. '+syncHint(),
      singular:'cliente', newLabel:'Novo cliente', extraActions:'<button class="btn" type="button" data-sync-pri="customers">Puxar do Primavera</button>',
      formSubtitle: syncHint(),
      fields:[
        {key:'code', label:'Código', required:true}, {key:'name', label:'Nome', required:true},
        {key:'tax_id', label:'NIF'}, {key:'email', label:'Email', type:'email'}, {key:'phone', label:'Telefone'},
        ...address,
        {key:'payment_term_code', label:'Cond. pagamento'}, {key:'currency', label:'Moeda', default:'EUR'},
        {key:'price_list', label:'Tabela de preços'}, {key:'salesperson', label:'Vendedor'},
        {key:'credit_limit', label:'Plafond', type:'number'}, {key:'notes', label:'Observações', type:'textarea', full:true},
        {key:'active', label:'Activo', type:'checkbox', default:true},
      ],
      columns:[
        {key:'code', label:'Cliente', render:r=>`<b>${esc(r.code)}</b>`}, {key:'name', label:'Nome'},
        {key:'tax_id', label:'NIF'}, {key:'city', label:'Localidade'}, {key:'payment_term_code', label:'CondPag'},
        {key:'sync_status', label:'Primavera', render:r=>badge(r.sync_status || 'local')},
        {key:'active', label:'Estado', render:r=>badge(r.active?'activo':'inactivo')},
      ],
    },
    suppliers: {
      ...supplierFicheActions,
      resource:'suppliers', title:'Fornecedores', subtitle:'Tabela Base/Suppliers do Primavera. '+syncHint(),
      singular:'fornecedor', newLabel:'Novo fornecedor', extraActions:'<button class="btn" type="button" data-sync-pri="suppliers">Puxar do Primavera</button>',
      formSubtitle: syncHint(),
      fields:[
        {key:'code', label:'Código', required:true}, {key:'name', label:'Nome', required:true},
        {key:'tax_id', label:'NIF'}, {key:'email', label:'Email', type:'email'}, {key:'phone', label:'Telefone'},
        {key:'contact_name', label:'Contacto'}, ...address,
        {key:'payment_term_code', label:'Cond. pagamento'}, {key:'currency', label:'Moeda', default:'EUR'},
        {key:'iban', label:'IBAN'}, {key:'notes', label:'Observações', type:'textarea', full:true},
        {key:'active', label:'Activo', type:'checkbox', default:true},
      ],
      columns:[
        {key:'code', label:'Fornecedor', render:r=>`<b>${esc(r.code)}</b>`}, {key:'name', label:'Nome'},
        {key:'tax_id', label:'NIF'}, {key:'city', label:'Localidade'}, {key:'iban', label:'IBAN'},
        {key:'sync_status', label:'Primavera', render:r=>badge(r.sync_status || 'local')},
        {key:'active', label:'Estado', render:r=>badge(r.active?'activo':'inactivo')},
      ],
    },
    'exchange-rates': {
      resource:'exchange-rates', title:'Câmbio', subtitle:'Taxa manual de conversão de moeda estrangeira para a moeda da empresa. Usada nas propostas e no controlo de custos em moeda diferente.',
      singular:'taxa de câmbio', newLabel:'Nova taxa',
      fields:[
        {key:'currency', label:'Moeda estrangeira', required:true, placeholder:'USD'},
        {key:'rate_to_base', label:'Taxa para a moeda da empresa', type:'number', required:true, help:'Quantas unidades da moeda da empresa equivalem a 1 unidade desta moeda (ex.: 1 USD = 0,92 EUR → 0.92).'},
        {key:'effective_date', label:'Válida a partir de', type:'date', required:true},
        {key:'notes', label:'Notas', type:'textarea', full:true},
      ],
      columns:[
        {key:'currency', label:'Moeda', render:r=>`<b>${esc(r.currency)}</b>`},
        {key:'rate_to_base', label:'Taxa', render:r=>money(r.rate_to_base)},
        {key:'effective_date', label:'Válida desde'},
      ],
    },
    banks: {
      resource:'banks', title:'Bancos', subtitle:'Tabela Base/Banks do Primavera. '+syncHint(),
      singular:'banco', newLabel:'Novo banco', extraActions:'<button class="btn" type="button" data-sync-pri="banks">Puxar do Primavera</button>',
      formSubtitle: syncHint(),
      fields:[
        {key:'code', label:'Código', required:true}, {key:'name', label:'Nome', required:true},
        {key:'swift', label:'SWIFT / BIC'}, {key:'iban_prefix', label:'Prefixo IBAN'},
        {key:'country', label:'País', default:'PT'}, {key:'notes', label:'Observações', type:'textarea', full:true},
        {key:'active', label:'Activo', type:'checkbox', default:true},
      ],
      columns:[
        {key:'code', label:'Banco', render:r=>`<b>${esc(r.code)}</b>`}, {key:'name', label:'Nome'},
        {key:'swift', label:'SWIFT'}, {key:'country', label:'País'},
        {key:'sync_status', label:'Primavera', render:r=>badge(r.sync_status || 'local')},
        {key:'active', label:'Estado', render:r=>badge(r.active?'activo':'inactivo')},
      ],
    },
    'service-stages': {
      resource:'service-stages', title:'Etapas de produção', subtitle:'Fases do circuito (corte, confeção, revista, bordado…) usadas para classificar os serviços subcontratados. Lista aberta — acrescente as que precisar.',
      singular:'etapa', newLabel:'Nova etapa',
      fields:[
        {key:'code', label:'Código', required:true}, {key:'name', label:'Nome', required:true},
        {key:'sequence', label:'Ordem', type:'number', default:0, help:'Posição no circuito — menor número corre primeiro.'},
        {key:'active', label:'Estado', type:'checkbox', default:true, help:'Disponível para escolher em serviços'},
      ],
      columns:[
        {key:'code', label:'Código', render:r=>`<b>${esc(r.code)}</b>`}, {key:'name', label:'Nome'},
        {key:'sequence', label:'Ordem'}, {key:'active', label:'Estado', render:r=>badge(r.active?'ativo':'inativo')},
      ],
    },
  };
}

export async function render(container, table = 'customers') {
  if (table === 'items') { await renderItems(container); return; }
  const config = configs()[table] || configs().customers;
  await renderEntityPage(container, config);
  container.querySelectorAll('[data-sync-pri]').forEach(button => {
    button.addEventListener('click', async () => {
      try {
        toast('A puxar a tabela do Primavera…');
        const result = await post(`/integrations/${state.companyId}/primavera/sync`, {resources:[button.dataset.syncPri]});
        const row = (result.results || [])[0] || {};
        toast(`Sincronizado: ${row.created || 0} novos, ${row.updated || 0} actualizados${row.skipped ? ' (recurso indisponível nesta instalação)' : ''}.`);
        await render(container, table);
      } catch (error) { toast(error.message, 'error'); }
    });
  });
}
