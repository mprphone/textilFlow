import { get } from '../api.js';
import { state } from '../state.js';
import { pageHeader } from '../ui.js?v=20260820-5';
import { assistantPanel, bindAssistant } from '../dashboard/assistant.js?v=20260819-5';
import { briefingHero, lineOverview, metricCards, orderFlow, priorityPanel, quickWorkflows } from '../dashboard/briefing.js?v=20260822-10';


export async function render(container) {
  const data = await get(`/dashboard/${state.companyId}`);
  container.innerHTML = pageHeader('Centro de comando', 'O que está a acontecer, o que exige decisão e onde atuar.', '<button class="btn" data-refresh>↻ Atualizar agora</button>') + `
    ${briefingHero(data, state.user?.name)}
    ${quickWorkflows()}
    ${metricCards(data)}
    <div class="dashboard-decision-grid">
      ${priorityPanel(data.briefing)}
      ${assistantPanel(data.briefing)}
    </div>
    ${orderFlow(data)}
    ${lineOverview(data.lines)}`;

  container.addEventListener('click', event => {
    const route = event.target.closest('[data-go-route]')?.dataset.goRoute;
    if (route) location.hash = `#/${route}`;
  });
  container.querySelector('[data-refresh]').addEventListener('click', () => render(container));
  bindAssistant(container);
}
