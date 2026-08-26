import { get, patch, post, remove } from '../api.js?v=20260826-3';
import { bindPhotoFields, readForm, renderForm } from '../forms.js?v=20260826-3';
import { badge, date, esc, money, number, percent } from '../format.js?v=20260826-3';
import { state } from '../state.js';
import { loading, openModal, toast } from '../ui.js?v=20260826-3';

const TABS = [
  {id: 'geral', label: 'Geral'},
  {id: 'servicos', label: 'Serviços e Preços'},
  {id: 'curso', label: 'Trabalhos em Curso'},
  {id: 'compras', label: 'Histórico de Compras'},
  {id: 'desempenho', label: 'Desempenho'},
  {id: 'ocorrencias', label: 'Ocorrências & Comunicação'},
  {id: 'documentos', label: 'Documentos'},
];

const KIND_TONE = {
  reclamacao: 'danger', incidencia: 'warn', qualidade: 'danger', atraso: 'warn',
  comunicacao: 'info', telefonema: 'info', email: 'info', reuniao: 'ok',
  nota: 'muted', acordo: 'ok', preco: 'warn', outro: 'muted',
};
const PROBLEM_KINDS = ['reclamacao', 'incidencia', 'qualidade', 'atraso'];
const OPEN_STATUSES = ['aberto', 'em_analise', 'aguarda_fornecedor'];
const OCC_FILTERS = {
  todas: 'Todas',
  abertas: 'Em aberto',
  problemas: 'Problemas',
  comunicacoes: 'Comunicações',
};

let current = {id: null, tab: 'geral', period: '12m', from: '', to: '', occFilter: 'todas', data: null};
let gradientSeq = 0;

export async function openSupplierDossier(supplierId, options = {}) {
  current = {
    id: Number(supplierId), tab: options.tab || 'geral', period: options.period || '12m',
    from: '', to: '', occFilter: 'todas', data: null,
  };
  openModal('Ficha de fornecedor', loading('A abrir a ficha…'), '', {cardClass: 'supplier-ficha-card'});
  try {
    await reload();
  } catch (error) {
    openModal('Ficha de fornecedor', `<div class="empty"><strong>Não foi possível abrir a ficha</strong><span>${esc(error.message)}</span></div>`, '', {cardClass: 'supplier-ficha-card'});
    toast(error.message, 'error');
  }
}

function widen() {
  // openModal limpa a classe, por isso alarga-se o cartão depois de pintar.
  document.querySelector('.modal-card')?.classList.add('supplier-ficha-card');
}

async function reload() {
  const query = [`period=${encodeURIComponent(current.period)}`];
  if (current.period === 'custom' && current.from && current.to) {
    query.push(`date_from=${current.from}`, `date_to=${current.to}`);
  }
  current.data = await get(`/partners/${state.companyId}/suppliers/${current.id}/dossier?${query.join('&')}`);
  paint();
}

function paint() {
  const data = current.data;
  const supplier = data.supplier || {};
  openModal('Ficha de fornecedor', fichaHtml(data, current.tab), supplier.name || '', {cardClass: 'supplier-ficha-card'});
  widen();
  bind(data);
}

function fichaHtml(data, tab) {
  const openOcc = (data.occurrences || []).filter(row => OPEN_STATUSES.includes(row.status)).length;
  return `<div class="sf">
    ${heroHtml(data)}
    ${alertsHtml(data.alerts || [])}
    <nav class="sf-tabs">${TABS.map(item => {
      const count = item.id === 'curso' ? (data.open_jobs || []).length
        : item.id === 'ocorrencias' ? openOcc : null;
      return `<button type="button" class="${item.id === tab ? 'on' : ''}" data-sf-tab="${item.id}">${item.label}${count ? `<i>${count}</i>` : ''}</button>`;
    }).join('')}</nav>
    <div class="sf-body">${tabHtml(data, tab)}</div>
    <p class="sf-foot">Indicadores calculados automaticamente a partir das requisições, receções, inspeções e ocorrências registadas.</p>
  </div>`;
}

function heroHtml(data) {
  const s = data.supplier || {};
  const summary = data.summary || {};
  const trend = trendOf(data.performance?.evolution || []);
  return `<header class="sf-hero">
    <div class="sf-hero-main">
      <div class="sf-avatar">${esc(initials(s.name))}</div>
      <div>
        <small>Ficha de fornecedor</small>
        <h2>${esc(s.name)}</h2>
        <div class="sf-meta">
          <span class="${s.active ? '' : 'off'}">${s.active ? 'Ativo' : 'Inactivo'}</span>
          ${s.type_label || s.supplier_type ? `<span>${esc(s.type_label || s.supplier_type)}</span>` : ''}
          <span>${esc(s.code)}</span>
          ${s.city ? `<span>${esc(s.city)}</span>` : ''}
          ${s.created_at ? `<span>Desde ${date(s.created_at)}</span>` : ''}
        </div>
      </div>
    </div>
    <div class="sf-hero-right">
      <div class="sf-hero-score">
        ${scoreRing(summary.score)}
        <div>
          <div class="lbl">Classificação</div>
          ${stars(summary.stars)}
          <span class="trend">${trend.label}</span>
        </div>
      </div>
      <div class="sf-actions">
        <button type="button" class="btn" data-sf-edit>Editar</button>
        <button type="button" class="btn" data-sf-print>Imprimir</button>
        <button type="button" class="btn primary" data-new-occ>+ Ocorrência</button>
      </div>
    </div>
  </header>`;
}

function initials(name) {
  return String(name || '?').trim().split(/\s+/).slice(0, 2).map(word => word[0] || '').join('').toUpperCase() || '?';
}

function trendOf(rows) {
  const pts = (rows || []).filter(row => row.pct != null);
  if (pts.length < 2) return {label: 'Sem histórico suficiente', dir: 0};
  const diff = Number(pts.at(-1).pct) - Number(pts.at(-2).pct);
  if (Math.abs(diff) < 1) return {label: '▬ Desempenho estável', dir: 0};
  return diff > 0
    ? {label: `▲ A melhorar (+${fmt(diff)} pp)`, dir: 1}
    : {label: `▼ A piorar (${fmt(diff)} pp)`, dir: -1};
}

function scoreRing(score) {
  const value = score == null ? 0 : Math.max(0, Math.min(10, Number(score)));
  const r = 30, c = 2 * Math.PI * r, dash = (value / 10) * c;
  return `<svg viewBox="0 0 72 72" width="72" height="72" role="img" aria-label="Classificação ${score == null ? 'sem dados' : `${value} em 10`}">
    <circle cx="36" cy="36" r="${r}" fill="none" stroke="rgba(255,255,255,.22)" stroke-width="7"/>
    <circle cx="36" cy="36" r="${r}" fill="none" stroke="#ffffff" stroke-width="7" stroke-linecap="round"
      stroke-dasharray="${dash.toFixed(1)} ${c.toFixed(1)}" transform="rotate(-90 36 36)"/>
    <text x="36" y="40" text-anchor="middle" fill="#fff" style="font:800 18px Inter,system-ui">${score == null ? '—' : fmt(value)}</text>
  </svg>`;
}

function alertsHtml(alerts) {
  if (!alerts.length) return '';
  return `<div class="sf-alerts">${alerts.map(row => `<button type="button" class="${esc(row.level)}" data-sf-tab="${esc(row.tab || 'desempenho')}">
    <span><b>${esc(row.title)}</b><span>${esc(row.detail || '')}</span></span>
  </button>`).join('')}</div>`;
}

function tabHtml(data, tab) {
  if (tab === 'servicos') return servicesHtml(data);
  if (tab === 'curso') return jobsHtml(data.open_jobs || [], 'Sem trabalhos em curso neste fornecedor.');
  if (tab === 'compras') return purchasesHtml(data);
  if (tab === 'desempenho') return performanceHtml(data);
  if (tab === 'ocorrencias') return occurrencesHtml(data, false);
  if (tab === 'documentos') return documentsHtml(data);
  return generalHtml(data);
}

function kv(label, value) {
  return `<div><span>${esc(label)}</span><strong>${value ?? '—'}</strong></div>`;
}

function generalHtml(data) {
  const s = data.supplier || {};
  const p = s.profile || {};
  const summary = data.summary || {};
  const finance = data.finance || {};
  const perf = data.performance || {};
  const addresses = p.addresses?.length ? p.addresses : [{label: 'Instalações principais', address: s.address, contact: s.contact_name, phone: s.phone}];
  const categories = p.categories?.length ? p.categories : [s.type_label || s.supplier_type].filter(Boolean);
  return `<div class="sf-geral">
    <div class="sf-col">
      <section class="sf-card"><h3>Informações gerais</h3>
        <div class="sf-kv">
          ${kv('Nome', esc(s.name))}
          ${kv('NIF', esc(s.tax_id || '—'))}
          ${kv('Código', esc(s.code))}
          ${kv('Tipo', esc(s.type_label || '—'))}
          ${kv('Estado', s.active ? '<em class="good">Ativo</em>' : '<em class="bad">Inactivo</em>')}
          ${kv('Idioma', esc(p.language === 'en' ? 'English' : 'Português'))}
          ${kv('Morada', esc([s.address, s.postal_code, s.city].filter(Boolean).join(', ') || '—'))}
          ${kv('Email', s.email ? `<a href="mailto:${esc(s.email)}">${esc(s.email)}</a>` : '—')}
          ${kv('Telefone', esc(s.phone || '—'))}
          ${kv('Contacto', esc([s.contact_name, p.contact_role].filter(Boolean).join(', ') || '—'))}
        </div>
      </section>
      <section class="sf-card"><h3>Condições comerciais</h3>
        <div class="sf-chips">
          <span>${esc(s.payment_terms || s.payment_term_code || 'Cond. pagamento —')}</span>
          <span>Transporte ${p.transport_included ? 'incluído' : 'não incluído'}</span>
          <span>${esc(s.currency || 'EUR')}</span>
          <span>Incoterm ${esc(p.incoterm || 'EXW')}</span>
        </div>
      </section>
      <section class="sf-card"><h3>Endereços do fornecedor</h3>
        <div class="sf-addr">${addresses.map(row => `<article><b>${esc(row.label || 'Morada')}</b><p>${esc(row.address || '—')}</p><small>${esc([row.contact, row.phone].filter(Boolean).join(' · ') || '')}</small></article>`).join('')}</div>
      </section>
      <section class="sf-card"><h3>Categorias / Especialidades</h3>
        <div class="sf-tags">${categories.length ? categories.map(item => `<span>${esc(item)}</span>`).join('') : '<span>Sem categorias</span>'}</div>
      </section>
      <section class="sf-card"><h3>Dados adicionais</h3>
        <div class="sf-kv">
          ${kv('IBAN', esc(s.iban || '—'))}
          ${kv('Banco', esc(p.bank_name || '—'))}
          ${kv('Certificações', esc((data.certifications || []).map(row => row.cert_type).join(' / ') || '—'))}
          ${kv('Seguro', esc(p.insurance || '—'))}
          ${kv('Capacidade', esc(p.daily_capacity || (s.weekly_capacity ? `${number(s.weekly_capacity)} / sem.` : '—')))}
        </div>
      </section>
    </div>
    <div class="sf-col">
      <section class="sf-card sf-resumo"><h3>Resumo rápido</h3>
        ${stat('★', 'Classificação geral', summary.score != null ? `${fmt(summary.score)} / 10` : 'Sem histórico', 'desempenho', tone(summary.score, 7, 5))}
        ${stat('◷', 'Entregas no prazo', summary.on_time_pct != null ? percent(summary.on_time_pct) : '—', 'desempenho', tone(summary.on_time_pct, 90, 80))}
        ${stat('⏱', 'Prazo médio real', summary.avg_real != null ? `${fmt(summary.avg_real)} dias` : '—', 'desempenho')}
        ${stat('⚠', 'Reclamações abertas', summary.open_complaints || 0, 'ocorrencias', summary.open_complaints ? 'bad' : 'ok')}
        ${stat('✉', 'Última ocorrência', date(summary.last_occurrence), 'ocorrencias')}
        ${stat('€', 'Última compra', `${date(summary.last_purchase)}${summary.last_purchase_ref ? ` · ${esc(summary.last_purchase_ref)}` : ''}`, 'compras')}
        ${stat('⚙', 'Trabalhos em curso', summary.open_jobs || 0, 'curso', (summary.open_jobs || 0) ? 'warn' : '')}
      </section>
      <section class="sf-card"><h3>Resumo financeiro (período)</h3>
        <div class="sf-kv">
          ${kv('Compras no período', money(finance.period_spend))}
          ${kv('Ano corrente', money(finance.year_spend))}
          ${kv('Requisições', finance.requisitions || 0)}
          ${kv('Desvio vs. preço acordado', finance.price_deviation_pct == null ? '—' : `<em class="${finance.price_deviation_pct > 0 ? 'bad' : 'good'}">${finance.price_deviation_pct > 0 ? '+' : ''}${fmt(finance.price_deviation_pct)}%</em>`)}
        </div>
      </section>
    </div>
    <div class="sf-col">
      <section class="sf-card"><h3>Desempenho</h3>
        <div class="sf-perf-mini">
          ${donut(perf.on_time_pct)}
          <ul>
            <li><span>Trabalhos realizados</span><b>${perf.completed || 0}</b></li>
            <li><span>Atraso médio</span><b>${signedDays(perf.avg_delay)}</b></li>
            <li><span>Taxa de rejeição</span><b>${perf.reject_rate_pct == null ? '—' : percent(perf.reject_rate_pct)}</b></li>
            <li><span>Incidências</span><b>${perf.incidents || 0}</b></li>
          </ul>
        </div>
        <h4>Evolução mensal · entregas no prazo</h4>
        ${chart(perf.evolution || [])}
      </section>
      ${occurrencesHtml(data, true)}
    </div>
  </div>`;
}

function stat(icon, label, value, tab, klass = '') {
  return `<button type="button" class="sf-stat ${klass}" data-sf-tab="${tab}">
    <span class="ic">${icon}</span>
    <span><span>${esc(label)}</span><strong>${value}</strong></span>
  </button>`;
}

function tone(value, good, warn) {
  if (value == null) return '';
  return Number(value) >= good ? 'ok' : Number(value) >= warn ? 'warn' : 'bad';
}

function fmt(value) {
  return Number(value || 0).toLocaleString('pt-PT', {maximumFractionDigits: 1});
}

function signedDays(value) {
  if (value == null) return '—';
  const n = Number(value);
  return `<em class="${n > 0 ? 'bad' : 'good'}">${n > 0 ? '+' : ''}${fmt(n)} dias</em>`;
}

function stars(value) {
  const n = Number(value || 0);
  return `<span class="sf-stars">${[1, 2, 3, 4, 5].map(i => `<i class="${n >= i ? 'full' : n >= i - 0.5 ? 'half' : ''}">★</i>`).join('')}</span>`;
}

function donut(pct) {
  const value = pct == null ? 0 : Number(pct);
  const colour = pct == null ? '#c7d2e0' : value >= 90 ? '#12805c' : value >= 80 ? '#c47f17' : '#c0392f';
  const r = 40, c = 2 * Math.PI * r, dash = (value / 100) * c;
  return `<svg class="sf-donut" viewBox="0 0 100 100" role="img" aria-label="Entregas no prazo ${pct == null ? 'sem dados' : percent(pct)}">
    <circle cx="50" cy="50" r="${r}" fill="none" stroke="#edf1f7" stroke-width="11"/>
    <circle cx="50" cy="50" r="${r}" fill="none" stroke="${colour}" stroke-width="11" stroke-linecap="round"
      stroke-dasharray="${dash.toFixed(1)} ${c.toFixed(1)}" transform="rotate(-90 50 50)"/>
    <text class="val" x="50" y="49" text-anchor="middle">${pct == null ? '—' : `${Math.round(value)}%`}</text>
    <text class="cap" x="50" y="62" text-anchor="middle">NO PRAZO</text>
  </svg>`;
}

function chart(rows, wide = false) {
  const pts = (rows || []).filter(row => row.pct != null);
  if (!pts.length) {
    return '<div class="sf-empty"><b>Sem entregas concluídas no período</b>Assim que existirem receções, a evolução aparece aqui.</div>';
  }
  const id = `sfGrad${++gradientSeq}`;
  const w = wide ? 1000 : 360, h = wide ? 250 : 170, left = wide ? 40 : 26, right = wide ? 78 : 46;
  const top = 12, bottom = wide ? 30 : 26;
  const iw = w - left - right, ih = h - top - bottom;
  const maxVol = Math.max(1, ...pts.map(row => (row.on_time || 0) + (row.late || 0)));
  const x = i => left + (pts.length === 1 ? iw / 2 : (i * iw) / (pts.length - 1));
  const y = pct => top + ih - (Number(pct) / 100) * ih;
  const barW = Math.max(6, Math.min(26, iw / (pts.length * 1.8)));
  const bars = pts.map((row, i) => {
    const vol = (row.on_time || 0) + (row.late || 0);
    const bh = (vol / maxVol) * ih * 0.55;
    return `<rect class="bar" x="${(x(i) - barW / 2).toFixed(1)}" y="${(top + ih - bh).toFixed(1)}" width="${barW.toFixed(1)}" height="${bh.toFixed(1)}" rx="3"><title>${esc(row.label)} · ${vol} entrega(s)</title></rect>`;
  }).join('');
  const line = pts.map((row, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(row.pct).toFixed(1)}`).join(' ');
  const area = `${line} L${x(pts.length - 1).toFixed(1)},${(top + ih).toFixed(1)} L${x(0).toFixed(1)},${(top + ih).toFixed(1)} Z`;
  const grid = [0, 50, 100].map(value => `<line class="grid" x1="${left}" y1="${y(value).toFixed(1)}" x2="${w - right}" y2="${y(value).toFixed(1)}"/>
    <text class="axis" x="${left - 5}" y="${(y(value) + 3).toFixed(1)}" text-anchor="end">${value}%</text>`).join('');
  const step = Math.ceil(pts.length / 6);
  const labels = pts.map((row, i) => (i % step === 0 || i === pts.length - 1)
    ? `<text class="axis" x="${x(i).toFixed(1)}" y="${h - 8}" text-anchor="middle">${esc(row.label)}</text>` : '').join('');
  const dots = pts.map((row, i) => `<circle class="pt ${Number(row.pct) < 80 ? 'low' : ''}" cx="${x(i).toFixed(1)}" cy="${y(row.pct).toFixed(1)}" r="3.6"><title>${esc(row.label)} · ${percent(row.pct)} no prazo (${row.on_time} ok / ${row.late} atraso)</title></circle>`).join('');
  return `<svg class="sf-chart" viewBox="0 0 ${w} ${h}" role="img" aria-label="Evolução das entregas no prazo">
    <defs><linearGradient id="${id}" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#2f62bc" stop-opacity=".28"/><stop offset="100%" stop-color="#2f62bc" stop-opacity="0"/>
    </linearGradient></defs>
    ${grid}
    ${bars}
    <line class="target" x1="${left}" y1="${y(80).toFixed(1)}" x2="${w - right}" y2="${y(80).toFixed(1)}"/>
    ${wide
      ? `<text class="tlabel" x="${w - right + 6}" y="${(y(80) + 3).toFixed(1)}">meta 80%</text>`
      : `<text class="tlabel" x="${left + 3}" y="${(y(80) - 5).toFixed(1)}">meta 80%</text>`}
    <path class="area" d="${area}" fill="url(#${id})"/>
    <path class="line" d="${line}"/>
    ${dots}
    ${labels}
  </svg>
  <div class="sf-legend"><span class="l1"><i></i>% no prazo</span><span class="l2"><i></i>entregas concluídas</span></div>`;
}

function servicesHtml(data) {
  const rows = data.services || [];
  return `<section class="sf-card"><h3>Serviços e preços acordados</h3>
    <div class="table-wrap"><table class="data-table"><thead><tr><th>Código</th><th>Serviço</th><th>Un.</th><th>Preço</th><th>Prazo</th><th>Mínimo</th><th>Estado</th></tr></thead>
    <tbody>${rows.length ? rows.map(row => `<tr>
      <td><b>${esc(row.code)}</b></td><td>${esc(row.name)}</td><td>${esc(row.unit)}</td>
      <td>${money(row.unit_cost)}</td><td>${row.lead_time_days || 0} d</td>
      <td>${number(row.minimum_quantity || 0)}</td><td>${badge(row.active ? 'activo' : 'inactivo')}</td>
    </tr>`).join('') : '<tr><td colspan="7">Sem serviços associados. Crie-os em Subcontratos.</td></tr>'}</tbody></table></div>
  </section>`;
}

function jobsHtml(rows, empty) {
  return `<section class="sf-card"><h3>Trabalhos</h3>
    <div class="table-wrap"><table class="data-table"><thead><tr><th>Ref.</th><th>OF</th><th>Serviço</th><th>Qtd.</th><th>Envio</th><th>Previsto</th><th>Real</th><th>Desvio</th><th>Estado</th></tr></thead>
    <tbody>${rows.length ? rows.map(row => `<tr>
      <td><b>${esc(row.reference)}</b></td>
      <td>${row.order_no ? `<button type="button" class="linkish" data-open-of="${row.production_order_id}">${esc(row.order_no)}</button>` : '—'}</td>
      <td>${esc(row.service_name || '—')}</td>
      <td>${number(row.quantity)}</td>
      <td>${date(row.sent_date)}</td>
      <td>${date(row.expected_date)}${row.planned_days != null ? ` · ${row.planned_days} d` : ''}</td>
      <td>${date(row.received_date)}${row.real_days != null ? ` · ${row.real_days} d` : ''}</td>
      <td>${row.delay_days == null ? '—' : signedDays(row.delay_days)}</td>
      <td>${badge(row.status)}</td>
    </tr>`).join('') : `<tr><td colspan="9">${esc(empty)}</td></tr>`}</tbody></table></div>
  </section>`;
}

function purchasesHtml(data) {
  return `${jobsHtml(data.history || [], 'Sem compras / requisições no período.')}
    <section class="sf-card section-spaced"><h3>Encomendas de compra</h3>
      <div class="table-wrap"><table class="data-table"><thead><tr><th>Nº</th><th>Data</th><th>Previsto</th><th>Total</th><th>Estado</th></tr></thead>
      <tbody>${(data.purchases || []).length ? data.purchases.map(row => `<tr>
        <td><b>${esc(row.order_no)}</b></td><td>${date(row.order_date)}</td><td>${date(row.expected_date)}</td>
        <td>${money(row.total)}</td><td>${badge(row.status)}</td>
      </tr>`).join('') : '<tr><td colspan="5">Sem encomendas de compra.</td></tr>'}</tbody></table></div>
    </section>`;
}

function performanceHtml(data) {
  const p = data.performance || {};
  const score = data.score || {};
  const ratings = data.internal_ratings || {};
  const labels = {prazo: 'Prazo', qualidade: 'Qualidade', incidencias: 'Incidências', preco: 'Preço'};
  const rateLabels = {comunicacao: 'Comunicação', flexibilidade: 'Flexibilidade', resposta: 'Capacidade de resposta', colaboracao: 'Colaboração', disponibilidade: 'Disponibilidade'};
  const trend = trendOf(p.evolution || []);
  return `<div class="sf-period">${['3m', '6m', '12m', 'year', 'custom'].map(id => {
    const names = { '3m': '3 meses', '6m': '6 meses', '12m': '12 meses', year: 'Ano atual', custom: 'Personalizado' };
    return `<button type="button" class="${current.period === id ? 'on' : ''}" data-period="${id}">${names[id]}</button>`;
  }).join('')}
    ${current.period === 'custom' ? `<label>De <input type="date" data-from value="${esc(current.from)}"></label><label>Até <input type="date" data-to value="${esc(current.to)}"></label><button type="button" class="btn small" data-apply-period>Aplicar</button>` : ''}
  </div>
  <div class="sf-score-row">
    <section class="sf-card"><h3>Classificação geral</h3>
      <div class="sf-score-head">
        <div>
          <div class="sf-score">${score.overall != null ? `${fmt(score.overall)} <small>/ 10</small>` : '—'}</div>
          <p>${trend.label}</p>
        </div>
        <div>${stars(data.summary?.stars)}</div>
      </div>
      <div class="sf-bars">${['prazo', 'qualidade', 'incidencias', 'preco'].map(key => {
        const val = score.parts?.[key];
        const width = val == null ? 100 : Math.max(2, Math.min(100, Number(val) * 10));
        const klass = val == null ? 'na' : val >= 8 ? 'good' : val >= 6 ? 'warn' : 'bad';
        return `<div class="sf-bar ${klass}">
          <b><span>${labels[key]}<i>${score.weights?.[key] || 0}%</i></span><em>${val == null ? 's/ dados' : `${fmt(val)}/10`}</em></b>
          <div class="track"><span style="width:${width}%"></span></div>
        </div>`;
      }).join('')}</div>
    </section>
    <section class="sf-card"><h3>Indicadores do período</h3>
      <div class="table-wrap"><table class="data-table sf-ind"><tbody>
        ${[['Trabalhos realizados', p.completed || 0], ['Entregues no prazo', p.on_time || 0], ['Entregues com atraso', p.late || 0],
          ['Cumprimento de prazo', p.on_time_pct == null ? '—' : percent(p.on_time_pct)],
          ['Prazo médio previsto', p.avg_planned == null ? '—' : `${fmt(p.avg_planned)} dias`],
          ['Prazo médio real', p.avg_real == null ? '—' : `${fmt(p.avg_real)} dias`],
          ['Atraso médio', signedDays(p.avg_delay)], ['Incidências', p.incidents || 0],
          ['Reclamações abertas', p.complaints || 0],
          ['Taxa de rejeição', p.reject_rate_pct == null ? '—' : percent(p.reject_rate_pct)],
        ].map(([label, value]) => `<tr><th>${esc(label)}</th><td>${value}</td></tr>`).join('')}
      </tbody></table></div>
    </section>
  </div>
  <section class="sf-card"><h3>% de entregas no prazo por mês</h3>${chart(p.evolution || [], true)}</section>
  <section class="sf-card section-spaced"><h3>Avaliação interna</h3>
    <p class="muted rating-help">Complementa os indicadores automáticos — não os substitui. Escala 1 a 5.</p>
    <div class="sf-rate">${Object.entries(rateLabels).map(([key, label]) => {
      const value = Number(ratings[key] || 0);
      return `<div class="sf-rate-row"><span>${label}</span>
        <span class="sf-stars-input" data-rate="${key}" data-value="${value}">${[1, 2, 3, 4, 5].map(n => `<button type="button" data-star="${n}" class="${n <= value ? 'on' : ''}" aria-label="${n}">★</button>`).join('')}</span>
      </div>`;
    }).join('')}</div>
    <div class="sf-rate-actions"><button type="button" class="btn primary" data-save-ratings>Guardar avaliação</button></div>
  </section>`;
}

function filterOccurrences(rows) {
  if (current.occFilter === 'abertas') return rows.filter(row => OPEN_STATUSES.includes(row.status));
  if (current.occFilter === 'problemas') return rows.filter(row => PROBLEM_KINDS.includes(row.kind));
  if (current.occFilter === 'comunicacoes') return rows.filter(row => !PROBLEM_KINDS.includes(row.kind));
  return rows;
}

function occurrencesHtml(data, compact) {
  if (compact) {
    const rows = data.recent_occurrences || [];
    return `<section class="sf-card"><div class="sf-card-head"><h3>Ocorrências recentes</h3>
        <button type="button" class="btn small" data-sf-tab="ocorrencias">Ver todas →</button></div>
      ${rows.length ? `<ol class="sf-timeline">${rows.map(row => `<li class="${KIND_TONE[row.kind] || ''}" data-occ="${row.id}">
        <div class="sf-tl-head"><time>${date(row.occurred_on)}</time><span class="sf-kind ${KIND_TONE[row.kind] || ''}">${esc(row.kind_label || row.kind)}</span>${badge(row.status_label || row.status)}</div>
        <p>${esc(row.subject)}</p>
        <small>${row.order_no ? `<button type="button" class="linkish" data-open-of="${row.production_order_id}">${esc(row.order_no)}</button> · ` : ''}${esc(row.responsible || 'Sem responsável')}</small>
      </li>`).join('')}</ol>` : '<div class="sf-empty"><b>Ainda sem histórico</b>Registe comunicações, reclamações e acordos para construir o histórico.</div>'}
    </section>`;
  }
  const all = data.occurrences || [];
  const rows = filterOccurrences(all);
  return `<section class="sf-card"><div class="sf-card-head"><h3>Ocorrências &amp; comunicação</h3>
      <div class="sf-filters">${Object.entries(OCC_FILTERS).map(([id, label]) => `<button type="button" class="${current.occFilter === id ? 'on' : ''}" data-occ-filter="${id}">${label}</button>`).join('')}</div>
      <button type="button" class="btn primary small" data-new-occ>+ Nova ocorrência / comunicação</button>
    </div>
    <div class="table-wrap"><table class="data-table"><thead><tr><th>Data</th><th>Tipo</th><th>Assunto</th><th>OF / Req.</th><th>Responsável</th><th>Prioridade</th><th>Estado</th></tr></thead>
    <tbody>${rows.length ? rows.map(row => `<tr class="sf-occ-row" data-occ="${row.id}">
      <td>${date(row.occurred_on)}</td>
      <td><span class="sf-kind ${KIND_TONE[row.kind] || ''}">${esc(row.kind_label || row.kind)}</span></td>
      <td><b>${esc(row.subject)}</b>${row.description ? `<div class="muted">${esc(row.description).slice(0, 140)}</div>` : ''}</td>
      <td>${row.order_no ? `<button type="button" class="linkish" data-open-of="${row.production_order_id}">${esc(row.order_no)}</button>` : esc(row.job_reference || '—')}</td>
      <td>${esc(row.responsible || '—')}</td>
      <td><span class="sf-prio ${esc(row.priority || 'normal')}">${esc(row.priority || 'normal')}</span></td>
      <td>${badge(row.status_label || row.status)}</td>
    </tr>`).join('') : `<tr><td colspan="7">${all.length ? 'Nenhum registo neste filtro.' : 'Ainda sem histórico de comunicações.'}</td></tr>`}</tbody></table></div>
  </section>`;
}

function documentsHtml(data) {
  return `<section class="sf-card"><h3>Certificações</h3>
    <div class="table-wrap"><table class="data-table"><thead><tr><th>Tipo</th><th>Nº</th><th>Emissão</th><th>Validade</th><th>Estado</th><th></th></tr></thead>
    <tbody>${(data.certifications || []).length ? data.certifications.map(row => `<tr>
      <td>${esc(row.cert_type)}</td><td>${esc(row.certificate_no || '—')}</td><td>${date(row.issued_date)}</td>
      <td>${date(row.expiry_date)}</td><td>${badge(row.status)}</td>
      <td>${row.document_path ? `<a href="${esc(row.document_path)}" target="_blank" rel="noopener">Abrir</a>` : '—'}</td>
    </tr>`).join('') : '<tr><td colspan="6">Sem certificações. Adicione-as em Parceiros → Certificações.</td></tr>'}</tbody></table></div>
  </section>
  <section class="sf-card section-spaced"><h3>Documentos ERP</h3>
    <div class="table-wrap"><table class="data-table"><thead><tr><th>Documento</th><th>Tipo</th><th>Data</th><th>Total</th><th>Estado</th></tr></thead>
    <tbody>${(data.documents || []).length ? data.documents.map(row => `<tr>
      <td><b>${esc(row.doc_no)}</b></td><td>${esc(row.doc_type)}</td><td>${date(row.doc_date)}</td>
      <td>${money(row.total)}</td><td>${badge(row.status)}</td>
    </tr>`).join('') : '<tr><td colspan="5">Sem documentos Primavera associados.</td></tr>'}</tbody></table></div>
  </section>`;
}

function occurrenceFields(data, row = {}, kind) {
  const kinds = Object.entries(data.kinds || {}).map(([value, label]) => ({value, label}));
  const statuses = Object.entries(data.statuses || {}).map(([value, label]) => ({value, label}));
  const orders = [...(data.open_jobs || []), ...(data.history || [])]
    .filter(item => item.production_order_id)
    .map(item => ({value: item.production_order_id, label: item.order_no || `#${item.production_order_id}`}));
  const uniqueOrders = [...new Map(orders.map(item => [item.value, item])).values()];
  const jobs = [...(data.open_jobs || []), ...(data.history || [])].map(item => ({value: item.id, label: item.reference}));
  const services = (data.services || []).map(item => ({value: item.id, label: item.name}));
  const fields = [
    {key: 'occurred_on', label: 'Data', type: 'date', required: true, default: new Date().toISOString().slice(0, 10)},
    {key: 'kind', label: 'Tipo', type: 'select', required: true, options: kinds, default: 'comunicacao'},
    {key: 'subject', label: 'Assunto', required: true, full: true},
    {key: 'production_order_id', label: 'OF relacionada', type: 'select', options: [{value: '', label: '—'}, ...uniqueOrders]},
    {key: 'subcontract_job_id', label: 'Requisição', type: 'select', options: [{value: '', label: '—'}, ...jobs]},
    {key: 'subcontract_service_id', label: 'Serviço', type: 'select', options: [{value: '', label: '—'}, ...services]},
    {key: 'responsible', label: 'Responsável interno'},
    {key: 'priority', label: 'Prioridade', type: 'select', options: ['baixa', 'normal', 'alta', 'urgente'], default: 'normal'},
    {key: 'status', label: 'Estado', type: 'select', options: statuses, default: 'aberto'},
    {key: 'due_date', label: 'Data limite', type: 'date'},
    {key: 'description', label: 'Descrição', type: 'textarea', full: true},
    {key: 'attachments', label: 'Anexos / fotos', type: 'photo', full: true},
  ];
  if ((kind || row.kind) === 'reclamacao') {
    const extra = row.complaint || row.extra || {};
    fields.push(
      {key: 'motivo', label: 'Motivo', default: extra.motivo, full: true},
      {key: 'qty_affected', label: 'Qtd. afetada', type: 'number', default: extra.qty_affected},
      {key: 'qty_rejected', label: 'Qtd. rejeitada', type: 'number', default: extra.qty_rejected},
      {key: 'cost_estimated', label: 'Custo estimado', type: 'number', default: extra.cost_estimated},
      {key: 'cost_actual', label: 'Custo real', type: 'number', default: extra.cost_actual},
      {key: 'supplier_responsible', label: 'Responsabilidade do fornecedor', type: 'select', options: [
        {value: '', label: '—'}, {value: 'sim', label: 'Sim'}, {value: 'nao', label: 'Não'}, {value: 'analise', label: 'Em análise'},
      ], default: extra.supplier_responsible},
      {key: 'supplier_reply', label: 'Resposta do fornecedor', type: 'textarea', full: true, default: extra.supplier_reply},
      {key: 'solution', label: 'Solução acordada', type: 'textarea', full: true, default: extra.solution},
      {key: 'resolved_date', label: 'Data da resolução', type: 'date', default: extra.resolved_date},
    );
  }
  return fields;
}

function bind(data) {
  const body = document.getElementById('modal-body');
  body.querySelectorAll('[data-sf-tab]').forEach(button => button.addEventListener('click', () => {
    current.tab = button.dataset.sfTab;
    paint();
  }));
  body.querySelectorAll('[data-occ-filter]').forEach(button => button.addEventListener('click', () => {
    current.occFilter = button.dataset.occFilter;
    paint();
  }));
  body.querySelectorAll('[data-period]').forEach(button => button.addEventListener('click', async () => {
    current.period = button.dataset.period;
    if (current.period !== 'custom') await reload();
    else paint();
  }));
  body.querySelector('[data-apply-period]')?.addEventListener('click', async () => {
    current.from = body.querySelector('[data-from]')?.value || '';
    current.to = body.querySelector('[data-to]')?.value || '';
    if (!current.from || !current.to) { toast('Indique as duas datas.', 'error'); return; }
    await reload();
  });
  body.querySelector('[data-sf-print]')?.addEventListener('click', () => {
    document.body.classList.add('printing-supplier');
    window.print();
    setTimeout(() => document.body.classList.remove('printing-supplier'), 400);
  });
  body.querySelector('[data-sf-edit]')?.addEventListener('click', () => openEdit(data));
  body.querySelectorAll('[data-new-occ]').forEach(button => button.addEventListener('click', () => openOccurrence(data, null)));
  body.querySelectorAll('[data-occ]').forEach(row => row.addEventListener('click', event => {
    if (event.target.closest('[data-open-of]')) return;
    const occ = (data.occurrences || []).find(item => String(item.id) === row.dataset.occ);
    if (occ) openOccurrence(data, occ);
  }));
  body.querySelectorAll('[data-open-of]').forEach(button => button.addEventListener('click', async event => {
    event.stopPropagation();
    const {loadOrderDossier} = await import('../production/dossier.js?v=20260826-3');
    await loadOrderDossier(Number(button.dataset.openOf));
  }));
  body.querySelectorAll('.sf-stars-input').forEach(group => group.addEventListener('click', event => {
    const button = event.target.closest('[data-star]');
    if (!button) return;
    const picked = Number(button.dataset.star);
    const value = Number(group.dataset.value || 0) === picked ? 0 : picked;
    group.dataset.value = String(value);
    group.querySelectorAll('[data-star]').forEach(item => item.classList.toggle('on', Number(item.dataset.star) <= value));
  }));
  body.querySelector('[data-save-ratings]')?.addEventListener('click', async () => {
    const ratings = {};
    body.querySelectorAll('.sf-stars-input').forEach(group => { ratings[group.dataset.rate] = Number(group.dataset.value || 0); });
    try {
      await patch(`/partners/${state.companyId}/suppliers/${current.id}/profile`, {internal_ratings: ratings});
      toast('Avaliação interna guardada.');
      await reload();
    } catch (error) { toast(error.message, 'error'); }
  });
}

function openEdit(data) {
  const s = data.supplier;
  const fields = [
    {key: 'name', label: 'Nome', required: true}, {key: 'code', label: 'Código', required: true},
    {key: 'tax_id', label: 'NIF'}, {key: 'supplier_type', label: 'Tipo', type: 'select', options: ['material', 'sewing', 'dyeing', 'printing', 'laundry', 'transport', 'general']},
    {key: 'email', label: 'Email'}, {key: 'phone', label: 'Telefone'}, {key: 'contact_name', label: 'Contacto'},
    {key: 'address', label: 'Morada', type: 'textarea', full: true}, {key: 'postal_code', label: 'Cód. postal'}, {key: 'city', label: 'Localidade'},
    {key: 'country', label: 'País'}, {key: 'payment_terms', label: 'Cond. pagamento'}, {key: 'currency', label: 'Moeda'},
    {key: 'iban', label: 'IBAN'}, {key: 'notes', label: 'Observações', type: 'textarea', full: true},
    {key: 'active', label: 'Activo', type: 'checkbox'},
  ];
  showSheet('Editar dados gerais', renderForm(fields, s), async form => {
    const payload = readForm(form, fields);
    await patch(`/partners/${state.companyId}/suppliers/${current.id}/profile`, payload);
    toast('Fornecedor actualizado.');
    await reload();
  });
}

function openOccurrence(data, row) {
  let kind = row?.kind || 'comunicacao';
  const values = row ? {...row, ...(row.complaint || {}), attachments: row.attachments || []} : {};
  const draw = () => {
    const fields = occurrenceFields(data, row || {}, kind);
    showSheet(row ? 'Editar ocorrência' : 'Nova ocorrência / comunicação', renderForm(fields, {...values, kind}), async form => {
      const payload = readForm(form, fields);
      const path = `/partners/${state.companyId}/suppliers/${current.id}/occurrences${row ? `/${row.id}` : ''}`;
      if (row) await patch(path, payload);
      else await post(path, payload);
      toast('Registo guardado.');
      current.tab = 'ocorrencias';
      await reload();
    }, row ? async () => {
      if (!confirm('Eliminar esta ocorrência?')) return;
      await remove(`/partners/${state.companyId}/suppliers/${current.id}/occurrences/${row.id}`);
      toast('Ocorrência eliminada.');
      await reload();
    } : null);
    const select = document.querySelector('#modal-body [name="kind"]');
    select?.addEventListener('change', () => {
      kind = select.value;
      values.kind = kind;
      draw();
    });
  };
  draw();
}

function showSheet(title, formHtml, onSave, onDelete) {
  const host = document.querySelector('#modal-body .sf-body') || document.getElementById('modal-body');
  host.innerHTML = `<section class="sf-card sf-sheet"><div class="sf-card-head"><h3>${esc(title)}</h3>
    <button type="button" class="btn" data-sheet-back>← Voltar</button></div>
    ${formHtml}
    <div class="sf-sheet-actions">
      ${onDelete ? '<button type="button" class="btn danger" data-sheet-del>Eliminar</button>' : ''}
      <button type="submit" class="btn primary" form="record-form">Guardar</button>
    </div>
  </section>`;
  bindPhotoFields(host);
  host.querySelector('[data-sheet-back]')?.addEventListener('click', paint);
  host.querySelectorAll('[data-close-modal]').forEach(button => button.addEventListener('click', event => {
    event.preventDefault();
    paint();
  }));
  host.querySelector('[data-sheet-del]')?.addEventListener('click', onDelete);
  host.querySelector('#record-form')?.addEventListener('submit', async event => {
    event.preventDefault();
    try { await onSave(event.currentTarget); }
    catch (error) { toast(error.message, 'error'); }
  });
}
