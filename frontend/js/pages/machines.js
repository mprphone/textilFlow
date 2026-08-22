import { get, crudList } from '../api.js';
import { options } from '../data.js';
import { renderEntityPage } from '../entity.js?v=20260819-9';
import { badge, date, esc, money, number } from '../format.js?v=20260819-5';
import { state } from '../state.js';

export async function render(container) {
  const typeOptions = await options('machine-types','name','code');
  const tabs = [
    {label:'Máquinas',config:{resource:'machines',title:'Máquinas e equipamentos',subtitle:'Capacidade, custo, estado, IoT e manutenção.',singular:'máquina',newLabel:'Nova máquina',fields:async()=>[
      {key:'code',label:'Código',required:true},{key:'name',label:'Nome',required:true},{key:'machine_type',label:'Tipo',type:'select',required:true,options:typeOptions,help:'A lista edita-se em Tipos de máquina.'},
      {key:'department_id',label:'Departamento',type:'select',options:await options('departments','name')},{key:'line_id',label:'Linha',type:'select',options:await options('production-lines','name')},
      {key:'manufacturer',label:'Fabricante'},{key:'model',label:'Modelo'},{key:'serial_no',label:'N.º série'},
      {key:'hourly_cost',label:'Custo/hora',type:'number',default:0},{key:'target_units_hour',label:'Objetivo un./h',type:'number',default:0},
      {key:'status',label:'Estado',type:'select',options:['available','running','maintenance','stopped'],default:'available'},
      {key:'next_maintenance',label:'Próxima manutenção',type:'date'},{key:'iot_identifier',label:'Identificador IoT',help:'Só como referência — não há hoje nenhuma integração automática que leia este identificador.'},{key:'active',label:'Ativa',type:'checkbox',default:true},
    ],columns:[{key:'code',label:'Código'},{key:'name',label:'Máquina'},{key:'machine_type',label:'Tipo'},{key:'line_id',label:'Linha'},{key:'hourly_cost',label:'Custo/h',render:r=>money(r.hourly_cost)},{key:'target_units_hour',label:'Objetivo/h',render:r=>number(r.target_units_hour)},{key:'next_maintenance',label:'Manutenção',render:r=>date(r.next_maintenance)},{key:'status',label:'Estado',render:r=>badge(r.status)}]}},
    {label:'Linhas / células',config:{resource:'production-lines',title:'Linhas e células',subtitle:'Modos de produção e capacidade diária.',singular:'linha',newLabel:'Nova linha',fields:async()=>[
      {key:'code',label:'Código',required:true},{key:'name',label:'Nome',required:true},{key:'department_id',label:'Departamento',type:'select',options:await options('departments','name')},
      {key:'production_mode',label:'Modo',type:'select',options:['line','cell','batch','piece'],default:'line'},
      {key:'capacity_minutes_day',label:'Minutos disponíveis/dia',type:'number',default:0},{key:'target_pcs_hour',label:'Peças/hora',type:'number',default:0},{key:'target_efficiency',label:'Eficiência objetivo (%)',type:'number',default:85},
      {key:'wip_limit',label:'Limite WIP kanban',type:'number',default:0,help:'0 = sem limite. Número máximo de lotes que a linha pode ter em simultâneo no kanban corte→costura.'},
      {key:'kanban_pull_enabled',label:'Kanban pull ativo',type:'checkbox',default:false,help:'Se ativo, a linha aparece no painel kanban e pode puxar lotes do corte.'},
      {key:'active',label:'Ativa',type:'checkbox',default:true},
    ],columns:[{key:'code',label:'Código'},{key:'name',label:'Nome'},{key:'production_mode',label:'Modo',render:r=>badge(r.production_mode)},{key:'capacity_minutes_day',label:'Capacidade',render:r=>`${number(r.capacity_minutes_day)} min/dia`},{key:'target_pcs_hour',label:'Peças/h',render:r=>number(r.target_pcs_hour)},{key:'wip_limit',label:'WIP',render:r=>r.wip_limit||'∞'},{key:'kanban_pull_enabled',label:'Kanban',render:r=>badge(r.kanban_pull_enabled?'ativo':'inativo')},{key:'active',label:'Estado',render:r=>badge(r.active?'ativa':'inativa')}]},
    {label:'Departamentos',config:{resource:'departments',title:'Departamentos e centros de custo',subtitle:'Estrutura fabril e imputação de custos indiretos.',singular:'departamento',newLabel:'Novo departamento',fields:async()=>[
      {key:'facility_id',label:'Unidade',type:'select',options:await options('facilities','name')},{key:'code',label:'Código',required:true},{key:'name',label:'Nome',required:true},{key:'cost_center',label:'Centro de custo'},{key:'hourly_overhead',label:'Custo indireto/h',type:'number',default:0},{key:'active',label:'Ativo',type:'checkbox',default:true},
    ],columns:[{key:'code',label:'Código'},{key:'name',label:'Departamento'},{key:'cost_center',label:'Centro custo'},{key:'hourly_overhead',label:'Indireto/h',render:r=>money(r.hourly_overhead)},{key:'active',label:'Estado',render:r=>badge(r.active?'ativo':'inativo')}]}},
  ];
  container.innerHTML = `<div class="tabs factory-tabs"><button class="tab active" data-factory-tab="floor">Planta da fábrica</button>${tabs.map((tab,index)=>`<button class="tab" data-factory-tab="${index}">${tab.label}</button>`).join('')}</div><div data-factory-panel></div>`;
  const panel = container.querySelector('[data-factory-panel]');
  await renderFactoryFloor(panel);
  container.querySelector('.factory-tabs').addEventListener('click', async event => {
    const button = event.target.closest('[data-factory-tab]');
    if (!button) return;
    container.querySelectorAll('[data-factory-tab]').forEach(item=>item.classList.toggle('active',item===button));
    if (button.dataset.factoryTab === 'floor') await renderFactoryFloor(panel);
    else await renderEntityPage(panel,tabs[Number(button.dataset.factoryTab)].config);
  });
}

async function renderFactoryFloor(container) {
  const [machines, lines, departments, live] = await Promise.all([
    crudList('machines',state.companyId,'limit=2000'), crudList('production-lines',state.companyId,'limit=2000'),
    crudList('departments',state.companyId,'limit=2000'), get(`/production/${state.companyId}/live`).catch(()=>({assignments:[]})),
  ]);
  const assignments = live.assignments || [];
  const lineMap = Object.fromEntries(lines.map(row=>[row.id,row]));
  const activeByMachine = Object.fromEntries(assignments.filter(row=>['in_progress','running','active'].includes(row.status)).map(row=>[row.machine_id,row]));
  const saved = JSON.parse(localStorage.getItem(`tf_factory_layout_${state.companyId}`) || '{}');
  const sectors = departments.length ? departments : [{id:'all',name:'Produção',code:'PROD'}];
  const statusLabel = {running:'Em funcionamento',available:'Disponível',maintenance:'Manutenção',stopped:'Parada'};
  const effectiveStatus = machine => activeByMachine[machine.id] ? 'running' : machine.status;
  const running = machines.filter(machine=>effectiveStatus(machine)==='running').length;
  const stopped = machines.filter(machine=>['maintenance','stopped'].includes(effectiveStatus(machine))).length;
  const occupiedSectors = sectors.filter(sector=>machines.some(machine=>String(machine.department_id)===String(sector.id))).length;
  container.innerHTML = `<div class="factory-head">
    <div><h1>Planta da fábrica</h1><p>Visão em tempo real da ocupação, fluxo e estado do parque industrial.</p></div>
    <div class="actions"><button class="btn" data-reset-layout>Repor posições</button><button class="btn primary" data-edit-layout>Editar planta</button></div>
  </div>
  <div class="factory-kpis">
    <div><span>Máquinas ativas</span><strong>${running}<small> / ${machines.length}</small></strong><i class="factory-dot running"></i></div>
    <div><span>Setores ocupados</span><strong>${occupiedSectors}<small> / ${sectors.length}</small></strong><i class="factory-dot available"></i></div>
    <div><span>Alertas</span><strong>${stopped}</strong><small>${stopped===1?'equipamento requer atenção':'equipamentos requerem atenção'}</small></div>
    <div><span>Ocupação global</span><strong>${machines.length?Math.round(running/machines.length*100):0}%</strong><div class="factory-meter"><i style="width:${machines.length?running/machines.length*100:0}%"></i></div></div>
  </div>
  <div class="factory-toolbar"><div class="factory-legend"><b>Estado</b><button class="active" data-status="all">Todos <em>${machines.length}</em></button><button data-status="running"><i class="running"></i>Em funcionamento</button><button data-status="available"><i class="available"></i>Disponível</button><button data-status="maintenance"><i class="maintenance"></i>Manutenção</button><button data-status="stopped"><i class="stopped"></i>Parada</button></div><label class="factory-search">⌕ <input placeholder="Procurar máquina…" data-factory-search></label></div>
  <div class="factory-layout-wrap"><div class="factory-layout" data-factory-layout>${sectors.map((sector,sectorIndex)=>{
    const sectorMachines=machines.filter(machine=>String(machine.department_id)===String(sector.id) || (!machine.department_id && sectorIndex===0));
    const sectorRunning=sectorMachines.filter(machine=>effectiveStatus(machine)==='running').length;
    const occupancy=sectorMachines.length?Math.round(sectorRunning/sectorMachines.length*100):0;
    return `<section class="factory-sector" data-sector="${sector.id}"><header><div><span>${esc(sector.code||`S${sectorIndex+1}`)}</span><h2>${esc(sector.name)}</h2></div><div class="sector-load"><b>${occupancy}%</b><small>ocupação</small><div class="factory-meter"><i style="width:${occupancy}%"></i></div></div></header><div class="sector-canvas">${sectorMachines.map((machine,index)=>{
      const pos=saved[machine.id]||{x:7+(index%4)*23,y:12+Math.floor(index/4)*36}; const status=effectiveStatus(machine); const task=activeByMachine[machine.id];
      return `<button class="machine-node ${status}" style="left:${pos.x}%;top:${pos.y}%" data-machine="${machine.id}" data-status-value="${status}" data-search-value="${esc(`${machine.code} ${machine.name}`.toLowerCase())}" aria-label="${esc(machine.name)} — ${statusLabel[status]||status}"><span class="machine-icon">${machineGlyph(machine.machine_type)}</span><span class="machine-copy"><b>${esc(machine.code)}</b><small>${esc(machine.name)}</small>${task?`<em>${esc(task.order_no||'Em produção')}</em>`:''}</span><i></i></button>`;
    }).join('') || '<div class="sector-empty">Sem máquinas atribuídas</div>'}</div></section>`;
  }).join('')}</div><aside class="machine-inspector" data-machine-inspector><button aria-label="Fechar detalhe" data-close-inspector>×</button><div data-inspector-body></div></aside></div>
  <p class="factory-hint">Selecione uma máquina para ver detalhes. Ative “Editar planta” para arrastar equipamentos.</p>`;

  let editing=false, filter='all', search='';
  const applyFilters=()=>container.querySelectorAll('.machine-node').forEach(node=>{node.hidden=!((filter==='all'||node.dataset.statusValue===filter)&&node.dataset.searchValue.includes(search));});
  container.querySelectorAll('[data-status]').forEach(button=>button.addEventListener('click',()=>{container.querySelectorAll('[data-status]').forEach(item=>item.classList.toggle('active',item===button));filter=button.dataset.status;applyFilters();}));
  container.querySelector('[data-factory-search]').addEventListener('input',event=>{search=event.target.value.toLowerCase().trim();applyFilters();});
  container.querySelector('[data-edit-layout]').addEventListener('click',event=>{editing=!editing;container.querySelector('[data-factory-layout]').classList.toggle('editing',editing);event.currentTarget.textContent=editing?'Concluir edição':'Editar planta';event.currentTarget.classList.toggle('success',editing);});
  container.querySelector('[data-reset-layout]').addEventListener('click',()=>{localStorage.removeItem(`tf_factory_layout_${state.companyId}`);renderFactoryFloor(container);});
  container.querySelector('[data-close-inspector]').addEventListener('click',()=>container.querySelector('.factory-layout-wrap').classList.remove('inspecting'));
  container.querySelectorAll('.machine-node').forEach(node=>{
    node.addEventListener('click',()=>showMachine(node));
    node.addEventListener('pointerdown',event=>startDrag(event,node));
  });
  function showMachine(node){const machine=machines.find(row=>row.id===Number(node.dataset.machine));const task=activeByMachine[machine.id];const line=lineMap[machine.line_id];const status=effectiveStatus(machine);container.querySelector('[data-inspector-body]').innerHTML=`<span class="machine-status ${status}">${statusLabel[status]||status}</span><div class="inspector-machine-icon">${machineGlyph(machine.machine_type)}</div><h2>${esc(machine.name)}</h2><p>${esc(machine.code)} · ${esc(machine.machine_type||'Equipamento')}</p><dl><div><dt>Setor / linha</dt><dd>${esc(line?.name||'Sem linha')}</dd></div><div><dt>Objetivo</dt><dd>${number(machine.target_units_hour)} un./h</dd></div><div><dt>Custo</dt><dd>${money(machine.hourly_cost)}/h</dd></div><div><dt>Próxima manutenção</dt><dd>${date(machine.next_maintenance)}</dd></div></dl>${task?`<div class="inspector-task"><span>Produção atual</span><b>${esc(task.order_no)}</b><small>${esc(task.operation||'Operação em curso')} · ${number(task.completed_quantity||0)}/${number(task.planned_quantity||0)} un.</small><div class="factory-meter"><i style="width:${Math.min(100,(task.completed_quantity||0)/(task.planned_quantity||1)*100)}%"></i></div></div>`:'<div class="inspector-task idle"><span>Sem tarefa ativa</span><b>Máquina disponível</b><small>Pronta para receber uma nova ordem.</small></div>'}<a class="btn primary wide" href="#/floor">Abrir terminal de produção</a>`;container.querySelector('.factory-layout-wrap').classList.add('inspecting');}
  function startDrag(event,node){if(!editing)return;event.preventDefault();const canvas=node.parentElement;node.setPointerCapture(event.pointerId);const move=e=>{const rect=canvas.getBoundingClientRect();const x=Math.max(1,Math.min(82,(e.clientX-rect.left)/rect.width*100));const y=Math.max(2,Math.min(72,(e.clientY-rect.top)/rect.height*100));node.style.left=`${x}%`;node.style.top=`${y}%`;};const up=()=>{node.removeEventListener('pointermove',move);const layout=JSON.parse(localStorage.getItem(`tf_factory_layout_${state.companyId}`)||'{}');layout[node.dataset.machine]={x:parseFloat(node.style.left),y:parseFloat(node.style.top)};localStorage.setItem(`tf_factory_layout_${state.companyId}`,JSON.stringify(layout));};node.addEventListener('pointermove',move);node.addEventListener('pointerup',up,{once:true});}
}

function machineGlyph(type='') {
  const value=type.toLowerCase();
  if(value.includes('cut')) return '✂';
  if(value.includes('spread')) return '▰';
  if(value.includes('press')) return '◆';
  return '⌁';
}
