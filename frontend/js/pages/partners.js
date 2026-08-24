import { post } from '../api.js';
import { renderEntityTabs } from '../entity.js?v=20260824-41';
import { badge, date, esc, number } from '../format.js?v=20260819-5';
import { options } from '../data.js';
import { state } from '../state.js';
import { toast } from '../ui.js?v=20260820-5';
import { openSupplierDossier } from './supplier_dossier.js?v=20260824-41';

const common = [
  { key:'code', label:'Código (Cliente/Fornecedor)', required:true, help:'Mesmo código do Primavera' },
  { key:'name', label:'Nome', required:true },
  { key:'tax_id', label:'NIF / Contrib.' },
  { key:'email', label:'Email', type:'email' },
  { key:'phone', label:'Telefone' },
  { key:'active', label:'Activo', type:'checkbox', default:true },
];

const address = [
  { key:'address', label:'Morada', type:'textarea', full:true },
  { key:'postal_code', label:'Cód. postal' },
  { key:'city', label:'Localidade' },
  { key:'country', label:'País', default:'PT' },
];

export async function render(container) {
  await renderEntityTabs(container, [
    { label:'Clientes', config:{ resource:'customers', title:'Clientes (Primavera)', subtitle:'Cliente, NIF, morada, cond. pagamento e moeda — os mesmos campos da ficha Base/Customers.', singular:'cliente', newLabel:'Novo cliente', extraActions:'<button class="btn" data-sync-pri="customers">Puxar do Primavera</button>', fields:[
      ...common,
      ...address,
      {key:'payment_term_code', label:'Cond. pagamento (código)', help:'Ex.: 30D, como no Primavera'},
      {key:'payment_terms', label:'Cond. pagamento (texto)'},
      {key:'currency', label:'Moeda', default:'EUR'},
      {key:'price_list', label:'Tabela de preços'},
      {key:'salesperson', label:'Vendedor'},
      {key:'credit_limit', label:'Plafond', type:'number'},
      {key:'notes', label:'Observações', type:'textarea', full:true},
    ], columns:[
      {key:'code', label:'Cliente', render:r=>`<b>${esc(r.code)}</b>`},
      {key:'name', label:'Nome'},
      {key:'tax_id', label:'NIF'},
      {key:'city', label:'Localidade'},
      {key:'payment_term_code', label:'CondPag'},
      {key:'currency', label:'Moeda'},
      {key:'sync_status', label:'Sync', render:r=>badge(r.sync_status || 'local')},
      {key:'active', label:'Estado', render:r=>badge(r.active?'activo':'inactivo')},
    ] } },
    { label:'Fornecedores', config:{ resource:'suppliers', title:'Fornecedores (Primavera)', subtitle:'Fornecedor, NIF, morada e IBAN — Base/Suppliers. Use 👁 para abrir a ficha completa com desempenho e ocorrências.', singular:'fornecedor', newLabel:'Novo fornecedor', extraActions:'<button class="btn" data-sync-pri="suppliers">Puxar do Primavera</button>',
      rowActions: row => `<button class="btn icon" type="button" data-icon="eye" data-supplier-ficha="${row.id}" aria-label="Abrir ficha completa" title="Abrir ficha completa"></button>`,
      onAction: event => {
        const button = event.target.closest('[data-supplier-ficha]');
        if (button) openSupplierDossier(Number(button.dataset.supplierFicha));
      },
      fields:[
      ...common.map(item => item.key==='code' ? {...item, label:'Código (Fornecedor)'} : item),
      {key:'supplier_type', label:'Tipo interno', type:'select', options:['material','sewing','dyeing','printing','laundry','transport','general']},
      ...address,
      {key:'contact_name', label:'Contacto'},
      {key:'payment_term_code', label:'Cond. pagamento'},
      {key:'currency', label:'Moeda', default:'EUR'},
      {key:'iban', label:'IBAN'},
      {key:'lead_time_days', label:'Prazo (dias)', type:'number', default:0},
      {key:'score', label:'Score interno', type:'number', default:0},
      {key:'notes', label:'Observações', type:'textarea', full:true},
    ], columns:[
      {key:'code', label:'Fornecedor', render:r=>`<b>${esc(r.code)}</b>`},
      {key:'name', label:'Nome'},
      {key:'tax_id', label:'NIF'},
      {key:'city', label:'Localidade'},
      {key:'payment_term_code', label:'CondPag'},
      {key:'sync_status', label:'Sync', render:r=>badge(r.sync_status || 'local')},
      {key:'active', label:'Estado', render:r=>badge(r.active?'activo':'inactivo')},
    ] } },
    { label:'Cond. pagamento', config:{ resource:'payment-terms', title:'Condições de pagamento', subtitle:'Códigos CondPag do Primavera (30D, pronto, etc.).', singular:'condição', newLabel:'Nova condição', extraActions:'<button class="btn" data-sync-pri="payment_terms">Puxar do Primavera</button>', fields:[
      {key:'code', label:'Código', required:true}, {key:'name', label:'Descrição', required:true},
      {key:'days', label:'Dias', type:'number', default:0}, {key:'active', label:'Activo', type:'checkbox', default:true},
    ], columns:[{key:'code',label:'Código'},{key:'name',label:'Descrição'},{key:'days',label:'Dias',render:r=>number(r.days)},{key:'active',label:'Estado',render:r=>badge(r.active?'activo':'inactivo')}] } },
    { label:'Certificações', config:{ resource:'certifications', title:'Certificações', subtitle:'Validade e documentação dos parceiros.', singular:'certificação', newLabel:'Nova certificação', fields:async()=>[{key:'supplier_id',label:'Fornecedor',type:'select',required:true,options:await options('suppliers','name')},{key:'cert_type',label:'Tipo',required:true},{key:'certificate_no',label:'Número'},{key:'issued_date',label:'Emissão',type:'date'},{key:'expiry_date',label:'Validade',type:'date'},{key:'status',label:'Estado',type:'select',options:['valid','expired','pending'],default:'valid'},{key:'document_path',label:'Documento / URL',type:'url',full:true}], columns:[{key:'supplier_id',label:'Fornecedor ID'},{key:'cert_type',label:'Certificação'},{key:'certificate_no',label:'Número'},{key:'issued_date',label:'Emissão',render:r=>date(r.issued_date)},{key:'expiry_date',label:'Validade',render:r=>date(r.expiry_date)},{key:'status',label:'Estado',render:r=>badge(r.status)}] } },
  ]);
  if (!container.dataset.syncPriBound) {
    container.dataset.syncPriBound = '1';
    container.addEventListener('click', async event => {
      const button = event.target.closest('[data-sync-pri]');
      if (!button) return;
      try {
        toast('A puxar tabelas do Primavera…');
        const result = await post(`/integrations/${state.companyId}/primavera/sync`, {resources:[button.dataset.syncPri]});
        const row = (result.results || [])[0] || {};
        toast(`Sincronizado: ${row.created || 0} novos, ${row.updated || 0} actualizados.`);
        await render(container);
      } catch (error) { toast(error.message, 'error'); }
    });
  }
}
