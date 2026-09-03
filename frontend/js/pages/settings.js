import { get, post, put } from '../api.js';
import { options } from '../data.js';
import { renderEntityPage } from '../entity.js?v=20260826-3';
import { badge, datetime, esc } from '../format.js?v=20260826-3';
import { bindPasswordToggles } from '../forms.js?v=20260826-3';
import { recordModal } from '../quick_create.js?v=20260826-3';
import { setCompany, setSession, state } from '../state.js';
import { closeModal, openModal, pageHeader, toast } from '../ui.js?v=20260826-3';
import { CORE_MODULE_IDS, MODULE_ACCESS_OPTIONS, MODULES, PLANT_MODULE_IDS } from '../navigation.js?v=20260828-2';
import { render as renderArticleTypes } from './article_types.js?v=20260826-3';
import { openCompanyFiche } from './company_fiche.js?v=20260826-3';

const tabs=['Campos adaptativos','Modelos de ficha','Fluxos','Tipos de peças','Utilizadores','Auditoria','Empresas'];

export async function render(container,active=0,showTabs=true){
  container.innerHTML=`${showTabs?`<div class="tabs">${tabs.map((label,index)=>`<button class="tab ${index===active?'active':''}" data-settings-tab="${index}">${label}</button>`).join('')}</div>`:''}<div data-settings-panel></div>`;
  const panel=container.querySelector('[data-settings-panel]');
  await renderTab(panel,active);
  container.querySelectorAll('[data-settings-tab]').forEach(button=>button.addEventListener('click',()=>render(container,Number(button.dataset.settingsTab),true)));
}

async function renderTab(panel,index){
  if(index===3)return renderArticleTypes(panel);
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
  if(index===4)return renderUsers(panel);
  if(index===5)return renderEntityPage(panel,{resource:'audit',readOnly:true,title:'Auditoria',subtitle:'Histórico de alterações, utilizador, entidade e payload.',singular:'evento',fields:[],columns:[{key:'created_at',label:'Data',render:r=>datetime(r.created_at)},{key:'user_id',label:'Utilizador'},{key:'entity',label:'Entidade',render:r=>badge(r.entity)},{key:'entity_id',label:'Registo'},{key:'action',label:'Ação',render:r=>badge(r.action)},{key:'payload',label:'Alteração',render:r=>`<code>${esc(JSON.stringify(r.payload||{}))}</code>`}]});
  return renderCompanies(panel);
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

function statusBadge(row) {
  const status = row.status || (row.active === false ? 'inactive' : 'active');
  const labels = {active:'ativa', inactive:'inativa', suspended:'suspensa'};
  return `<span class="badge co-st-${status}">${labels[status] || status}</span>`;
}

async function renderCompanies(panel){
  const rows=await get('/admin/companies');
  const current=rows.find(row=>Number(row.id)===Number(state.companyId))||rows[0];
  const enabled=new Set(current?.enabled_modules||[]);
  const core=MODULES.filter(module=>!module.plant);
  const plant=MODULES.filter(module=>module.plant);
  const box=(module,checked)=>`<label class="module-switch ${checked?'on':''}"><input type="checkbox" data-company-module="${module.id}" ${checked?'checked':''}><span><b>${esc(module.label)}</b><small>${module.plant?'Processo interno de fábrica':'Módulo de gestão e rasto'}</small></span></label>`;
  panel.innerHTML=pageHeader('Empresas e módulos','Crie empresas, altere os dados e escolha os módulos de cada uma. O seletor no topo troca o ambiente em que está a trabalhar.','<button class="btn" data-edit-company>Visualizar dados</button><button class="btn primary" data-new-company>+ Nova empresa</button>')+`
    ${current?`<section class="card company-modules"><div class="card-header"><div><h2>${esc(current.name)}</h2><span>${esc(current.code)} · ${esc(current.tax_id || 'sem NIF')} · ${esc(current.currency)} · ${esc(current.timezone)}</span></div><button class="btn primary" data-save-modules>Guardar módulos</button></div>
      <h3>Gestão e rasto</h3><div class="module-grid">${core.map(module=>box(module,enabled.has(module.id))).join('')}</div>
      <h3>Processos internos</h3><p class="muted">Ative só o que esta fábrica faz. O que ficar desligado não aparece na barra e o trabalho sai por subcontrato.</p>
      <div class="module-grid">${plant.map(module=>box(module,enabled.has(module.id))).join('')}</div>
    </section>`:''}
    <div class="table-wrap u-mt-3"><table class="data-table"><thead><tr><th></th><th>Código</th><th>Empresa</th><th>NIF</th><th>Moeda</th><th>Módulos de processo</th><th>Estado</th></tr></thead><tbody>${rows.map(row=>`<tr class="track-row ${Number(row.id)===Number(current?.id)?'is-current':''}" data-open-company="${row.id}"><td>${Number(row.id)===Number(current?.id)?'<b>Atual</b>':'Abrir'}</td><td><b>${esc(row.code)}</b></td><td>${esc(row.name)}</td><td>${esc(row.tax_id||'—')}</td><td>${esc(row.currency)}</td><td>${(row.enabled_modules||[]).filter(id=>PLANT_MODULE_IDS.includes(id)).map(id=>`<span class="tag">${esc(MODULES.find(module=>module.id===id)?.label||id)}</span>`).join(' ')||'<span class="muted">Sem processos extra</span>'}</td><td>${statusBadge(row)}</td></tr>`).join('')}</tbody></table></div>`;
  panel.querySelector('[data-new-company]').addEventListener('click',()=>openCompanyFiche(panel, null, ()=>renderCompanies(panel)));
  panel.querySelector('[data-edit-company]')?.addEventListener('click',()=>{
    if (!current) return;
    openCompanyFiche(panel, current, ()=>renderCompanies(panel));
  });
  const selectedNow=()=>[...panel.querySelectorAll('[data-company-module]:checked')].map(input=>input.dataset.companyModule).sort().join(',');
  const initialModules=selectedNow();
  panel.querySelectorAll('[data-open-company]').forEach(row=>row.addEventListener('click',()=>{
    if(selectedNow()!==initialModules && !confirm('Há módulos por guardar. Trocar de empresa na mesma?')) return;
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
