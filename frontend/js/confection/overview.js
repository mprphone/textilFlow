import { crudList, get, post } from '../api.js';
import { date, esc, money, number, percent, progress } from '../format.js?v=20260826-3';
import { state } from '../state.js';
import { toast } from '../ui.js?v=20260826-3';

function loadClass(value) {
  return value > 100 ? 'capacity-danger' : value >= 90 ? 'capacity-warning' : 'capacity-good';
}

function scenarioMarkup(result) {
  const recommended = result.recommended_scenario;
  return `<div class="capacity-result-head"><div><span>Resultado para ${esc(result.style.reference)}</span><strong>${number(result.quantity)} peças · SAM ${number(result.sam_minutes)} min</strong></div><span>Entrega pretendida ${date(result.requested_date)}</span></div><div class="scenario-grid">${result.scenarios.map((row,index)=>`<div class="scenario-card ${row.feasible?'feasible':'not-feasible'} ${index===recommended?'recommended':''}">${index===recommended?'<span class="scenario-tag">RECOMENDADO</span>':''}<h3>${esc(row.name)}</h3><p><b>${number(row.internal_quantity)}</b> internas + <b>${number(row.external_quantity)}</b> externas</p><strong>${row.completion_date?date(row.completion_date):'Sem capacidade'}</strong><small>${row.feasible?'Entrega possível':'Fora da data pedida'} · ${money(row.unit_cost)}/peça</small></div>`).join('')}</div>`;
}

export async function renderOverview(container) {
  const [data, styles] = await Promise.all([
    get(`/confection/${state.companyId}/overview?weeks=8`),
    crudList('styles', state.companyId, 'limit=2000'),
  ]);
  const metrics = data.metrics;
  const futureDate = new Date(); futureDate.setDate(futureDate.getDate() + 30);
  container.innerHTML = `<div class="confection-overview">
    <section class="capacity-hero">
      <div>
        <span>CAPACIDADE DE HOJE</span>
        <h2>${percent(metrics.occupancy_pct)} ocupada</h2>
        <p>Para saber o que foi feito, tem de inserir as peças do dia. O custo sai do vencimento da costureira.</p>
        <div class="capacity-hero-actions">
          <a class="btn primary" href="#/confection-diary">＋ Inserir produção do dia</a>
          <a class="btn" href="#/confection-map">Abrir mapa</a>
        </div>
      </div>
      <div class="capacity-hero-gauge ${loadClass(metrics.occupancy_pct)}"><strong>${percent(metrics.occupancy_pct)}</strong><small>${number(metrics.confirmed_minutes)} / ${number(metrics.effective_minutes)} min</small></div>
    </section>
    <div class="metric-grid confection-metrics">
      <div class="metric"><span class="label">Pessoas hoje</span><strong>${number(metrics.present_employees)}</strong><span class="trend">${number(metrics.scheduled_employees)} previstas</span></div>
      <div class="metric"><span class="label">Minutos livres</span><strong>${number(Math.max(0, metrics.effective_minutes - metrics.confirmed_minutes))}</strong><span class="trend">depois do plano confirmado</span></div>
      <div class="metric"><span class="label">Produção hoje</span><strong>${number(metrics.actual_good_units)}</strong><span class="trend">${metrics.actual_good_units ? `${number(metrics.actual_rejected_units)} rejeitadas` : 'ainda sem registo'} · <a href="#/confection-diary">inserir</a></span></div>
      <div class="metric"><span class="label">Máquinas</span><strong>${number(metrics.machines_available)}/${number(metrics.machines_total)}</strong><span class="trend">disponíveis</span></div>
    </div>
    <section class="card capacity-weeks"><div class="card-header"><h2>Ocupação nas próximas semanas</h2><span>Verde folga · amarelo cheio · vermelho não cabe</span></div><div class="week-strip">${data.weekly.map((row,index)=>`<div class="week-capacity ${loadClass(row.potential_load_pct)}"><span>${index===0?'Esta semana':`Semana +${index}`}</span><strong>${percent(row.potential_load_pct)}</strong><small>${number(Math.max(0,row.free_minutes))} min livres</small><div>${progress(row.potential_load_pct,row.potential_load_pct>100?'red':'green')}</div></div>`).join('')}</div></section>
    <div class="grid-2 capacity-main-grid">
      <section class="card"><div class="card-header"><h2>Por linha, hoje</h2><span>${date(data.date)} · <a href="#/confection-map">abrir mapa</a></span></div><div class="table-wrap"><table class="data-table"><thead><tr><th>Linha</th><th>Pessoas</th><th>Carga</th><th>Livre</th></tr></thead><tbody>${data.today_lines.map(row=>`<tr><td><b>${esc(row.line_name)}</b></td><td>${number(row.present_employees)}/${number(row.scheduled_employees)}</td><td><b class="${loadClass(row.potential_load_pct)}-text">${percent(row.potential_load_pct)}</b>${progress(row.potential_load_pct,row.potential_load_pct>100?'red':'green')}</td><td>${number(row.free_minutes)} min</td></tr>`).join('')||'<tr><td colspan="4"><div class="empty"><strong>Sem linhas</strong>Crie as linhas em <a href="#/confection-lines">Linhas de produção</a>.</div></td></tr>'}</tbody></table></div></section>
      <section class="card capacity-check"><div class="card-header"><h2>Posso aceitar esta encomenda?</h2><span>Simula sem mexer no plano</span></div><form data-capacity-check><label>Artigo<select name="style_id" required><option value="">Selecionar…</option>${styles.map(row=>`<option value="${row.id}">${esc(row.reference)} · ${esc(row.description)}</option>`).join('')}</select></label><div><label>Quantidade<input name="quantity" type="number" min="1" value="1200" required></label><label>Entrega pretendida<input name="requested_date" type="date" value="${futureDate.toISOString().slice(0,10)}" required></label></div><button class="btn primary wide">Analisar capacidade</button></form></section>
    </div>
    <section class="card capacity-result hidden" data-capacity-result></section>
    <section class="card"><div class="card-header"><h2>Alertas</h2><span>Linhas acima de 90%</span></div><div class="alert-list">${data.alerts.map(row=>`<div class="alert-item ${row.severity==='danger'?'danger':'warning'}"><strong>${esc(row.title)}</strong><span>${date(row.date)}</span></div>`).join('')||'<div class="empty"><strong>Sem sobrecargas</strong>Há folga no horizonte analisado.</div>'}</div></section>
  </div>`;
  container.querySelector('[data-capacity-check]').addEventListener('submit', async event => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const button = event.currentTarget.querySelector('button'); button.disabled = true; button.textContent = 'A calcular…';
    try {
      const result = await post('/confection/capacity-check',{company_id:state.companyId,style_id:Number(form.get('style_id')),quantity:Number(form.get('quantity')),requested_date:form.get('requested_date')});
      const target=container.querySelector('[data-capacity-result]');target.innerHTML=scenarioMarkup(result);target.classList.remove('hidden');target.scrollIntoView({behavior:'smooth',block:'nearest'});
    } catch (error) { toast(error.message, 'error'); }
    finally { button.disabled=false;button.textContent='Analisar capacidade'; }
  });
}
