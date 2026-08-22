import { get } from '../api.js';
import { options } from '../data.js';
import { renderEntityTabs } from '../entity.js?v=20260822-1';
import { badge, datetime, esc, number } from '../format.js?v=20260819-5';
import { state } from '../state.js';
import { toast } from '../ui.js?v=20260820-5';

function aqlCalculatorHtml() {
  return `<div class="card" style="margin-bottom:16px">
    <div class="card-header"><h2>Calculadora de amostragem AQL</h2><span>Sugestão rápida de amostra e critério de aceitação</span></div>
    <div class="form-grid">
      <label>Tamanho do lote<input type="number" data-aql-lot value="500" min="1"></label>
      <label>AQL (%)<input type="number" data-aql-pct value="2.5" step="0.1" min="0"></label>
      <label>Nível de inspeção<select data-aql-level><option value="I">I (reduzido)</option><option value="II" selected>II (normal)</option><option value="III">III (rigoroso)</option></select></label>
      <button class="btn primary" data-aql-calc style="align-self:end">Calcular</button>
    </div>
    <div data-aql-result class="muted" style="margin-top:10px">Indique o tamanho do lote e calcule.</div>
  </div>`;
}

function bindAqlCalculator(container) {
  container.querySelector('[data-aql-calc]')?.addEventListener('click', async () => {
    const lot = Number(container.querySelector('[data-aql-lot]').value || 0);
    const pct = Number(container.querySelector('[data-aql-pct]').value || 2.5);
    const level = container.querySelector('[data-aql-level]').value;
    const result = container.querySelector('[data-aql-result]');
    try {
      const plan = await get(`/quality/${state.companyId}/aql-plan?lot_size=${lot}&aql_pct=${pct}&inspection_level=${level}`);
      result.innerHTML = `Amostra: <b>${plan.sample_size}</b> peças (código ${esc(plan.code_letter)}) · Aceitar até <b>${plan.accept_max_defects}</b> defeito(s) · Rejeitar a partir de <b>${plan.reject_min_defects}</b> · <small>${esc(plan.note)}</small>`;
    } catch (error) { toast(error.message, 'error'); }
  });
}

export async function render(container){
  container.innerHTML = aqlCalculatorHtml() + '<div data-quality-tabs></div>';
  bindAqlCalculator(container);
  await renderEntityTabs(container.querySelector('[data-quality-tabs]'), [
    {
      label: 'Inspeções',
      config: {
        resource:'quality-inspections',title:'Qualidade e defeitos',subtitle:'Inspeção inline/final, AQL, causa, severidade e decisão.',singular:'inspeção',newLabel:'Nova inspeção',fields:async()=>[
          {key:'production_order_id',label:'Ordem',type:'select',options:await options('production-orders','order_no')},{key:'batch_id',label:'Lote',type:'select',options:await options('batches','batch_no')},{key:'operation_id',label:'Operação',type:'select',options:await options('operations','name')},
          {key:'employee_id',label:'Inspetor',type:'select',options:await options('employees','name')},{key:'machine_id',label:'Máquina',type:'select',options:await options('machines','name')},{key:'supplier_id',label:'Fornecedor',type:'select',options:await options('suppliers','name')},
          {key:'inspection_type',label:'Tipo',type:'select',options:['incoming','inline','endline','final','aql'],default:'inline'},{key:'inspected_quantity',label:'Inspecionadas',type:'number',default:0},{key:'defect_quantity',label:'Defeitos',type:'number',default:0},
          {key:'defect_code',label:'Código defeito'},{key:'severity',label:'Severidade',type:'select',options:['minor','major','critical'],default:'minor'},{key:'result',label:'Resultado',type:'select',options:['pending','passed','conditional','failed'],default:'pending',help:'"Reprovado" bloqueia a expedição das ordens associadas.'},
          {key:'notes',label:'Observações',type:'textarea',full:true},{key:'photos',label:'Fotografias (JSON/URLs)',type:'json',default:[],full:true},
        ],columns:[{key:'created_at',label:'Data',render:r=>datetime(r.created_at)},{key:'production_order_id',label:'OF'},{key:'batch_id',label:'Lote'},{key:'inspection_type',label:'Tipo'},{key:'inspected_quantity',label:'Inspec.',render:r=>number(r.inspected_quantity)},{key:'defect_quantity',label:'Defeitos',render:r=>number(r.defect_quantity)},{key:'defect_code',label:'Código'},{key:'severity',label:'Severidade',render:r=>badge(r.severity)},{key:'result',label:'Resultado',render:r=>badge(r.result)}]
      },
    },
    {
      label: 'Ações corretivas',
      config: {
        resource:'corrective-actions',title:'Ações corretivas (CAPA)',subtitle:'Causa, ação, responsável, prazo e verificação de eficácia por inspeção.',singular:'ação corretiva',newLabel:'Nova ação corretiva',fields:async()=>[
          {key:'quality_inspection_id',label:'Inspeção',type:'select',required:true,options:await options('quality-inspections',r=>`#${r.id} · ${r.inspection_type} · ${r.defect_code||'sem código'} · ${r.severity}`)},
          {key:'responsible_employee_id',label:'Responsável',type:'select',options:await options('employees','name')},
          {key:'root_cause',label:'Causa raiz',type:'textarea',full:true},{key:'action',label:'Ação corretiva',type:'textarea',full:true},
          {key:'due_date',label:'Prazo',type:'date'},{key:'status',label:'Estado',type:'select',options:['open','in_progress','verified','closed'],default:'open'},
          {key:'effectiveness_notes',label:'Verificação de eficácia',type:'textarea',full:true},
        ],columns:[{key:'created_at',label:'Aberta em',render:r=>datetime(r.created_at)},{key:'quality_inspection_id',label:'Inspeção'},{key:'root_cause',label:'Causa'},{key:'action',label:'Ação'},{key:'due_date',label:'Prazo'},{key:'status',label:'Estado',render:r=>badge(r.status)}]
      },
    },
  ]);
}
