import { options } from '../data.js';
import { renderEntityPage } from '../entity.js?v=20260819-9';
import { badge, esc, money } from '../format.js?v=20260819-5';

export async function render(container) {
  const skills = await options('skill-types', 'name', 'name');
  await renderEntityPage(container, {
    resource:'employees', title:'Pessoas da confeção', subtitle:'Nome, vencimento e custo/hora. O custo real da produção usa estes valores.',
    singular:'funcionário', newLabel:'Novo funcionário',
    transform: payload => {
      const skill = payload.skill_pick;
      delete payload.skill_pick;
      return {...payload, skills: skill ? [skill] : []};
    },
    fields: async row => [
      {key:'code',label:'Código',required:true,section:'Identificação'},{key:'name',label:'Nome',required:true,section:'Identificação'},
      {key:'job_title',label:'Função',section:'Identificação'},{key:'badge_code',label:'Código do cartão',section:'Identificação'},
      {key:'department_id',label:'Departamento',type:'select',options:await options('departments','name'),section:'Organização'},
      {key:'line_id',label:'Linha / célula',type:'select',options:await options('production-lines','name'),section:'Organização'},
      {key:'monthly_salary',label:'Vencimento mensal (€)',type:'number',default:0,section:'Custos e tempo',help:'O custo/hora calcula-se sozinho: vencimento ÷ (horas semanais × 52 ÷ 12).'},
      {key:'weekly_hours',label:'Horas semanais',type:'number',default:40,section:'Custos e tempo'},
      {key:'hourly_cost',label:'Custo por hora (€)',type:'number',default:0,section:'Custos e tempo',help:'Preenchido automaticamente a partir do vencimento. Pode ajustar à mão se precisar.'},
      {key:'skill_pick',label:'Competência',type:'select',options:skills,default:(row?.skills||[])[0]||'',section:'Competência',help:'A lista edita-se em Configurar → Competências.'},
      {key:'active',label:'Estado',type:'checkbox',default:true,help:'Funcionário ativo',section:'Estado'},
    ],
    columns:[
      {key:'code',label:'Código'},{key:'name',label:'Nome'},{key:'job_title',label:'Função'},
      {key:'department_id',label:'Dept.'},{key:'line_id',label:'Linha'},
      {key:'monthly_salary',label:'Vencimento',render:r=>money(r.monthly_salary)},
      {key:'hourly_cost',label:'Custo/h',render:r=>money(r.hourly_cost)},
      {key:'skills',label:'Competência',render:r=>esc((r.skills||[])[0]||'—')},
      {key:'active',label:'Estado',render:r=>badge(r.active?'ativo':'inativo')},
    ],
  });
}
