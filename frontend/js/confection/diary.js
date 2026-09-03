import { get, post } from '../api.js';
import { esc, number } from '../format.js?v=20260826-3';
import { state } from '../state.js';
import { pageHeader, toast } from '../ui.js?v=20260826-3';

function todayIso() {
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 10);
}

function requestedOrderId() {
  const query = location.hash.split('?')[1] || '';
  return Number(new URLSearchParams(query).get('order') || 0);
}

function readableDate(value) {
  if (!value) return 'Sem data';
  return new Intl.DateTimeFormat('pt-PT', { day: '2-digit', month: 'short', year: 'numeric' })
    .format(new Date(`${value}T12:00:00`));
}

function variantKey(variant) {
  return variant.variant_id == null ? 'single' : String(variant.variant_id);
}

function pastelIndex(value) {
  return [...String(value)].reduce((total, char) => total + char.charCodeAt(0), 0) % 8;
}

function historyMarkup(data) {
  return `<section class="card diary-history">
    <div class="card-header">
      <div><h2>Produção registada</h2><small>${esc(readableDate(data.date))}</small></div>
      <strong>${number(data.totals.quantity_good)} peças</strong>
    </div>
    ${data.items.length ? `<div class="diary-history-grid">${data.items.map(row => `
      <article class="diary-history-item">
        <div><b>${esc(row.order_no)}</b><span>${esc(row.article || 'Artigo')}</span></div>
        <div><b>${esc(row.size || 'Único')}</b><span>${esc(row.color || '')}</span></div>
        <div><b>${esc(row.line)}</b><span>Linha</span></div>
        <strong>${number(row.quantity_good)}</strong>
      </article>`).join('')}</div>` : `
      <div class="diary-empty"><span>✓</span><strong>Ainda não há produção neste dia</strong><small>Comece por escolher uma encomenda acima.</small></div>`}
  </section>`;
}

export async function renderDailyProduction(container) {
  let workDate = todayIso();
  let [data, options] = await Promise.all([
    get(`/confection/${state.companyId}/daily-output?work_date=${workDate}`),
    get(`/confection/${state.companyId}/daily-output/options`),
  ]);
  const preselect = requestedOrderId();
  let selectedOrder = options.orders.find(order => order.articles.some(article => article.production_order_id === preselect)) || null;
  let selectedArticle = selectedOrder?.articles.find(article => article.production_order_id === preselect) || null;
  let selectedLineId = selectedArticle?.line_id || (options.lines.length === 1 ? options.lines[0].id : null);
  let quantities = {};
  let saving = false;
  let successText = '';

  container.innerHTML = pageHeader(
    'Produção do dia',
    'Registo simples para tablet: encomenda, artigo, linha e quantidades por tamanho.',
  ) + `
    <section class="card diary-date-card">
      <label><span>Dia da produção</span><input data-work-date type="date" value="${esc(workDate)}" max="2999-12-31"></label>
      <div><b>Registo por linha</b><small>Não é necessário escolher costureira nem indicar horas.</small></div>
    </section>
    <section class="card diary-touch" data-diary-workflow></section>
    <div data-diary-history>${historyMarkup(data)}</div>`;

  const workflow = container.querySelector('[data-diary-workflow]');

  const resetAfter = level => {
    successText = '';
    if (level === 'order') {
      selectedOrder = null;
      selectedArticle = null;
      selectedLineId = null;
    } else if (level === 'article') {
      selectedArticle = null;
      selectedLineId = null;
    } else if (level === 'line') {
      selectedLineId = null;
    }
    quantities = {};
  };

  const drawWorkflow = () => {
    const currentStep = !selectedOrder ? 1 : !selectedArticle ? 2 : selectedLineId ? 4 : 3;
    const total = Object.values(quantities).reduce((sum, value) => sum + value, 0);
    workflow.innerHTML = `
      <div class="diary-steps" aria-label="Etapas do registo">
        ${['Encomenda', 'Artigo', 'Linha', 'Tamanhos'].map((label, index) => `<span class="${currentStep >= index + 1 ? 'active' : ''} ${currentStep > index + 1 ? 'done' : ''}"><i>${currentStep > index + 1 ? '✓' : index + 1}</i>${label}</span>`).join('')}
      </div>
      ${successText ? `<div class="diary-success"><span>✓</span><b>${esc(successText)}</b></div>` : ''}
      ${selectedOrder ? `<div class="diary-breadcrumbs">
        <button type="button" data-change="order"><small>Encomenda</small><b>${esc(selectedOrder.order_no)}</b></button>
        ${selectedArticle ? `<span>›</span><button type="button" data-change="article"><small>Artigo</small><b>${esc(selectedArticle.reference)}</b></button>` : ''}
        ${selectedLineId ? `<span>›</span><button type="button" data-change="line"><small>Linha</small><b>${esc(options.lines.find(line => line.id === selectedLineId)?.name || '')}</b></button>` : ''}
      </div>` : ''}

      ${!selectedOrder ? `<div class="diary-stage">
        <div class="diary-stage-title"><span>1</span><div><h2>Escolha a encomenda</h2><p>Toque num quadrado para continuar.</p></div></div>
        ${options.orders.length ? `<div class="diary-order-grid">${options.orders.map(order => `
          <button type="button" class="diary-order-card pastel-${pastelIndex(order.key)}" data-order="${esc(order.key)}">
            <span>Encomenda</span><strong>${esc(order.order_no)}</strong><b>${esc(order.customer)}</b>
            <small>${order.articles.length} ${order.articles.length === 1 ? 'artigo' : 'artigos'}</small>
            <em>${number(order.remaining_quantity)} por produzir</em>
            ${order.delivery_date ? `<time>Entrega ${esc(readableDate(order.delivery_date))}</time>` : ''}
          </button>`).join('')}</div>` : `<div class="diary-empty"><strong>Não há encomendas disponíveis</strong><small>As encomendas em produção aparecerão aqui.</small></div>`}
      </div>` : ''}

      ${selectedOrder && !selectedArticle ? `<div class="diary-stage">
        <div class="diary-stage-title"><span>2</span><div><h2>Escolha o artigo</h2><p>Encomenda ${esc(selectedOrder.order_no)} · ${esc(selectedOrder.customer)}</p></div></div>
        <div class="diary-article-grid">${selectedOrder.articles.map(article => `
          <button type="button" class="diary-article-card" data-article="${article.production_order_id}">
            <span>Artigo</span><strong>${esc(article.reference)}</strong><b>${esc(article.description || '')}</b>
            <small>${esc(article.order_no)} · ${number(article.remaining_quantity)} por produzir</small>
            ${article.line ? `<em>${esc(article.line)}</em>` : ''}
          </button>`).join('')}</div>
      </div>` : ''}

      ${selectedArticle && !selectedLineId ? `<div class="diary-stage">
        <div class="diary-stage-title"><span>3</span><div><h2>Escolha a linha</h2><p>Toque na linha que está a produzir este artigo.</p></div></div>
        ${options.lines.length ? `<div class="diary-line-grid">${options.lines.map(line => `
          <button type="button" class="diary-line-card" data-line="${line.id}"><span>▤</span><strong>${esc(line.name)}</strong><small>${esc(line.code)}</small></button>`).join('')}</div>` : `<div class="diary-empty"><strong>Não existem linhas ativas</strong><small>Crie uma linha em Configurar a fábrica.</small></div>`}
      </div>` : ''}

      ${selectedArticle && selectedLineId ? `<div class="diary-stage">
        <div class="diary-stage-title"><span>4</span><div><h2>Indique as peças por tamanho</h2><p>Use apenas os botões. Pode somar 1, 5 ou 10 peças de cada vez.</p></div></div>
        <div class="diary-size-grid">${selectedArticle.variants.map(variant => {
          const key = variantKey(variant);
          const value = quantities[key] || 0;
          const limited = variant.remaining_quantity != null;
          const sizeMax = limited ? Math.max(0, Math.floor(variant.remaining_quantity)) : Number.MAX_SAFE_INTEGER;
          const articleRoom = Math.max(0, Math.floor(selectedArticle.remaining_quantity) - (total - value));
          const max = Math.min(sizeMax, articleRoom);
          const complete = max === 0 && value === 0;
          return `<article class="diary-size-card ${value ? 'has-value' : ''} ${complete ? 'complete' : ''}" data-size-card="${esc(key)}">
            <div class="diary-size-head"><div><span>Tamanho</span><strong>${esc(variant.size || 'Único')}</strong></div>${variant.color ? `<b>${esc(variant.color)}</b>` : ''}</div>
            <div class="diary-size-progress"><span>${number(variant.reported_quantity)} feitas</span>${limited ? `<span>${number(variant.remaining_quantity)} em falta</span>` : ''}</div>
            ${complete ? `<div class="diary-size-complete">✓ Completo</div>` : `
              <div class="diary-counter"><button type="button" data-size="${esc(key)}" data-delta="-1" ${value === 0 ? 'disabled' : ''}>−</button><output>${number(value)}</output><button type="button" data-size="${esc(key)}" data-delta="1" ${limited && value >= max ? 'disabled' : ''}>+1</button></div>
              <div class="diary-quick-add"><button type="button" data-size="${esc(key)}" data-delta="5" ${limited && value >= max ? 'disabled' : ''}>+5</button><button type="button" data-size="${esc(key)}" data-delta="10" ${limited && value >= max ? 'disabled' : ''}>+10</button></div>`}
          </article>`;
        }).join('')}</div>
        <div class="diary-confirm-bar"><div><small>Total a registar</small><strong>${number(total)} peças</strong></div><button class="btn primary" type="button" data-save ${!total || saving ? 'disabled' : ''}>${saving ? 'A guardar…' : `✓ Confirmar ${number(total)} peças`}</button></div>
      </div>` : ''}`;
  };

  workflow.addEventListener('click', async event => {
    const change = event.target.closest('[data-change]');
    if (change) {
      resetAfter(change.dataset.change);
      drawWorkflow();
      return;
    }
    const orderButton = event.target.closest('[data-order]');
    if (orderButton) {
      selectedOrder = options.orders.find(order => order.key === orderButton.dataset.order) || null;
      selectedArticle = null;
      selectedLineId = null;
      quantities = {};
      drawWorkflow();
      return;
    }
    const articleButton = event.target.closest('[data-article]');
    if (articleButton) {
      selectedArticle = selectedOrder.articles.find(article => article.production_order_id === Number(articleButton.dataset.article)) || null;
      selectedLineId = selectedArticle?.line_id || (options.lines.length === 1 ? options.lines[0].id : null);
      quantities = {};
      drawWorkflow();
      return;
    }
    const lineButton = event.target.closest('[data-line]');
    if (lineButton) {
      selectedLineId = Number(lineButton.dataset.line);
      quantities = {};
      drawWorkflow();
      return;
    }
    const counterButton = event.target.closest('[data-size][data-delta]');
    if (counterButton) {
      const key = counterButton.dataset.size;
      const variant = selectedArticle.variants.find(item => variantKey(item) === key);
      const current = quantities[key] || 0;
      const total = Object.values(quantities).reduce((sum, value) => sum + value, 0);
      const sizeMax = variant.remaining_quantity == null ? Number.MAX_SAFE_INTEGER : Math.max(0, Math.floor(variant.remaining_quantity));
      const articleRoom = Math.max(0, Math.floor(selectedArticle.remaining_quantity) - (total - current));
      const max = Math.min(sizeMax, articleRoom);
      quantities[key] = Math.min(max, Math.max(0, current + Number(counterButton.dataset.delta)));
      drawWorkflow();
      return;
    }
    const saveButton = event.target.closest('[data-save]');
    if (!saveButton || saving) return;
    const outputs = selectedArticle.variants
      .map(variant => ({ variant_id: variant.variant_id, quantity_good: quantities[variantKey(variant)] || 0 }))
      .filter(output => output.quantity_good > 0);
    if (!outputs.length) return;
    saving = true;
    drawWorkflow();
    try {
      data = await post(`/confection/${state.companyId}/daily-output/bulk`, {
        work_date: workDate,
        production_order_id: selectedArticle.production_order_id,
        line_id: selectedLineId,
        outputs,
      });
      const savedTotal = outputs.reduce((sum, output) => sum + output.quantity_good, 0);
      resetAfter('order');
      successText = `${number(savedTotal)} peças registadas com sucesso`;
      container.querySelector('[data-diary-history]').innerHTML = historyMarkup(data);
      toast(`${number(savedTotal)} peças registadas.`);
      try {
        options = await get(`/confection/${state.companyId}/daily-output/options`);
      } catch (_) {
        // O registo já foi concluído; a próxima abertura atualiza as encomendas.
      }
    } catch (error) {
      toast(error.message, 'error');
    } finally {
      saving = false;
      drawWorkflow();
    }
  });

  container.querySelector('[data-work-date]').addEventListener('change', async event => {
    workDate = event.target.value || todayIso();
    successText = '';
    drawWorkflow();
    try {
      data = await get(`/confection/${state.companyId}/daily-output?work_date=${workDate}`);
      container.querySelector('[data-diary-history]').innerHTML = historyMarkup(data);
    } catch (error) {
      toast(error.message, 'error');
    }
  });

  drawWorkflow();
}
