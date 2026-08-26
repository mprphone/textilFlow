import { get, post, put, remove } from '../api.js?v=20260826-3';
import { badge, esc } from '../format.js?v=20260826-3';
import { bindPasswordToggles, readForm, renderForm } from '../forms.js?v=20260826-3';
import { setCompany, setSession, state } from '../state.js';
import { closeModal, openModal, toast } from '../ui.js?v=20260826-3';

const TABS = [
  {id: 'geral', label: 'Geral'},
  {id: 'erp', label: 'ERP'},
  {id: 'email', label: 'Contas de email'},
];
const STATUS_LABEL = {active: 'Ativa', inactive: 'Inativa', suspended: 'Suspensa'};
const LEGAL_FORM = {
  lda: 'Sociedade por quotas (Lda.)', unipessoal: 'Unipessoal por quotas', sa: 'Sociedade anónima (S.A.)',
  eni: 'Empresário em nome individual', cooperativa: 'Cooperativa', outra: 'Outra',
};
const CARD = {cardClass: 'company-fiche-card'};

const ctx = {panel: null, company: null, companyId: null, tab: 'geral', mode: 'view', accounts: [], erp: null};

export async function openCompanyFiche(panel, company = null, onChanged = null) {
  ctx.panel = panel;
  ctx.onChanged = onChanged;
  ctx.company = company;
  ctx.companyId = company?.id || null;
  ctx.tab = 'geral';
  ctx.mode = company ? 'view' : 'edit';
  ctx.accounts = [];
  ctx.erp = null;
  try {
    ctx.software = await softwareOptionsFor(company);
  } catch {
    ctx.software = {options: KNOWN_BILLING, currentSystem: 'primavera'};
  }
  openModal(company ? company.name : 'Nova empresa', '<div class="loading">A abrir a ficha…</div>', '', CARD);
  await paint();
}

async function paint() {
  const name = ctx.company?.name || 'Nova empresa';
  const subtitle = ctx.mode === 'view' ? 'A consultar. Use Editar para alterar.' : 'Altere só o que precisa e grave.';
  openModal(name, await ficheHtml(), subtitle, CARD);
  bindHeader();
  await bindTab();
}

async function ficheHtml() {
  const canEdit = isAdmin();
  return `<div class="co-fiche">
    <nav class="co-tabs">${TABS.map(tab => `<button type="button" class="${ctx.tab === tab.id ? 'on' : ''}" data-co-tab="${tab.id}">${tab.label}</button>`).join('')}</nav>
    <div class="co-toolbar">
      ${ctx.companyId && canEdit ? (ctx.mode === 'view'
        ? '<button type="button" class="btn primary" data-co-edit>Editar</button>'
        : '<button type="button" class="btn" data-co-view>Visualizar</button>') : ''}
    </div>
    <div class="co-pane" data-co-pane>${await paneHtml()}</div>
  </div>`;
}

async function paneHtml() {
  if (ctx.tab === 'erp') return erpHtml();
  if (ctx.tab === 'email') return emailHtml();
  if (ctx.mode === 'view' && ctx.company) return viewGeralHtml(ctx.company);
  return editGeralHtml();
}

function viewGeralHtml(company) {
  const p = company.profile || {};
  const values = companyValues(company);
  const status = company.status || (company.active === false ? 'inactive' : 'active');
  const row = (label, value) => `<div><span>${esc(label)}</span><strong>${value || '—'}</strong></div>`;
  const secret = (set) => set ? 'Definida (cifrada)' : 'Não definida';
  return `<div class="co-view">
    <section class="sf-card"><h3>Identificação</h3><div class="sf-kv">
      ${row('Estado', `<span class="badge co-st-${status}">${STATUS_LABEL[status] || status}</span>`)}
      ${row('Código', esc(values.code))}
      ${row('Nome', esc(values.name))}
      ${row('Firma', esc(values.legal_name))}
      ${row('Forma jurídica', esc(LEGAL_FORM[values.legal_form] || values.legal_form || '—'))}
      ${row('NIF', esc(values.tax_id))}
      ${row('CAE', esc(values.cae))}
    </div></section>
    <section class="sf-card"><h3>Sede</h3><div class="sf-kv">
      ${row('Morada', esc(values.address))}
      ${row('Complemento', esc(values.address_extra))}
      ${row('Cód. postal', esc(values.postal_code))}
      ${row('Localidade', esc(values.city))}
      ${row('Distrito', esc(values.district))}
      ${row('País', esc(values.country))}
      ${row('Telefone', esc(values.phone))}
      ${row('Email', values.email ? `<a href="mailto:${esc(values.email)}">${esc(values.email)}</a>` : '—')}
      ${row('Website', esc(values.website))}
    </div></section>
    <section class="sf-card"><h3>Legal</h3><div class="sf-kv">
      ${row('Conservatória', esc(values.conservatory_no))}
      ${row('Matrícula', esc(values.commercial_registry))}
      ${row('Segurança social', esc(values.social_security_no))}
      ${row('Capital social', values.share_capital ? `${esc(values.share_capital)} ${esc(values.share_capital_currency || 'EUR')}` : '—')}
      ${row('IBAN', esc(values.iban))}
      ${row('BIC / SWIFT', esc(values.bic))}
      ${row('Gerência', esc(values.manager_name))}
      ${row('Moeda', esc(values.currency))}
      ${row('Fuso horário', esc(values.timezone))}
    </div></section>
    <section class="sf-card"><h3>Faturação</h3><div class="sf-kv">
      ${row('Software', esc(p.billing_software || '—'))}
      ${row('Código no software', esc(p.billing_company_code))}
      ${row('URL da API', esc(p.billing_api_url))}
      ${row('Senha das Finanças', secret(company.tax_password_set))}
      ${row('Senha de faturação', secret(company.billing_password_set))}
      ${row('Chave API', secret(company.billing_api_key_set))}
    </div></section>
  </div>`;
}

function editGeralHtml() {
  const software = ctx.software || {options: [{value: 'primavera', label: 'Primavera'}], currentSystem: 'primavera'};
  const values = companyValues(ctx.company || {currency: 'EUR', timezone: 'Europe/Lisbon', status: 'active', country: 'Portugal'}, {billing_software: software.currentSystem});
  return `${renderForm(companyFields(ctx.company, software.options), values, {formClass: 'form-grid company-fiche', includeFooter: false})}
    <div class="form-footer"><button type="button" class="btn" data-co-view>Cancelar</button><button type="submit" class="btn primary" form="record-form">Guardar</button></div>`;
}

async function erpHtml() {
  if (!ctx.companyId) return '<div class="sf-empty"><b>Grave a empresa primeiro</b>Depois configura o ERP neste separador.</div>';
  const [data, catalog] = await Promise.all([
    get(`/integrations/${ctx.companyId}/primavera/status`).catch(() => ({config: {}})),
    get(`/erp/${ctx.companyId}/documents/types`).catch(() => ({system: 'primavera'})),
  ]);
  ctx.erp = data;
  const cfg = data.config || {};
  const ro = ctx.mode === 'view' || !isAdmin();
  const attr = ro ? 'readonly' : '';
  const dis = ro ? 'disabled' : '';
  return `<section class="sf-card"><h3>Sistema de faturação</h3>
      <p class="muted">O TextileFlow envia guias e faturas quando a Web API estiver licenciada.</p>
      <div class="sf-kv">${kv('Estado', data.connected ? 'Ligado' : data.configured ? 'Configurado' : 'Por configurar')}
        ${kv('Palavra-passe', data.password_set ? 'Definida (cifrada)' : 'Não definida')}</div>
      ${!ro ? `<form id="erp-system-form" class="form-grid company-fiche">
        <div class="field"><label>Trabalham com<select name="system">
          <option value="primavera" ${catalog.system === 'primavera' ? 'selected' : ''}>Primavera</option>
          <option value="generic" ${catalog.system === 'generic' ? 'selected' : ''}>TextileFlow / genérico</option>
        </select></label></div>
        <div class="form-footer"><button class="btn" type="submit">Guardar sistema</button></div>
      </form>` : ''}
    </section>
    <section class="sf-card"><h3>Ligação Web API</h3>
      <form id="primavera-form" class="form-grid company-fiche">
        <div class="field"><label>URL da Web API<input name="base_url" value="${esc(cfg.base_url || '')}" ${attr}></label></div>
        <div class="field"><label>Empresa no Primavera<input name="erp_company" value="${esc(cfg.erp_company || '')}" ${attr}></label></div>
        <div class="field"><label>Utilizador técnico<input name="username" value="${esc(cfg.username || '')}" autocomplete="off" ${attr}></label></div>
        <div class="field"><label>Palavra-passe<input name="password" type="password" autocomplete="off" placeholder="${data.password_set ? 'Em branco = manter' : ''}" ${attr}></label></div>
        <div class="field"><label>Tipo documento venda<input name="sales_doc_type" value="${esc(cfg.sales_doc_type || 'FA')}" ${attr}></label></div>
        <div class="field"><label>Série faturas<input name="sales_series" value="${esc(cfg.sales_series || 'A')}" ${attr}></label></div>
        <div class="field"><label>Validar SSL<input name="verify_ssl" type="checkbox" ${cfg.verify_ssl ? 'checked' : ''} ${dis}><span>Desligue só em servidores internos</span></label></div>
        <div class="field"><label>Web API activa<input name="enabled" type="checkbox" ${cfg.enabled ? 'checked' : ''} ${dis}><span>Enviar documentos</span></label></div>
        ${!ro ? `<div class="form-footer">
          <button type="submit" class="btn primary">Guardar ligação</button>
          <button type="button" class="btn" data-erp-test>Testar</button>
        </div>` : ''}
      </form>
    </section>`;
}

async function emailHtml() {
  if (!ctx.companyId) return '<div class="sf-empty"><b>Grave a empresa primeiro</b>Depois configura as caixas de correio.</div>';
  const data = await get(`/mailbox/${ctx.companyId}/accounts`).catch(() => ({items: []}));
  ctx.accounts = data.items || [];
  const editing = ctx.mode === 'edit' && isAdmin();
  const rows = ctx.accounts.map(row => `<tr>
    <td><b>${esc(row.label)}</b><div class="muted">${esc(row.email)}</div></td>
    <td>${badge(row.purpose)}</td>
    <td>${row.can_send ? 'Enviar' : '—'} / ${row.can_read ? 'Ler' : '—'}</td>
    <td>${row.is_default ? badge('predefinida') : ''}</td>
    ${editing ? `<td><button type="button" class="btn small" data-mail-edit="${row.id}">Alterar</button>
      <button type="button" class="btn small" data-mail-test="${row.id}">Testar</button>
      <button type="button" class="btn small" data-mail-inbox="${row.id}">Caixa</button>
      <button type="button" class="btn small danger" data-mail-del="${row.id}">Apagar</button></td>` : `<td><button type="button" class="btn small" data-mail-inbox="${row.id}">Caixa</button></td>`}
  </tr>`).join('') || '<tr><td colspan="5">Ainda sem contas. O programa precisa de SMTP para enviar e IMAP para ler.</td></tr>';
  return `<section class="sf-card"><div class="sf-card-head"><h3>Contas de email da empresa</h3>
      ${editing ? '<button type="button" class="btn primary small" data-mail-new>+ Nova conta</button>' : ''}
    </div>
    <div class="table-wrap"><table class="data-table"><thead><tr><th>Conta</th><th>Finalidade</th><th>Capacidade</th><th></th><th></th></tr></thead><tbody>${rows}</tbody></table></div>
    <div data-mail-form></div>
    <div data-mail-inbox></div>
  </section>`;
}

function mailFields(account = {}) {
  return [
    {key: 'label', label: 'Nome da conta', required: true, default: account.label || 'Caixa principal'},
    {key: 'email', label: 'Endereço', type: 'email', required: true, default: account.email},
    {key: 'from_name', label: 'Nome a mostrar', default: account.from_name},
    {key: 'purpose', label: 'Finalidade', type: 'select', options: [
      {value: 'both', label: 'Enviar e ler'}, {value: 'send', label: 'Só enviar'}, {value: 'read', label: 'Só ler'},
    ], default: account.purpose || 'both'},
    {key: 'smtp_host', label: 'Servidor SMTP', default: account.smtp_host, section: 'Envio'},
    {key: 'smtp_port', label: 'Porta SMTP', type: 'number', default: account.smtp_port || 587, section: 'Envio'},
    {key: 'smtp_security', label: 'Segurança SMTP', type: 'select', options: [
      {value: 'starttls', label: 'STARTTLS'}, {value: 'ssl', label: 'SSL'}, {value: 'none', label: 'Nenhuma'},
    ], default: account.smtp_security || 'starttls', section: 'Envio'},
    {key: 'smtp_user', label: 'Utilizador SMTP', default: account.smtp_user, section: 'Envio'},
    {key: 'password', label: 'Senha de envio', type: 'password', help: account.password_set ? 'Em branco = manter' : 'Guardada cifrada.', section: 'Envio'},
    {key: 'imap_host', label: 'Servidor IMAP', default: account.imap_host, section: 'Leitura'},
    {key: 'imap_port', label: 'Porta IMAP', type: 'number', default: account.imap_port || 993, section: 'Leitura'},
    {key: 'imap_security', label: 'Segurança IMAP', type: 'select', options: [
      {value: 'ssl', label: 'SSL'}, {value: 'starttls', label: 'STARTTLS'}, {value: 'none', label: 'Nenhuma'},
    ], default: account.imap_security || 'ssl', section: 'Leitura'},
    {key: 'imap_user', label: 'Utilizador IMAP', default: account.imap_user, section: 'Leitura'},
    {key: 'imap_password', label: 'Senha de leitura', type: 'password', help: account.imap_password_set ? 'Em branco = manter' : 'Se vazio, usa a senha de envio.', section: 'Leitura'},
    {key: 'imap_folder', label: 'Pasta', default: account.imap_folder || 'INBOX', section: 'Leitura'},
    {key: 'is_default', label: 'Conta predefinida', type: 'checkbox', default: account.is_default, section: 'Leitura'},
    {key: 'signature', label: 'Assinatura', type: 'textarea', full: true, default: account.signature},
  ];
}

function bindHeader() {
  const body = document.getElementById('modal-body');
  body.querySelectorAll('[data-co-tab]').forEach(button => button.addEventListener('click', async () => {
    ctx.tab = button.dataset.coTab;
    if (!ctx.companyId && ctx.tab !== 'geral') { toast('Grave a empresa no Geral primeiro.', 'error'); ctx.tab = 'geral'; }
    await paint();
  }));
  body.querySelector('[data-co-edit]')?.addEventListener('click', async () => { ctx.mode = 'edit'; await paint(); });
  body.querySelector('[data-co-view]')?.addEventListener('click', async () => {
    if (!ctx.companyId) { closeModal(); return; }
    ctx.mode = 'view';
    await paint();
  });
}

async function bindTab() {
  if (ctx.tab === 'geral' && ctx.mode === 'edit') return bindGeralForm();
  if (ctx.tab === 'erp') return bindErp();
  if (ctx.tab === 'email') return bindEmail();
}

function bindGeralForm() {
  const form = document.getElementById('record-form');
  if (!form) return;
  bindPasswordToggles(form);
  bindStatus(form, ctx.company?.status || (ctx.company?.active === false ? 'inactive' : 'active'));
  form.addEventListener('submit', async event => {
    event.preventDefault();
    try {
      const payload = readForm(form, companyFields(ctx.company, ctx.software?.options || []));
      const saved = ctx.companyId
        ? await put(`/admin/companies/${ctx.companyId}`, payload)
        : await post('/admin/companies', payload);
      ctx.companyId = saved.id;
      ctx.company = saved;
      ctx.mode = 'view';
      toast('Empresa guardada.');
      await refreshSession(saved);
      await paint();
    } catch (error) { toast(error.message, 'error'); }
  });
}

function bindStatus(form, initial) {
  const slot = document.getElementById('modal-status-slot');
  if (!slot) return;
  const current = STATUS_LABEL[initial] ? initial : 'active';
  slot.innerHTML = `<div class="co-status" role="group" aria-label="Estado da empresa">${Object.entries(STATUS_LABEL).map(([id, label]) => `<button type="button" class="co-status-btn" data-status="${id}">${label}</button>`).join('')}</div>`;
  let hidden = form.elements.namedItem('status');
  if (!hidden) {
    hidden = document.createElement('input');
    hidden.type = 'hidden';
    hidden.name = 'status';
    form.appendChild(hidden);
  }
  const paintStatus = value => {
    hidden.value = value;
    slot.querySelectorAll('[data-status]').forEach(button => button.classList.toggle('is-on', button.dataset.status === value));
  };
  slot.querySelectorAll('[data-status]').forEach(button => button.addEventListener('click', () => paintStatus(button.dataset.status)));
  paintStatus(current);
}

function bindErp() {
  const body = document.getElementById('modal-body');
  const form = body.querySelector('#primavera-form');
  body.querySelector('#erp-system-form')?.addEventListener('submit', async event => {
    event.preventDefault();
    try {
      await put(`/erp/${ctx.companyId}/erp-system`, {system: event.currentTarget.system.value});
      toast('Sistema de faturação guardado.');
      await paint();
    } catch (error) { toast(error.message, 'error'); }
  });
  form?.addEventListener('submit', async event => {
    event.preventDefault();
    try {
      await put(`/integrations/${ctx.companyId}/primavera/config`, readPrimavera(form));
      toast('Ligação ERP guardada.');
      await paint();
    } catch (error) { toast(error.message, 'error'); }
  });
  body.querySelector('[data-erp-test]')?.addEventListener('click', async () => {
    try {
      await put(`/integrations/${ctx.companyId}/primavera/config`, readPrimavera(form));
      const result = await post(`/integrations/${ctx.companyId}/primavera/test`);
      toast(result.message, result.ok ? 'success' : 'error');
      await paint();
    } catch (error) { toast(error.message, 'error'); }
  });
}

function readPrimavera(form) {
  const data = Object.fromEntries(new FormData(form).entries());
  data.enabled = form.elements.namedItem('enabled')?.checked === true;
  data.verify_ssl = form.elements.namedItem('verify_ssl')?.checked === true;
  if (!data.password) delete data.password;
  return data;
}

function bindEmail() {
  const body = document.getElementById('modal-body');
  body.querySelector('[data-mail-new]')?.addEventListener('click', () => showMailForm(null));
  body.querySelectorAll('[data-mail-edit]').forEach(button => button.addEventListener('click', () => {
    showMailForm(ctx.accounts.find(row => String(row.id) === button.dataset.mailEdit));
  }));
  body.querySelectorAll('[data-mail-del]').forEach(button => button.addEventListener('click', async () => {
    if (!confirm('Apagar esta conta de email?')) return;
    try {
      await remove(`/mailbox/${ctx.companyId}/accounts/${button.dataset.mailDel}`);
      toast('Conta apagada.');
      await paint();
    } catch (error) { toast(error.message, 'error'); }
  }));
  body.querySelectorAll('[data-mail-test]').forEach(button => button.addEventListener('click', async () => {
    try {
      const result = await post(`/mailbox/${ctx.companyId}/accounts/${button.dataset.mailTest}/test`, {});
      toast(result.ok ? 'Ligação ok.' : (result.checks || []).map(item => item.detail).join(' · '), result.ok ? 'success' : 'error');
    } catch (error) { toast(error.message, 'error'); }
  }));
  body.querySelectorAll('[data-mail-inbox]').forEach(button => button.addEventListener('click', () => loadInbox(Number(button.dataset.mailInbox))));
}

function showMailForm(account) {
  const host = document.querySelector('[data-mail-form]');
  if (!host) return;
  const fields = mailFields(account || {});
  host.innerHTML = `<h3>${account ? 'Alterar conta' : 'Nova conta'}</h3>${renderForm(fields, account || {}, {formClass: 'form-grid company-fiche', includeFooter: false})}
    <div class="form-footer"><button type="button" class="btn" data-mail-cancel>Cancelar</button><button type="submit" class="btn primary" form="record-form">Guardar conta</button></div>`;
  bindPasswordToggles(host);
  host.querySelector('[data-mail-cancel]')?.addEventListener('click', () => { host.innerHTML = ''; });
  host.querySelector('#record-form')?.addEventListener('submit', async event => {
    event.preventDefault();
    try {
      const payload = readForm(event.currentTarget, fields);
      if (account) await put(`/mailbox/${ctx.companyId}/accounts/${account.id}`, payload);
      else await post(`/mailbox/${ctx.companyId}/accounts`, payload);
      toast('Conta de email guardada.');
      await paint();
    } catch (error) { toast(error.message, 'error'); }
  });
}

async function loadInbox(accountId) {
  const host = document.querySelector('[data-mail-inbox]');
  if (!host) return;
  host.innerHTML = '<div class="loading">A ler a caixa…</div>';
  try {
    const data = await get(`/mailbox/${ctx.companyId}/accounts/${accountId}/messages?limit=15`);
    const rows = (data.items || []).map(row => `<tr>
      <td>${esc((row.date || '').slice(0, 16).replace('T', ' '))}</td>
      <td>${esc(row.from)}</td>
      <td><b>${esc(row.subject)}</b></td>
      <td>${row.seen ? '' : badge('nova')}</td>
    </tr>`).join('') || '<tr><td colspan="4">Caixa vazia ou pasta sem mensagens.</td></tr>';
    host.innerHTML = `<h3>Últimas mensagens · ${esc(data.folder || 'INBOX')}</h3>
      <div class="table-wrap"><table class="data-table"><thead><tr><th>Data</th><th>De</th><th>Assunto</th><th></th></tr></thead><tbody>${rows}</tbody></table></div>`;
  } catch (error) {
    host.innerHTML = `<div class="empty"><strong>Não foi possível ler a caixa</strong><span>${esc(error.message)}</span></div>`;
  }
}

async function refreshSession(saved) {
  const me = await get('/auth/me');
  setSession(me);
  if (saved?.id) setCompany(saved.id);
  const select = document.getElementById('company-select');
  if (select) select.innerHTML = state.companies.map(company => `<option value="${company.id}" ${Number(company.id) === Number(state.companyId) ? 'selected' : ''}>${esc(company.name)}</option>`).join('');
  if (ctx.onChanged) await ctx.onChanged(saved);
}

function isAdmin() {
  return state.companies.find(row => Number(row.id) === Number(ctx.companyId || state.companyId))?.role === 'admin';
}

function kv(label, value) {
  return `<div><span>${esc(label)}</span><strong>${value || '—'}</strong></div>`;
}

const KNOWN_BILLING = [{value: 'primavera', label: 'Primavera'}, {value: 'generic', label: 'TextileFlow / genérico'}];

async function softwareOptionsFor(company = null) {
  const configured = new Set();
  const id = company?.id || state.companyId;
  let currentSystem = 'primavera';
  if (id) {
    const [pri, catalog] = await Promise.all([
      get(`/integrations/${id}/primavera/status`).catch(() => ({})),
      get(`/erp/${id}/documents/types`).catch(() => ({})),
    ]);
    if (pri.configured || pri.connected || (pri.config && pri.config.base_url)) configured.add('primavera');
    if (catalog.system) { configured.add(catalog.system); currentSystem = catalog.system; }
  }
  if (!configured.size) KNOWN_BILLING.forEach(item => configured.add(item.value));
  return {options: KNOWN_BILLING.filter(item => configured.has(item.value)), currentSystem};
}

function companyFields(company = null, softwareOptions = []) {
  const keep = 'Cifrada no servidor. Em branco = manter.';
  const fresh = 'Guardada cifrada. Não volta a ser mostrada.';
  const locked = Boolean(company?.nif_locked);
  return [
    {key: 'code', label: 'Código', required: true, section: 'Identificação'},
    {key: 'name', label: 'Nome', required: true, section: 'Identificação'},
    {key: 'legal_name', label: 'Firma / denominação', section: 'Identificação'},
    {key: 'legal_form', label: 'Forma jurídica', type: 'select', options: Object.entries(LEGAL_FORM).map(([value, label]) => ({value, label})), section: 'Identificação'},
    {key: 'tax_id', label: 'NIF', required: true, section: 'Identificação', readonly: locked, title: locked ? 'NIF validado. Não pode ser alterado.' : 'NIF português de 9 dígitos.'},
    {key: 'cae', label: 'CAE', section: 'Identificação'},
    {key: 'address', label: 'Morada da sede', type: 'textarea', rows: 2, span: 2, section: 'Sede'},
    {key: 'address_extra', label: 'Complemento', section: 'Sede'},
    {key: 'postal_code', label: 'Cód. postal', section: 'Sede'},
    {key: 'city', label: 'Localidade', section: 'Sede'},
    {key: 'district', label: 'Distrito', section: 'Sede'},
    {key: 'country', label: 'País', section: 'Sede', default: 'Portugal'},
    {key: 'phone', label: 'Telefone', section: 'Sede'},
    {key: 'email', label: 'Email', type: 'email', section: 'Sede'},
    {key: 'website', label: 'Website', section: 'Sede'},
    {key: 'conservatory_no', label: 'Conservatória / CRC', section: 'Legal'},
    {key: 'commercial_registry', label: 'Matrícula / pess. coletiva', section: 'Legal'},
    {key: 'social_security_no', label: 'Segurança social', section: 'Legal'},
    {key: 'share_capital', label: 'Capital social', type: 'money', currencyKey: 'share_capital_currency', currencyDefault: 'EUR', currencies: ['EUR', 'USD', 'GBP', 'CHF'], section: 'Legal'},
    {key: 'iban', label: 'IBAN', span: 2, section: 'Legal'},
    {key: 'bic', label: 'BIC / SWIFT', section: 'Legal'},
    {key: 'manager_name', label: 'Gerência', span: 2, section: 'Legal'},
    {key: 'currency', label: 'Moeda operacional', required: true, section: 'Legal'},
    {key: 'timezone', label: 'Fuso horário', required: true, section: 'Legal'},
    {key: 'status', type: 'hidden'},
    {key: 'billing_software', label: 'Software', type: 'select', options: softwareOptions, section: 'Faturação'},
    {key: 'billing_company_code', label: 'Código no software', section: 'Faturação'},
    {key: 'billing_api_url', label: 'URL da API', span: 2, section: 'Faturação'},
    {key: 'tax_password', label: 'Senha das Finanças', type: 'password', autocomplete: false, section: 'Faturação', placeholder: company?.tax_password_set ? '•••• definida' : '', help: company?.tax_password_set ? keep : fresh},
    {key: 'billing_password', label: 'Senha de faturação', type: 'password', autocomplete: false, section: 'Faturação', placeholder: company?.billing_password_set ? '•••• definida' : '', help: company?.billing_password_set ? keep : fresh},
    {key: 'billing_api_key', label: 'Chave API faturação', type: 'password', autocomplete: false, section: 'Faturação', placeholder: company?.billing_api_key_set ? '•••• definida' : '', help: company?.billing_api_key_set ? keep : fresh},
  ];
}

function companyValues(company = {}, extras = {}) {
  const profile = company.profile || {};
  return {
    country: 'Portugal', ...profile, code: company.code, name: company.name, tax_id: company.tax_id,
    currency: company.currency || 'EUR', timezone: company.timezone || 'Europe/Lisbon',
    status: company.status || (company.active === false ? 'inactive' : 'active'),
    billing_software: profile.billing_software || extras.billing_software || 'primavera',
    share_capital_currency: profile.share_capital_currency || extras.share_capital_currency || company.currency || 'EUR',
  };
}
