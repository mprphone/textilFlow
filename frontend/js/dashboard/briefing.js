import { badge, esc, money, number, percent, progress } from '../format.js?v=20260819-5';

function greeting() {
  const hour = new Date().getHours();
  return hour < 12 ? 'Bom dia' : hour < 20 ? 'Boa tarde' : 'Boa noite';
}

export function briefingHero(data, userName = '') {
  const briefing = data.briefing;
  const firstName = String(userName || '').split(' ')[0];
  return `<section class="decision-hero">
    <div class="decision-copy"><span class="decision-eyebrow">BRIEFING OPERACIONAL · AGORA</span><h1>${greeting()}${firstName ? `, ${esc(firstName)}` : ''}.</h1><p>${esc(briefing.narrative)}</p>
      <div class="decision-chips"><span class="${briefing.critical_count ? 'danger' : ''}"><b>${briefing.critical_count}</b> críticos</span><span class="${briefing.warning_count ? 'warning' : ''}"><b>${briefing.warning_count}</b> avisos</span><span><b>${briefing.cost_risks}</b> riscos de custo</span></div>
    </div>
    <div class="health-score" style="--score:${briefing.health_score * 3.6}deg"><div><strong>${briefing.health_score}</strong><span>Saúde da operação</span></div></div>
  </section>`;
}

export function priorityPanel(briefing) {
  const priorities = briefing.priorities.slice(0, 5);
  return `<section class="card priority-card"><div class="card-header"><div><h2>O que precisa da sua atenção</h2><span>Ordenado por impacto no prazo, custo e operação</span></div><span class="live-label"><i></i> atualizado</span></div>
    <div class="priority-list">${priorities.length ? priorities.map((item, index) => `<article class="priority-item ${item.severity}">
      <span class="priority-number">${index + 1}</span><div><span class="priority-area">${esc(item.area)}</span><h3>${esc(item.title)}</h3><p>${esc(item.explanation)}</p></div>
      <button class="btn small" data-go-route="${item.route}">${esc(item.action)} →</button>
    </article>`).join('') : '<div class="all-clear"><span>✓</span><div><b>Não existem prioridades críticas</b><p>A operação está dentro dos parâmetros definidos.</p></div></div>'}</div>
  </section>`;
}

export function quickWorkflows() {
  return `<section class="quick-workflows"><button data-go-route="tracking"><span>▶</span><b>Controlo</b><small>Onde está cada OF</small></button><button data-go-route="corte"><span>✂</span><b>Corte</b><small>Mesas e Gantt</small></button><button data-go-route="confection-map"><span>▦</span><b>Confeção</b><small>Mapa e carga das linhas</small></button><button data-go-route="subcontracts"><span>⇄</span><b>Subcontratos</b><small>O que está fora</small></button><button data-go-route="shipping"><span>▰</span><b>Expedição</b><small>O que pode sair</small></button><button data-go-route="costing"><span>€</span><b>Proposta</b><small>Aceitar trabalho</small></button></section>`;
}

export function metricCards(data) {
  return `<section class="metric-grid smart-metrics">
    <div class="metric"><span class="metric-icon blue">▤</span><span class="label">Ordens ativas</span><strong>${number(data.orders_active)}</strong><span class="trend">em execução ou planeadas</span></div>
    <div class="metric"><span class="metric-icon ${data.orders_at_risk ? 'red' : 'green'}">!</span><span class="label">Prazos em risco</span><strong>${number(data.orders_at_risk)}</strong><span class="trend ${data.orders_at_risk ? 'bad' : ''}">${data.orders_at_risk ? 'exigem decisão' : 'sem atrasos previstos'}</span></div>
    <div class="metric"><span class="metric-icon violet">↗</span><span class="label">Plano concluído</span><strong>${percent(data.completion_pct)}</strong><span class="trend">${number(data.completed_quantity)} peças</span></div>
    <div class="metric"><span class="metric-icon green">✓</span><span class="label">Qualidade à primeira</span><strong>${percent(data.quality_rate)}</strong><span class="trend">produção aceite</span></div>
    <div class="metric"><span class="metric-icon amber">€</span><span class="label">Custo direto registado</span><strong>${money(data.direct_cost)}</strong><span class="trend">pessoas + máquinas</span></div>
  </section>`;
}

export function orderFlow(data) {
  return `<section class="card order-flow"><div class="card-header"><div><h2>Encomendas em movimento</h2><span>Onde estão e quanto falta</span></div><button class="link-button" data-go-route="tracking">Ver rasto →</button></div>
    <div class="order-flow-list">${data.orders.length ? data.orders.slice(0, 6).map(order => `<article><div class="order-identity"><b>${esc(order.order_no)}</b><span>${esc(order.reference)} · ${esc(order.description)}</span></div><div class="order-stage"><span>${esc(order.stage)}</span><small>${esc(order.location || 'Local por definir')}</small></div><div class="order-progress">${progress(order.progress, order.progress >= 80 ? 'green' : '')}</div><div class="order-due"><span>Entrega</span><b>${esc(order.planned_end || 'Por definir')}</b></div><div>${badge(order.status)}</div></article>`).join('') : '<div class="empty"><strong>Sem ordens ativas</strong>Crie a primeira encomenda para iniciar o fluxo.</div>'}</div>
  </section>`;
}

export function lineOverview(lines) {
  return `<section class="card"><div class="card-header"><div><h2>Ritmo da confeção</h2><span>Produção real por linha ou célula</span></div><button class="link-button" data-go-route="live">Abrir tempo real →</button></div><div class="factory-lines">${lines.map(line => `<article><div><b>${esc(line.name)}</b><span>${badge(line.efficiency >= line.target ? 'No objetivo' : 'Abaixo do objetivo')}</span></div><strong>${percent(line.efficiency)}</strong><div class="line-bar"><i style="width:${Math.min(100, line.efficiency)}%"></i><em style="left:${Math.min(100, line.target)}%"></em></div><footer><span>${number(line.good)} boas</span><span>${number(line.hours)} h registadas</span><span>objetivo ${percent(line.target)}</span></footer></article>`).join('')}</div></section>`;
}
