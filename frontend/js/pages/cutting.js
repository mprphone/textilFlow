import { crudList } from '../api.js';
import { renderEntityPage } from '../entity.js?v=20260819-9';
import { badge, money, number } from '../format.js?v=20260819-5';
import { options } from '../data.js';
import { renderProductionMap } from '../confection/map.js?v=20260822-15';
import { state } from '../state.js';

export async function renderMap(container) {
  await renderProductionMap(container, 'cutting');
}

export async function renderLines(container) {
  const departments = await crudList('departments', state.companyId, 'limit=200');
  const corte = departments.find(row => ['COR', 'CORTE', 'CUT'].includes(row.code) || (row.name || '').toLowerCase().includes('corte'));
  const opts = departments.map(row => ({value: row.id, label: row.name}));
  await renderEntityPage(container, {
    resource: 'production-lines',
    query: [corte ? `department_id=${corte.id}` : '', 'active=true'].filter(Boolean).join('&'),
    title: 'Mesas de corte',
    subtitle: 'Linhas do departamento Corte. Se existirem máquinas de corte, o mapa usa as máquinas como mesas.',
    singular: 'mesa',
    newLabel: 'Nova mesa',
    transform: payload => ({...payload, department_id: payload.department_id || corte?.id, active: payload.active !== false}),
    fields: [
      {key: 'code', label: 'Código', required: true},
      {key: 'name', label: 'Nome', required: true},
      {key: 'department_id', label: 'Departamento', type: 'select', options: opts, default: corte?.id},
      {key: 'production_mode', label: 'Modo', type: 'select', options: ['batch', 'line', 'cell', 'piece'], default: 'batch'},
      {key: 'capacity_minutes_day', label: 'Minutos disponíveis/dia', type: 'number', default: 480},
      {key: 'target_pcs_hour', label: 'Peças/hora', type: 'number', default: 0},
      {key: 'target_efficiency', label: 'Eficiência objetivo (%)', type: 'number', default: 88},
      {key: 'active', label: 'Ativa', type: 'checkbox', default: true},
    ],
    columns: [
      {key: 'code', label: 'Código'},
      {key: 'name', label: 'Mesa'},
      {key: 'production_mode', label: 'Modo', render: r => badge(r.production_mode)},
      {key: 'capacity_minutes_day', label: 'Min/dia', render: r => number(r.capacity_minutes_day)},
      {key: 'target_pcs_hour', label: 'Peças/h', render: r => number(r.target_pcs_hour)},
      {key: 'active', label: 'Estado', render: r => badge(r.active ? 'ativa' : 'inativa')},
    ],
  });
}

export async function render(container){
  await renderEntityPage(container,{resource:'cutting-jobs',title:'Sala de corte',subtitle:'Estendimentos, planos, lotes, cortadores, máquinas, desperdício e custo real.',singular:'trabalho de corte',newLabel:'Novo trabalho de corte',fields:async()=>[
    {key:'production_order_id',label:'Ordem de fabrico',type:'select',required:true,options:await options('production-orders','order_no'),section:'Ordem'},{key:'batch_id',label:'Lote',type:'select',options:await options('batches','batch_no'),section:'Ordem'},
    {key:'cutter_employee_id',label:'Cortador(a)',type:'select',options:await options('employees','name'),section:'Recursos'},{key:'machine_id',label:'Máquina',type:'select',options:await options('machines','name'),section:'Recursos'},
    {key:'marker_code',label:'Plano / marcador',section:'Plano'},{key:'fabric_lot',label:'Lote de tecido',section:'Plano'},{key:'layers',label:'Folhas',type:'number',default:0,section:'Plano'},
    {key:'planned_pieces',label:'Peças planeadas',type:'number',default:0,section:'Resultado'},{key:'good_pieces',label:'Peças boas',type:'number',default:0,section:'Resultado'},{key:'rejected_pieces',label:'Rejeitadas',type:'number',default:0,section:'Resultado'},
    {key:'planned_fabric',label:'Tecido planeado',type:'number',default:0,section:'Consumo'},{key:'actual_fabric',label:'Tecido real',type:'number',default:0,section:'Consumo'},
    {key:'duration_minutes',label:'Duração (min)',type:'number',default:0,section:'Tempo e custo'},{key:'status',label:'Estado',type:'select',options:['planned','in_progress','completed','cancelled'],default:'planned',section:'Tempo e custo'},
    {key:'started_at',label:'Início',type:'datetime-local',section:'Tempo e custo'},{key:'ended_at',label:'Fim',type:'datetime-local',section:'Tempo e custo'},
  ],columns:[{key:'production_order_id',label:'OF'},{key:'marker_code',label:'Plano'},{key:'fabric_lot',label:'Lote tecido'},{key:'cutter_employee_id',label:'Cortador(a)'},{key:'machine_id',label:'Máquina'},{key:'layers',label:'Folhas',render:r=>number(r.layers)},{key:'good_pieces',label:'Boas',render:r=>number(r.good_pieces)},{key:'rejected_pieces',label:'Rejeitadas',render:r=>number(r.rejected_pieces)},{key:'waste_pct',label:'Desperdício',render:r=>`${number(r.waste_pct)}%`},{key:'duration_minutes',label:'Tempo',render:r=>`${number(r.duration_minutes)} min`},{key:'labor_cost',label:'M.O.',render:r=>money(r.labor_cost)},{key:'machine_cost',label:'Máquina',render:r=>money(r.machine_cost)},{key:'status',label:'Estado',render:r=>badge(r.status)}]});
}
