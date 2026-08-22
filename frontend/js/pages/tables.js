import { post } from '../api.js';
import { renderEntityPage } from '../entity.js?v=20260819-9';
import { badge, esc, money } from '../format.js?v=20260821-22';
import { state } from '../state.js';
import { toast } from '../ui.js?v=20260821-19';

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
    items: {
      resource:'materials', title:'Artigos', subtitle:'Tabela Base/Items do Primavera. '+syncHint(),
      singular:'artigo', newLabel:'Novo artigo', extraActions:'<button class="btn" type="button" data-sync-pri="items">Puxar do Primavera</button>',
      formSubtitle: syncHint(),
      fields:[
        {key:'code', label:'Código', required:true}, {key:'name', label:'Descrição', required:true},
        {key:'unit', label:'Unidade', default:'UN'}, {key:'barcode', label:'Cód. barras'},
        {key:'family', label:'Família'}, {key:'subfamily', label:'Subfamília'}, {key:'brand', label:'Marca'},
        {key:'vat_code', label:'IVA', default:'23'}, {key:'warehouse', label:'Armazém'},
        {key:'item_type', label:'Tipo artigo', default:'M'}, {key:'unit_cost', label:'Custo médio', type:'number'},
        {key:'active', label:'Activo', type:'checkbox', default:true},
      ],
      columns:[
        {key:'code', label:'Artigo', render:r=>`<b>${esc(r.code)}</b>`}, {key:'name', label:'Descrição'},
        {key:'unit', label:'Un.'}, {key:'family', label:'Família'}, {key:'vat_code', label:'IVA'},
        {key:'unit_cost', label:'Custo', render:r=>money(r.unit_cost)},
        {key:'sync_status', label:'Primavera', render:r=>badge(r.sync_status || 'local')},
        {key:'active', label:'Estado', render:r=>badge(r.active?'activo':'inactivo')},
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
  };
}

export async function render(container, table = 'customers') {
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
