import { get, post } from '../api.js';
import { options } from '../data.js';
import { badge, date, esc, number } from '../format.js?v=20260826-3';
import { recordModal } from '../quick_create.js';
import { state } from '../state.js';
import { pageHeader } from '../ui.js?v=20260826-3';

const KIND = {
  dyeing: 'dyeing', printing: 'printing', weaving: 'weaving', spinning: 'spinning',
  corte: 'corte', laundry: 'laundry', embroidery: 'embroidery', finishing: 'finishing',
};

export async function render(container, moduleId) {
  const kind = KIND[moduleId] || moduleId;
  const data = await get(`/process/${state.companyId}/${kind}/cockpit`);
  const plant = data.plant || {};
  const counts = data.counts || {};
  const jobs = data.jobs || [];
  const orders = data.orders || [];
  const outside = data.outside || [];
  const machines = data.machines || [];
  const people = data.people || [];
  container.innerHTML = pageHeader(
    plant.label || 'Processo',
    `${plant.resource || 'Processo interno desta fábrica'}. Pessoas, máquinas e trabalhos deste módulo.`,
    `<a class="btn" href="#/tracking">Rasto das OF</a><a class="btn" href="#/subcontracts">Subcontratos</a><button class="btn primary" data-new-job>+ Novo trabalho</button>`,
    'compact',
  ) + `
    <div class="track-kpis process-kpis">
      <div><span>Trabalhos abertos</span><strong>${number(counts.open_jobs)}</strong></div>
      <div><span>OF neste processo</span><strong>${number(counts.orders)}</strong></div>
      <div><span>Ainda fora (subcontrato)</span><strong>${number(counts.outside)}</strong></div>
      <div><span>Máquinas</span><strong>${number(counts.machines)}</strong></div>
      <div><span>Pessoas</span><strong>${number(counts.people)}</strong></div>
    </div>
    <section class="listing-panel"><div class="card-header" style="padding:8px 10px"><h2>Trabalhos internos</h2><span>${esc(plant.noun || 'trabalho')}</span></div>
      <div class="table-wrap listing-table"><table class="data-table"><thead><tr><th>Ref.</th><th>OF</th><th>Qtd.</th><th>Concluído</th><th>Un.</th><th>Estado</th><th>Data</th></tr></thead>
      <tbody>${jobs.length ? jobs.map(job => `<tr><td><b>${esc(job.reference)}</b></td><td>${esc(orders.find(row => row.id === job.production_order_id)?.order_no || '—')}</td><td>${number(job.quantity)}</td><td>${number(job.completed_quantity)}</td><td>${esc(job.unit)}</td><td>${badge(job.status)}</td><td>${date(job.planned_date)}</td></tr>`).join('') : '<tr><td colspan="7"><div class="empty"><strong>Sem trabalhos internos</strong>Crie o primeiro trabalho deste processo.</div></td></tr>'}</tbody></table></div>
    </section>
    <div class="dossier-grid u-mt-3">
      <section class="listing-panel"><div class="card-header" style="padding:8px 10px"><h2>OF no processo</h2></div>
        <div class="table-wrap listing-table"><table class="data-table"><thead><tr><th>OF</th><th>Artigo</th><th>Qtd.</th><th>Fase</th></tr></thead>
        <tbody>${orders.length ? orders.map(row => `<tr><td><b>${esc(row.order_no)}</b></td><td>${esc(row.reference ? `${row.reference} · ${row.description}` : '—')}</td><td>${number(row.quantity)}</td><td>${badge(row.current_stage)}</td></tr>`).join('') : '<tr><td colspan="4"><div class="empty"><strong>Nenhuma OF nesta fase</strong>Distribua quantidade para este processo no rasto da produção.</div></td></tr>'}</tbody></table></div>
      </section>
      <section class="listing-panel"><div class="card-header" style="padding:8px 10px"><h2>Ainda em subcontrato</h2></div>
        <div class="table-wrap listing-table"><table class="data-table"><thead><tr><th>Guia</th><th>Serviço</th><th>Qtd. fora</th><th>Estado</th></tr></thead>
        <tbody>${outside.length ? outside.map(job => `<tr><td><b>${esc(job.reference)}</b></td><td>${esc(job.service_name || '—')}</td><td>${number(job.out_quantity || job.quantity)}</td><td>${badge(job.status)}</td></tr>`).join('') : '<tr><td colspan="4"><div class="empty"><strong>Nada fora</strong>Este processo corre em casa, ou ainda não há envios.</div></td></tr>'}</tbody></table></div>
      </section>
    </div>
    <div class="dossier-grid u-mt-3">
      <section class="listing-panel"><div class="card-header" style="padding:8px 10px"><h2>Máquinas</h2><a class="btn small" href="#/machines">Abrir cadastro</a></div>
        <div class="table-wrap listing-table"><table class="data-table"><tbody>${machines.length ? machines.map(row => `<tr><td><b>${esc(row.code)}</b></td><td>${esc(row.name)}</td><td>${badge(row.status || '—')}</td></tr>`).join('') : '<tr><td colspan="3" class="muted">Ainda sem máquinas associadas a este processo. Cadastre-as em Máquinas.</td></tr>'}</tbody></table></div>
      </section>
      <section class="listing-panel"><div class="card-header" style="padding:8px 10px"><h2>Pessoas</h2><a class="btn small" href="#/people">Abrir cadastro</a></div>
        <div class="table-wrap listing-table"><table class="data-table"><tbody>${people.length ? people.map(row => `<tr><td><b>${esc(row.code)}</b></td><td>${esc(row.name)}</td><td>${esc(row.job_title || '—')}</td></tr>`).join('') : '<tr><td colspan="3" class="muted">Ainda sem pessoas neste processo. Cadastre-as em Pessoas.</td></tr>'}</tbody></table></div>
      </section>
    </div>`;

  container.querySelector('[data-new-job]').addEventListener('click', async () => {
    const orderOptions = await options('production-orders', 'order_no');
    recordModal({
      title: `Novo trabalho · ${plant.label}`,
      values: {unit: plant.unit || 'un', status: 'planned', quantity: 0},
      fields: [
        {key:'reference', label:'Referência', required:true, section:'Trabalho'},
        {key:'production_order_id', label:'Ordem de fabrico', type:'select', options:orderOptions, section:'Trabalho'},
        {key:'quantity', label:'Quantidade', type:'number', required:true, section:'Trabalho'},
        {key:'unit', label:'Unidade', section:'Trabalho'},
        {key:'planned_date', label:'Data', type:'date', section:'Trabalho'},
        {key:'status', label:'Estado', type:'select', options:['planned','in_progress','paused','completed','cancelled'], section:'Trabalho'},
        {key:'notes', label:'Notas', type:'textarea', full:true, section:'Trabalho'},
      ],
      save: payload => post(`/process/${state.companyId}/${kind}/jobs`, payload),
      onSaved: () => render(container, moduleId),
    });
  });
}
