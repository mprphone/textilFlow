import { renderControls } from '../costing/control.js?v=20260819-8';
import { renderCostOverview, renderProposals } from '../costing/proposals.js?v=20260824-41';


export async function render(container) {
  container.innerHTML = '<div class="tabs cost-main-tabs"><button class="tab active" data-cost-tab="overview">Visão geral</button><button class="tab" data-cost-tab="proposals">Propostas</button><button class="tab" data-cost-tab="control">Orçamentado vs. real</button></div><div data-cost-panel></div>';
  let panel = container.querySelector('[data-cost-panel]');
  let renderSequence = 0;
  const mount = async renderer => {
    const sequence = ++renderSequence;
    const next = document.createElement('div');
    next.dataset.costPanel = '';
    next.innerHTML = '<div class="loading">A carregar…</div>';
    try { await renderer(next); }
    catch { next.innerHTML = '<div class="empty"><strong>Não foi possível carregar esta vista.</strong>Tente novamente dentro de alguns instantes.</div>'; }
    if (sequence !== renderSequence) return;
    panel.replaceWith(next);
    panel = next;
  };
  await mount(renderCostOverview);
  container.querySelector('.cost-main-tabs').addEventListener('click', async event => {
    const button = event.target.closest('[data-cost-tab]');
    if (!button) return;
    container.querySelectorAll('[data-cost-tab]').forEach(item => item.classList.toggle('active', item === button));
    if (button.dataset.costTab === 'control') await mount(renderControls);
    else if (button.dataset.costTab === 'proposals') await mount(renderProposals);
    else await mount(renderCostOverview);
  });
}
