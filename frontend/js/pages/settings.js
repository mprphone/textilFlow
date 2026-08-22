import { get, post, put } from '../api.js';
import { options } from '../data.js';
import { renderEntityPage } from '../entity.js?v=20260819-9';
import { badge, datetime, esc } from '../format.js?v=20260819-5';
import { bindPasswordToggles } from '../forms.js?v=20260821-19';
import { recordModal } from '../quick_create.js?v=20260821-19';
import { setCompany, setSession, state } from '../state.js';
import { closeModal, openModal, pageHeader, toast } from '../ui.js?v=20260821-19';
import { CORE_MODULE_IDS, MODULE_ACCESS_OPTIONS, MODULES, PLANT_MODULE_IDS } from '../navigation.js?v=20260822-11';

const tabs=['Campos adaptativos','Modelos de ficha','Fluxos','Tipos de artigo','Utilizadores','Auditoria','Empresas','Integrações'];

export async function render(container,active=0,showTabs=true){
  container.innerHTML=`${showTabs?`<div class="tabs">${tabs.map((label,index)=>`<button class="tab ${index===active?'active':''}" data-settings-tab="${index}">${label}</button>`).join('')}</div>`:''}<div data-settings-panel></div>`;
  const panel=container.querySelector('[data-settings-panel]');
  await renderTab(panel,active);
  container.querySelectorAll('[data-settings-tab]').forEach(button=>button.addEventListener('click',()=>render(container,Number(button.dataset.settingsTab),true)));
}

async function renderTab(panel,index){
  if(index===0)return renderEntityPage(panel,{resource:'field-definitions',title:'Campos adaptativos',subtitle:'Adicione campos sem alterar código; as versões antigas permanecem preservadas.',singular:'campo',newLabel:'Novo campo',fields:[
    {key:'entity_type',label:'Entidade',type:'select',required:true,options:['style','customer','supplier','employee','machine','order']},{key:'field_key',label:'Chave técnica',required:true},{key:'label',label:'Etiqueta',required:true},
    {key:'data_type',label:'Tipo',type:'select',options:['text','number','date','select','textarea','boolean','json'],default:'text'},{key:'section',label:'Secção',default:'Geral'},{key:'display_order',label:'Ordem',type:'number',default:0},
    {key:'options',label:'Opções (JSON)',type:'json',default:[]},{key:'default_value',label:'Valor inicial (JSON)',type:'json'},{key:'required',label:'Obrigatório',type:'checkbox'},{key:'version',label:'Versão',type:'number',default:1},{key:'active',label:'Ativo',type:'checkbox',default:true},
  ],columns:[{key:'entity_type',label:'Entidade',render:r=>badge(r.entity_type)},{key:'field_key',label:'Chave'},{key:'label',label:'Etiqueta'},{key:'data_type',label:'Tipo'},{key:'section',label:'Secção'},{key:'display_order',label:'Ordem'},{key:'version',label:'Versão',render:r=>`V${r.version}`},{key:'required',label:'Obrigatório',render:r=>r.required?'Sim':'Não'},{key:'active',label:'Estado',render:r=>badge(r.active?'ativo':'histórico')}]});
  if(index===1)return renderEntityPage(panel,{resource:'form-templates',title:'Modelos de ficha',subtitle:'Estrutura versionada das fichas por tipo de entidade.',singular:'modelo',newLabel:'Novo modelo',fields:[
    {key:'entity_type',label:'Entidade',required:true},{key:'name',label:'Nome',required:true},{key:'version',label:'Versão',type:'number',default:1},{key:'schema',label:'Estrutura (JSON)',type:'json',default:{sections:['Geral']},full:true},{key:'active',label:'Ativo',type:'checkbox',default:true},
  ],columns:[{key:'entity_type',label:'Entidade'},{key:'name',label:'Modelo'},{key:'version',label:'Versão',render:r=>`V${r.version}`},{key:'schema',label:'Estrutura',render:r=>`<code>${esc(JSON.stringify(r.schema))}</code>`},{key:'active',label:'Estado',render:r=>badge(r.active?'ativo':'histórico')}]});
  if(index===2)return renderEntityPage(panel,{resource:'workflows',title:'Fluxos configuráveis',subtitle:'Etapas de desenvolvimento, produção ou aprovação sem regras rígidas.',singular:'fluxo',newLabel:'Novo fluxo',fields:[
    {key:'entity_type',label:'Entidade',required:true},{key:'name',label:'Nome',required:true},{key:'version',label:'Versão',type:'number',default:1},{key:'stages',label:'Etapas (JSON)',type:'json',default:['novo','em_curso','concluído'],full:true},{key:'active',label:'Ativo',type:'checkbox',default:true},
  ],columns:[{key:'entity_type',label:'Entidade'},{key:'name',label:'Fluxo'},{key:'version',label:'Versão',render:r=>`V${r.version}`},{key:'stages',label:'Etapas',render:r=>(r.stages||[]).map(stage=>`<span class="tag">${esc(stage)}</span>`).join(' ')},{key:'active',label:'Estado',render:r=>badge(r.active?'ativo':'histórico')}]});
  if(index===3)return renderEntityPage(panel,{resource:'article-types',title:'Tipos de artigo',subtitle:'Cada tipo liga um modelo de ficha e um fluxo adequado.',singular:'tipo de artigo',newLabel:'Novo tipo',fields:async()=>[
    {key:'code',label:'Código',required:true},{key:'name',label:'Nome',required:true},{key:'category',label:'Categoria'},{key:'default_unit',label:'Unidade',default:'un'},
    {key:'template_id',label:'Modelo de ficha',type:'select',options:await options('form-templates',r=>`${r.name} V${r.version}`)},{key:'workflow_id',label:'Fluxo',type:'select',options:await options('workflows',r=>`${r.name} V${r.version}`)},{key:'active',label:'Ativo',type:'checkbox',default:true},
  ],columns:[{key:'code',label:'Código'},{key:'name',label:'Tipo'},{key:'category',label:'Categoria'},{key:'default_unit',label:'Unidade'},{key:'template_id',label:'Modelo'},{key:'workflow_id',label:'Fluxo'},{key:'active',label:'Estado',render:r=>badge(r.active?'ativo':'inativo')}]});
  if(index===4)return renderUsers(panel);
  if(index===5)return renderEntityPage(panel,{resource:'audit',readOnly:true,title:'Auditoria',subtitle:'Histórico de alterações, utilizador, entidade e payload.',singular:'evento',fields:[],columns:[{key:'created_at',label:'Data',render:r=>datetime(r.created_at)},{key:'user_id',label:'Utilizador'},{key:'entity',label:'Entidade',render:r=>badge(r.entity)},{key:'entity_id',label:'Registo'},{key:'action',label:'Ação',render:r=>badge(r.action)},{key:'payload',label:'Alteração',render:r=>`<code>${esc(JSON.stringify(r.payload||{}))}</code>`}]});
  if(index===6)return renderCompanies(panel);
  return renderIntegrations(panel);
}

async function renderIntegrations(panel){
  const [data, catalog] = await Promise.all([
    get(`/integrations/${state.companyId}/primavera/status`),
    get(`/erp/${state.companyId}/documents/types`).catch(()=>({system:'primavera'})),
  ]);
  const erpSystem = catalog.system || 'primavera';
  const cfg=data.config||{};
  const canManage=state.companies.find(company=>company.id===state.companyId)?.role==='admin';
  const stateClass=data.connected?'connected':data.configured?'ready':'';
  const stateLabel=data.connected?'Ligado':data.configured?'Configurado, à espera da licença':'Por configurar';
  const outbox=(data.outbox||[]).map(item=>`<tr><td>${esc(item.created_at||'').slice(0,16).replace('T',' ')}</td><td>${badge(item.kind)}</td><td>${badge(item.status)}</td><td>${esc(item.remote_id||item.error||'—')}</td></tr>`).join('')||'<tr><td colspan="4" class="muted">Ainda não há documentos na fila. As expedições entram automaticamente.</td></tr>';
  panel.innerHTML=pageHeader('Integrações ERP','Primavera é o motor fiscal e de stock. O TextileFlow envia guias e faturas quando a Web API estiver licenciada.')+`
    <div class="integration-hero"><div class="integration-brand"><span>P</span><div><small>ERP PRINCIPAL</small><h2>PRIMAVERA v10</h2><p>${esc(data.message)}</p></div></div><span class="integration-state ${stateClass}"><i></i>${esc(stateLabel)}</span></div>
    <section class="card" style="margin-bottom:12px"><div class="card-header"><h2>Sistema de faturação desta empresa</h2><span>Define o ecrã de Documentos</span></div>
      <form id="erp-system-form" class="form-grid">
        <div class="field"><label>Trabalham com<select name="system">
          <option value="primavera" ${erpSystem==='primavera'?'selected':''}>Primavera (tipo FA + série)</option>
          <option value="moloni" ${erpSystem==='moloni'?'selected':''}>Moloni (FT, série do ano)</option>
          <option value="generic" ${erpSystem==='generic'?'selected':''}>Outro / genérico TextileFlow</option>
        </select></label><small class="muted">O separador Documentos usa os códigos e a série desse sistema, para a fábrica não mudar de hábitos.</small></div>
        ${canManage?'<div class="form-footer"><button class="btn primary" type="submit">Guardar sistema</button></div>':''}
      </form>
    </section>
    <div class="integration-grid">
      <section class="card"><div class="card-header"><h2>Ligação Web API</h2><span>${data.password_set?'Palavra-passe gravada cifrada':'Sem palavra-passe'}</span></div>
        <form id="primavera-form" class="form-grid primavera-form">
          <div class="field"><label>URL da Web API<input name="base_url" value="${esc(cfg.base_url||'')}" placeholder="http://SERVIDOR:2018" ${canManage?'':'readonly'}></label><small class="muted">Endereço do serviço Primavera Web API (porta 2018 na instalação típica).</small></div>
          <div class="field"><label>URL do token (opcional)<input name="token_url" value="${esc(cfg.token_url||'')}" placeholder="vazio = URL/token" ${canManage?'':'readonly'}></label></div>
          <div class="field"><label>Empresa no Primavera<input name="erp_company" value="${esc(cfg.erp_company||'')}" placeholder="Código da empresa ERP" ${canManage?'':'readonly'}></label></div>
          <div class="field"><label>Instância<input name="instance" value="${esc(cfg.instance||'DEFAULT')}" ${canManage?'':'readonly'}></label></div>
          <div class="field"><label>Linha<input name="line" value="${esc(cfg.line||'professional')}" placeholder="professional ou executive" ${canManage?'':'readonly'}></label></div>
          <div class="field"><label>Utilizador técnico<input name="username" value="${esc(cfg.username||'')}" autocomplete="off" ${canManage?'':'readonly'}></label></div>
          <div class="field"><label>Palavra-passe<input name="password" type="password" autocomplete="off" placeholder="${data.password_set?'Deixe em branco para manter':''}" ${canManage?'':'readonly'}></label></div>
          <div class="field"><label>Tipo documento venda<input name="sales_doc_type" value="${esc(cfg.sales_doc_type||'FA')}" ${canManage?'':'readonly'}></label></div>
          <div class="field"><label>Série faturas<input name="sales_series" value="${esc(cfg.sales_series||'A')}" ${canManage?'':'readonly'}></label></div>
          <div class="field"><label>Tipo guia<input name="delivery_doc_type" value="${esc(cfg.delivery_doc_type||'GT')}" ${canManage?'':'readonly'}></label></div>
          <div class="field"><label>Série guias<input name="delivery_series" value="${esc(cfg.delivery_series||'A')}" ${canManage?'':'readonly'}></label></div>
          <div class="field"><label>Armazém<input name="warehouse" value="${esc(cfg.warehouse||'')}" ${canManage?'':'readonly'}></label></div>
          <div class="field"><label>Timeout (s)<input name="timeout_seconds" type="number" value="${esc(cfg.timeout_seconds||20)}" ${canManage?'':'readonly'}></label></div>
          <div class="field"><label>Web API activa<input name="enabled" type="checkbox" ${cfg.enabled?'checked':''} ${canManage?'':'disabled'}><span>Enviar documentos quando a licença existir</span></label></div>
          <div class="field"><label>Validar SSL<input name="verify_ssl" type="checkbox" ${cfg.verify_ssl?'checked':''} ${canManage?'':'disabled'}><span>Desligue só em servidores internos com certificado próprio</span></label></div>
          ${canManage?`<div class="form-footer"><button type="submit" class="btn primary">Guardar ligação</button><button type="button" class="btn" data-primavera-test>Testar ligação</button><button type="button" class="btn" data-primavera-flush>Enviar fila</button><button type="button" class="btn" data-primavera-sync>Puxar clientes, artigos e fornecedores</button></div>`:''}
        </form>
      </section>
      <section class="card"><div class="card-header"><h2>O que a API vai tratar</h2><span>${data.pending||0} na fila</span></div>
        <div class="sync-map">${(data.capabilities||[]).map(item=>`<div><i>↔</i><span><b>${esc(item.label)}</b><small>${esc(item.path)}</small></span><em>${item.ready?'Pronto':'À espera'}</em></div>`).join('')}</div>
        <p class="integration-note">Donos: TextileFlow = OF, planeamento e expedição operacional. Primavera = stock, reservas, guias, faturas, contas correntes.</p>
        <p class="integration-note">A fila envia sozinha a cada 2 minutos. Depois de 3 falhas o documento fica em alerta no dashboard e deixa de repetir até clicar em Enviar fila.</p>
      </section>
    </div>
    <section class="card" style="margin-top:12px"><div class="card-header"><h2>Fila para o Primavera</h2><span>Expedições entram aqui mesmo sem licença</span></div>
      <div class="table-wrap"><table class="data-table"><thead><tr><th>Quando</th><th>Documento</th><th>Estado</th><th>Resposta</th></tr></thead><tbody>${outbox}</tbody></table></div>
    </section>`;
  const form=panel.querySelector('#primavera-form');
  form?.addEventListener('submit',async event=>{
    event.preventDefault();
    try{
      await put(`/integrations/${state.companyId}/primavera/config`,readPrimaveraForm(form));
      toast('Ligação Primavera guardada. A palavra-passe fica cifrada no servidor.');
      await renderIntegrations(panel);
    }catch(error){toast(error.message,'error');}
  });
  panel.querySelector('#erp-system-form')?.addEventListener('submit',async event=>{
    event.preventDefault();
    try{
      await put(`/erp/${state.companyId}/erp-system`, {system: event.currentTarget.system.value});
      toast('Sistema de faturação guardado. O ecrã de Documentos passa a usar esses códigos e séries.');
      await renderIntegrations(panel);
    }catch(error){toast(error.message,'error');}
  });
  panel.querySelector('[data-primavera-test]')?.addEventListener('click',async()=>{
    try{
      await put(`/integrations/${state.companyId}/primavera/config`,readPrimaveraForm(form));
      const result=await post(`/integrations/${state.companyId}/primavera/test`);
      toast(result.message, result.ok?'success':'error');
      await renderIntegrations(panel);
    }catch(error){toast(error.message,'error');}
  });
  panel.querySelector('[data-primavera-flush]')?.addEventListener('click',async()=>{
    try{
      const result=await post(`/integrations/${state.companyId}/primavera/flush`);
      toast(`Fila: ${result.sent||0} enviados, ${result.failed||0} com erro.`);
      await renderIntegrations(panel);
    }catch(error){toast(error.message,'error');}
  });
  panel.querySelector('[data-primavera-sync]')?.addEventListener('click',async()=>{
    try{
      const result=await post(`/integrations/${state.companyId}/primavera/sync`,{});
      const summary=(result.results||[]).map(row=>`${row.resource}: ${row.created||0}+ / ${row.updated||0}~`).join(' · ');
      toast(summary || 'Sincronização concluída.');
      await renderIntegrations(panel);
    }catch(error){toast(error.message,'error');}
  });
}

function readPrimaveraForm(form){
  const data=Object.fromEntries(new FormData(form).entries());
  data.enabled=form.elements.namedItem('enabled')?.checked===true;
  data.verify_ssl=form.elements.namedItem('verify_ssl')?.checked===true;
  data.timeout_seconds=Number(data.timeout_seconds||20);
  if(!data.password)delete data.password;
  return data;
}

async function renderUsers(panel){
  const rows=await get(`/admin/${state.companyId}/users`);
  const canManage=state.companies.find(company=>company.id===state.companyId)?.role==='admin';
  const names=Object.fromEntries((state.companies||[]).map(company=>[company.id, company.name]));
  panel.innerHTML=pageHeader('Utilizadores e permissões','Defina quem entra, em que empresas e que operações pode fazer.',canManage?'<button class="btn primary" data-new-user>+ Novo utilizador</button>':'')+`<div class="table-wrap"><table class="data-table"><thead><tr><th>Utilizador</th><th>Nome</th><th>Empresas</th><th>Perfil</th><th>Operações</th><th>Estado</th>${canManage?'<th></th>':''}</tr></thead><tbody>${rows.map(row=>`<tr class="track-row" data-edit-user="${row.id}"><td><b>${esc(row.username)}</b></td><td>${esc(row.full_name)}</td><td>${(row.company_ids||[]).map(id=>`<span class="tag">${esc(names[id]||('#'+id))}</span>`).join(' ')||'—'}</td><td>${badge(row.role)}</td><td>${accessSummary(row.permissions||[])}</td><td>${badge(row.active?'ativo':'inativo')}</td>${canManage?`<td><button class="btn small" type="button">Editar</button></td>`:''}</tr>`).join('')}</tbody></table></div>`;
  panel.querySelector('[data-new-user]')?.addEventListener('click',()=>openUserFiche(panel, null));
  panel.querySelectorAll('[data-edit-user]').forEach(row=>row.addEventListener('click',()=>{
    const found=rows.find(item=>item.id===Number(row.dataset.editUser));
    if (found && canManage) openUserFiche(panel, found);
  }));
}

function userRoles(){return [{value:'admin',label:'Administrador'},{value:'manager',label:'Gestor'},{value:'commercial',label:'Comercial'},{value:'designer',label:'Designer / Produto'},{value:'planner',label:'Planeador'},{value:'supervisor',label:'Supervisor'},{value:'quality',label:'Qualidade'},{value:'warehouse',label:'Armazém / Expedição'},{value:'operator',label:'Operador'},{value:'viewer',label:'Consulta'}];}
function accessSummary(permissions){if(permissions.includes('none'))return '<span class="badge red">Sem módulos</span>';if(permissions.includes('*'))return '<span class="badge blue">Todos os módulos</span>';if(!permissions.length)return '<span class="badge">Pelo perfil</span>';return permissions.map(item=>`<span class="tag">${esc(MODULE_ACCESS_OPTIONS.find(module=>module.id===item)?.label||item)}</span>`).join(' ');}

function moduleBox(module, checked){
  return `<label class="user-row"><span class="user-row-copy">${esc(module.label)}</span><span class="user-switch"><input type="checkbox" data-user-module="${module.id}" ${checked?'checked':''}></span></label>`;
}

function readUserForm(form){
  const useDefaults = form.elements.namedItem('use_profile_defaults')?.checked === true;
  const selected = [...form.querySelectorAll('[data-user-module]:checked')].map(input=>input.dataset.userModule);
  const companyIds = [...form.querySelectorAll('[name="company_ids"]:checked')].map(input=>Number(input.value));
  const password = form.elements.namedItem('password')?.value || '';
  const status = form.elements.namedItem('active')?.value;
  const payload = {
    username: form.elements.namedItem('username')?.value?.trim(),
    full_name: form.elements.namedItem('full_name')?.value?.trim(),
    email: form.elements.namedItem('email')?.value?.trim() || null,
    role: form.elements.namedItem('role')?.value || 'operator',
    active: status !== 'inactive',
    company_ids: companyIds,
    permissions: useDefaults ? [] : (selected.length === MODULE_ACCESS_OPTIONS.length ? ['*'] : (selected.length ? selected : ['none'])),
  };
  if (password) payload.password = password;
  if (!payload.company_ids.includes(Number(state.companyId))) payload.company_ids.unshift(Number(state.companyId));
  return payload;
}

function bindUserStatus(active) {
  const slot = document.getElementById('modal-status-slot');
  const form = document.getElementById('user-fiche');
  if (!slot || !form) return;
  slot.innerHTML = `<div class="co-status" role="group" aria-label="Estado da conta"><button type="button" class="co-status-btn" data-status="active">Ativa</button><button type="button" class="co-status-btn" data-status="inactive">Inativa</button></div>`;
  let hidden = form.elements.namedItem('active');
  if (!hidden) {
    hidden = document.createElement('input');
    hidden.type = 'hidden';
    hidden.name = 'active';
    form.appendChild(hidden);
  }
  const paint = value => {
    hidden.value = value;
    slot.querySelectorAll('[data-status]').forEach(button => button.classList.toggle('is-on', button.dataset.status === value));
  };
  slot.querySelectorAll('[data-status]').forEach(button => button.addEventListener('click', () => paint(button.dataset.status)));
  paint(active === false ? 'inactive' : 'active');
}

async function openUserFiche(panel, account = null){
  const companies = await get('/admin/companies');
  const editing = Boolean(account?.id);
  const selectedCompanies = new Set((account?.company_ids || [state.companyId]).map(Number));
  const permissions = account?.permissions || [];
  const useDefaults = editing ? !permissions.length : true;
  const allModules = permissions.includes('*') || permissions.includes('none') ? [] : permissions;
  const core = MODULES.filter(module => CORE_MODULE_IDS.includes(module.id));
  const plant = MODULES.filter(module => module.plant);
  const roleOptions = userRoles().map(role => `<option value="${role.value}" ${((account?.role)||'operator')===role.value?'selected':''}>${esc(role.label)}</option>`).join('');
  const checked = id => useDefaults ? false : (permissions.includes('*') || allModules.includes(id));
  const companyRows = companies.map(company => {
    const current = Number(company.id) === Number(state.companyId);
    const on = selectedCompanies.has(Number(company.id)) || current;
    return `<label class="user-row"><span class="user-row-copy"><b>${esc(company.name)}</b><small>${esc(company.code)}${current?' · sessão atual':''}</small></span><span class="user-switch"><input type="checkbox" name="company_ids" value="${company.id}" ${on?'checked':''}></span></label>`;
  }).join('');
  openModal(
    editing ? `Editar ${account.full_name}` : 'Novo utilizador',
    `<form id="user-fiche" class="user-fiche">
      <input type="hidden" name="active" value="${account?.active===false?'inactive':'active'}">
      <div class="user-ident">
        <div class="field"><label>Utilizador *<input name="username" required ${editing?'readonly':''} value="${esc(account?.username||'')}" autocomplete="off"></label></div>
        <div class="field"><label>Nome completo *<input name="full_name" required value="${esc(account?.full_name||'')}"></label></div>
        <div class="field"><label>Email<input name="email" type="email" value="${esc(account?.email||'')}"></label></div>
        <div class="field"><label>${editing?'Nova palavra-passe':'Palavra-passe inicial *'}<span class="pw-wrap"><input name="password" type="password" ${editing?'':'required'} minlength="6" autocomplete="new-password" placeholder="${editing?'Em branco = manter':''}"><button type="button" class="pw-toggle" aria-label="Mostrar senha">👁</button></span></label></div>
      </div>
      <nav class="user-tabs" role="tablist">
        <button type="button" class="is-on" data-user-tab="companies">Empresas que pode ver</button>
        <button type="button" data-user-tab="ops">Operações que pode fazer</button>
      </nav>
      <section class="user-pane" data-user-pane="companies">
        <article class="user-panel">
          <header><span>Acesso às empresas</span><small>O utilizador só vê as que estiverem ligadas</small></header>
          <div class="user-rows">${companyRows}</div>
        </article>
      </section>
      <section class="user-pane hidden" data-user-pane="ops">
        <div class="user-ops-head">
          <div class="field"><label>Perfil funcional<select name="role">${roleOptions}</select></label></div>
          <label class="user-defaults"><input name="use_profile_defaults" type="checkbox" ${useDefaults?'checked':''}><span>Usar módulos recomendados para o perfil</span></label>
        </div>
        <div class="user-mod-wrap ${useDefaults?'is-dim':''}" data-mod-wrap>
          <div class="user-panels">
            <article class="user-panel">
              <header><span>Gestão e rasto</span><small>Ecrãs da barra superior</small></header>
              <div class="user-rows user-rows-3">${core.map(module=>moduleBox(module, checked(module.id))).join('')}</div>
            </article>
            <article class="user-panel">
              <header><span>Processos de fábrica</span><small>Só aparecem se a empresa os tiver ativos</small></header>
              <div class="user-rows user-rows-3">${plant.map(module=>moduleBox(module, checked(module.id))).join('')}</div>
            </article>
          </div>
        </div>
      </section>
      <div class="form-footer"><button type="button" class="btn" data-close-modal>Cancelar</button><button type="submit" class="btn primary">Guardar</button></div>
    </form>`,
    editing ? 'Pode gravar e continuar a ajustar empresas e operações.' : 'Depois de gravar a ficha fica aberta para continuar a editar.',
  );
  bindPasswordToggles(document.getElementById('modal-body'));
  bindUserStatus(account?.active !== false);
  const form = document.getElementById('user-fiche');
  form.querySelector('[data-close-modal]').addEventListener('click', closeModal);
  form.querySelectorAll('[data-user-tab]').forEach(button => button.addEventListener('click', () => {
    form.querySelectorAll('[data-user-tab]').forEach(item => item.classList.toggle('is-on', item === button));
    form.querySelectorAll('[data-user-pane]').forEach(pane => pane.classList.toggle('hidden', pane.dataset.userPane !== button.dataset.userTab));
  }));
  const wrap = form.querySelector('[data-mod-wrap]');
  const defaults = form.elements.namedItem('use_profile_defaults');
  const syncDefaults = () => wrap.classList.toggle('is-dim', defaults.checked);
  defaults.addEventListener('change', syncDefaults);
  let editingId = account?.id || null;
  form.addEventListener('submit', async event => {
    event.preventDefault();
    try {
      const payload = readUserForm(form);
      if (!payload || !payload.company_ids || !payload.company_ids.length) throw new Error('Escolha pelo menos uma empresa.');
      if (!editingId && !payload.password) throw new Error('Indique a palavra-passe inicial.');
      const saved = editingId
        ? await put(`/admin/${state.companyId}/users/${editingId}`, payload)
        : await post(`/admin/${state.companyId}/users`, payload);
      editingId = saved && saved.id;
      const title = document.getElementById('modal-title');
      if (title) title.textContent = `Editar ${(saved && saved.full_name) || payload.full_name}`;
      const pass = form.elements.namedItem('password');
      if (pass) { pass.value = ''; pass.required = false; pass.placeholder = 'Em branco = manter'; }
      const userInput = form.elements.namedItem('username');
      if (userInput) userInput.readOnly = true;
      toast('Utilizador guardado.');
      await renderUsers(panel);
    } catch (error) {
      toast(error.message, 'error');
    }
  });
}

function refreshCompanySelect() {
  const select = document.getElementById('company-select');
  if (!select) return;
  select.innerHTML = state.companies.map(company => `<option value="${company.id}" ${Number(company.id) === Number(state.companyId) ? 'selected' : ''}>${esc(company.name)}</option>`).join('');
}

const KNOWN_BILLING_SOFTWARE = [
  {value:'primavera', label:'Primavera'},
  {value:'moloni', label:'Moloni'},
  {value:'generic', label:'TextileFlow / genérico'},
];

async function softwareOptionsFor(company = null) {
  const knownIds = new Set(KNOWN_BILLING_SOFTWARE.map(item => item.value));
  const configured = new Set();
  const id = company?.id || state.companyId;
  let currentSystem = 'primavera';
  if (id) {
    const [pri, catalog] = await Promise.all([
      get(`/integrations/${id}/primavera/status`).catch(() => ({})),
      get(`/erp/${id}/documents/types`).catch(() => ({})),
    ]);
    if (pri.configured || pri.connected || (pri.config && pri.config.base_url)) configured.add('primavera');
    if (catalog.system) {
      configured.add(catalog.system);
      currentSystem = catalog.system;
    }
  }
  if (!configured.size) KNOWN_BILLING_SOFTWARE.forEach(item => configured.add(item.value));
  const stored = String((company?.profile || {}).billing_software || '').trim();
  if (stored) configured.add(knownIds.has(stored.toLowerCase()) ? stored.toLowerCase() : stored);
  const options = KNOWN_BILLING_SOFTWARE.filter(item => configured.has(item.value));
  if (stored && !options.some(item => item.value === stored || item.value === stored.toLowerCase())) {
    options.push({value: stored, label: stored});
  }
  return {options, currentSystem};
}

function companyFields(company = null, softwareOptions = []) {
  const taxSet = Boolean(company?.tax_password_set);
  const apiSet = Boolean(company?.billing_api_key_set);
  const billPassSet = Boolean(company?.billing_password_set);
  const keepSecret = 'Cifrada no servidor. Em branco = manter.';
  const newSecret = 'Guardada cifrada. Não volta a ser mostrada.';
  return [
    {key:'code', label:'Código', required:true, section:'Identificação'},
    {key:'name', label:'Nome', required:true, section:'Identificação'},
    {key:'legal_name', label:'Firma / denominação', section:'Identificação'},
    {key:'legal_form', label:'Forma jurídica', type:'select', options:[
      {value:'lda', label:'Sociedade por quotas (Lda.)'},
      {value:'unipessoal', label:'Unipessoal por quotas'},
      {value:'sa', label:'Sociedade anónima (S.A.)'},
      {value:'eni', label:'Empresário em nome individual'},
      {value:'cooperativa', label:'Cooperativa'},
      {value:'outra', label:'Outra'},
    ], section:'Identificação'},
    {key:'tax_id', label:'NIF', required:true, section:'Identificação', title:'NIF português de 9 dígitos. Pode alterar depois de gravar.'},
    {key:'cae', label:'CAE', section:'Identificação', placeholder:'14100'},
    {key:'address', label:'Morada da sede', type:'textarea', rows:2, span:2, section:'Sede'},
    {key:'address_extra', label:'Complemento', section:'Sede'},
    {key:'postal_code', label:'Cód. postal', section:'Sede', placeholder:'0000-000'},
    {key:'city', label:'Localidade', section:'Sede'},
    {key:'district', label:'Distrito', section:'Sede'},
    {key:'country', label:'País', section:'Sede', default:'Portugal'},
    {key:'phone', label:'Telefone', section:'Sede'},
    {key:'email', label:'Email', type:'email', section:'Sede'},
    {key:'website', label:'Website', section:'Sede'},
    {key:'conservatory_no', label:'Conservatória / CRC', section:'Legal'},
    {key:'commercial_registry', label:'Matrícula / pess. coletiva', section:'Legal'},
    {key:'social_security_no', label:'Segurança social', section:'Legal'},
    {key:'share_capital', label:'Capital social', type:'money', currencyKey:'share_capital_currency', currencyDefault:'EUR', currencies:['EUR','USD','GBP','CHF'], section:'Legal'},
    {key:'iban', label:'IBAN', span:2, section:'Legal'},
    {key:'bic', label:'BIC / SWIFT', section:'Legal'},
    {key:'manager_name', label:'Gerência', span:2, section:'Legal'},
    {key:'currency', label:'Moeda operacional', required:true, section:'Legal'},
    {key:'timezone', label:'Fuso horário', required:true, section:'Legal'},
    {key:'status', type:'hidden'},
    {key:'billing_software', label:'Software', type:'select', options:softwareOptions, section:'Faturação', title:'Só aparecem os sistemas com ligação configurada em Integrações.'},
    {key:'billing_company_code', label:'Código no software', section:'Faturação'},
    {key:'billing_api_url', label:'URL da API', span:2, section:'Faturação'},
    {key:'tax_password', label:'Senha das Finanças', type:'password', autocomplete:false, section:'Faturação', placeholder:taxSet ? '•••• definida' : '', help:taxSet ? keepSecret : newSecret},
    {key:'billing_password', label:'Senha de faturação', type:'password', autocomplete:false, section:'Faturação', placeholder:billPassSet ? '•••• definida' : '', help:billPassSet ? keepSecret : newSecret},
    {key:'billing_api_key', label:'Chave API faturação', type:'password', autocomplete:false, section:'Faturação', placeholder:apiSet ? '•••• definida' : '', help:apiSet ? keepSecret : newSecret},
  ];
}

function companyValues(company = {}, extras = {}) {
  const profile = company.profile || {};
  return {
    country: 'Portugal',
    ...profile,
    code: company.code,
    name: company.name,
    tax_id: company.tax_id,
    currency: company.currency || 'EUR',
    timezone: company.timezone || 'Europe/Lisbon',
    status: company.status || (company.active === false ? 'inactive' : 'active'),
    billing_software: profile.billing_software || extras.billing_software || 'primavera',
    share_capital_currency: profile.share_capital_currency || extras.share_capital_currency || company.currency || 'EUR',
  };
}

const COMPANY_STATUS_OPTIONS = [
  {id:'active', label:'Ativa'},
  {id:'inactive', label:'Inativa'},
  {id:'suspended', label:'Suspensa'},
];

function bindCompanyStatus(initial) {
  const slot = document.getElementById('modal-status-slot');
  const form = document.getElementById('record-form');
  if (!slot || !form) return;
  const current = COMPANY_STATUS_OPTIONS.some(item => item.id === initial) ? initial : 'active';
  slot.innerHTML = `<div class="co-status" role="group" aria-label="Estado da empresa">${COMPANY_STATUS_OPTIONS.map(item => `<button type="button" class="co-status-btn" data-status="${item.id}">${item.label}</button>`).join('')}</div>`;
  let hidden = form.elements.namedItem('status');
  if (!hidden) {
    hidden = document.createElement('input');
    hidden.type = 'hidden';
    hidden.name = 'status';
    form.appendChild(hidden);
  }
  const paint = value => {
    hidden.value = value;
    slot.querySelectorAll('[data-status]').forEach(button => button.classList.toggle('is-on', button.dataset.status === value));
  };
  slot.querySelectorAll('[data-status]').forEach(button => {
    button.addEventListener('click', () => paint(button.dataset.status));
  });
  paint(current);
}

function statusBadge(row) {
  const status = row.status || (row.active === false ? 'inactive' : 'active');
  const labels = {active:'ativa', inactive:'inativa', suspended:'suspensa'};
  return `<span class="badge co-st-${status}">${labels[status] || status}</span>`;
}

async function refreshSessionCompanies() {
  const me = await get('/auth/me');
  setSession(me);
  refreshCompanySelect();
}

async function openCompanyFiche(panel, company = null) {
  let companyId = company?.id || null;
  const software = await softwareOptionsFor(company);
  recordModal({
    title: companyId ? `Editar ${company.name}` : 'Nova empresa',
    subtitle: 'Pode gravar e continuar a editar. O software de faturação vem das ligações em Integrações.',
    formClass: 'form-grid company-fiche',
    stayOpen: true,
    values: companyValues(company || {currency:'EUR', timezone:'Europe/Lisbon', status:'active', country:'Portugal'}, {billing_software: software.currentSystem}),
    fields: companyFields(company, software.options),
    save: payload => {
      if (companyId) return put(`/admin/companies/${companyId}`, payload);
      return post('/admin/companies', payload).then(saved => {
        companyId = saved.id;
        const title = document.getElementById('modal-title');
        if (title && saved.name) title.textContent = `Editar ${saved.name}`;
        return saved;
      });
    },
    onSaved: async saved => {
      await refreshSessionCompanies();
      if (saved?.id) setCompany(saved.id);
      refreshCompanySelect();
      await renderCompanies(panel);
    },
  });
  bindCompanyStatus((company && company.status) || (company && company.active === false ? 'inactive' : 'active'));
}

async function renderCompanies(panel){
  const rows=await get('/admin/companies');
  const current=rows.find(row=>Number(row.id)===Number(state.companyId))||rows[0];
  const enabled=new Set(current?.enabled_modules||[]);
  const core=MODULES.filter(module=>!module.plant);
  const plant=MODULES.filter(module=>module.plant);
  const box=(module,checked)=>`<label class="module-switch ${checked?'on':''}"><input type="checkbox" data-company-module="${module.id}" ${checked?'checked':''}><span><b>${esc(module.label)}</b><small>${module.plant?'Processo interno de fábrica':'Módulo de gestão e rasto'}</small></span></label>`;
  panel.innerHTML=pageHeader('Empresas e módulos','Crie empresas, altere os dados e escolha os módulos de cada uma. O seletor no topo troca o ambiente em que está a trabalhar.','<button class="btn" data-edit-company>Editar dados</button><button class="btn primary" data-new-company>+ Nova empresa</button>')+`
    ${current?`<section class="card company-modules"><div class="card-header"><div><h2>${esc(current.name)}</h2><span>${esc(current.code)} · ${esc(current.tax_id || 'sem NIF')} · ${esc(current.currency)} · ${esc(current.timezone)}</span></div><button class="btn primary" data-save-modules>Guardar módulos</button></div>
      <h3>Gestão e rasto</h3><div class="module-grid">${core.map(module=>box(module,enabled.has(module.id))).join('')}</div>
      <h3>Processos internos</h3><p class="muted">Ative só o que esta fábrica faz. O que ficar desligado não aparece na barra e o trabalho sai por subcontrato.</p>
      <div class="module-grid">${plant.map(module=>box(module,enabled.has(module.id))).join('')}</div>
    </section>`:''}
    <div class="table-wrap" style="margin-top:12px"><table class="data-table"><thead><tr><th></th><th>Código</th><th>Empresa</th><th>NIF</th><th>Moeda</th><th>Módulos de processo</th><th>Estado</th></tr></thead><tbody>${rows.map(row=>`<tr class="track-row ${Number(row.id)===Number(current?.id)?'is-current':''}" data-open-company="${row.id}"><td>${Number(row.id)===Number(current?.id)?'<b>Atual</b>':'Abrir'}</td><td><b>${esc(row.code)}</b></td><td>${esc(row.name)}</td><td>${esc(row.tax_id||'—')}</td><td>${esc(row.currency)}</td><td>${(row.enabled_modules||[]).filter(id=>PLANT_MODULE_IDS.includes(id)).map(id=>`<span class="tag">${esc(MODULES.find(module=>module.id===id)?.label||id)}</span>`).join(' ')||'<span class="muted">Sem processos extra</span>'}</td><td>${statusBadge(row)}</td></tr>`).join('')}</tbody></table></div>`;
  panel.querySelector('[data-new-company]').addEventListener('click',()=>openCompanyFiche(panel));
  panel.querySelector('[data-edit-company]')?.addEventListener('click',()=>{
    if (!current) return;
    openCompanyFiche(panel, current);
  });
  panel.querySelectorAll('[data-open-company]').forEach(row=>row.addEventListener('click',()=>{
    setCompany(row.dataset.openCompany);
    refreshCompanySelect();
    renderCompanies(panel);
  }));
  panel.querySelector('[data-save-modules]')?.addEventListener('click',async()=>{
    const selected=[...panel.querySelectorAll('[data-company-module]:checked')].map(input=>input.dataset.companyModule);
    try{
      const saved=await put(`/admin/companies/${current.id}`,{enabled_modules:selected});
      const membership=state.companies.find(row=>Number(row.id)===Number(current.id));
      if(membership)membership.enabled_modules=saved.enabled_modules||selected;
      toast('Módulos da empresa atualizados.');
      location.reload();
    }catch(error){
      toast(error.message, 'error');
    }
  });
}
