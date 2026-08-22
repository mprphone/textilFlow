import { post } from '../api.js';
import { esc } from '../format.js?v=20260819-5';
import { state } from '../state.js';

export function assistantPanel(briefing) {
  return `<section class="factory-copilot"><div class="copilot-head"><div><span>✦</span><div><b>Assistente da fábrica</b><small>Responde com os dados reais do sistema</small></div></div><em>IA operacional</em></div>
    <div class="copilot-prompts">${briefing.questions.map(question => `<button data-question="${esc(question)}">${esc(question)}</button>`).join('')}</div>
    <div class="copilot-input"><input id="factory-question" placeholder="Pergunte sobre custos, prazos, eficiência ou qualidade…"><button data-ask aria-label="Perguntar">→</button></div>
    <div id="factory-answer" class="copilot-answer hidden" role="status" aria-live="polite"></div>
  </section>`;
}

export function bindAssistant(container) {
  const input = container.querySelector('#factory-question');
  const target = container.querySelector('#factory-answer');
  const ask = async question => {
    if (!question.trim()) return;
    target.classList.remove('hidden');
    target.innerHTML = '<span class="thinking">A analisar produção, custos e exceções…</span>';
    try {
      const result = await post(`/assistant/${state.companyId}/query`, {question});
      target.innerHTML = `<p>${esc(result.answer)}</p>${result.facts?.length ? `<div class="answer-facts">${result.facts.map(item => `<span><small>${esc(item.label)}</small><b>${esc(item.value)}</b></span>`).join('')}</div>` : ''}${result.actions?.length ? `<div class="answer-actions">${result.actions.map(item => `<button class="btn small" data-go-route="${item.route}">${esc(item.label)} →</button>`).join('')}</div>` : ''}`;
    } catch (error) { target.innerHTML = `<p class="cost-bad">${esc(error.message)}</p>`; }
  };
  container.querySelector('[data-ask]').addEventListener('click', () => ask(input.value));
  input.addEventListener('keydown', event => { if (event.key === 'Enter') ask(input.value); });
  container.querySelectorAll('[data-question]').forEach(button => button.addEventListener('click', () => { input.value = button.dataset.question; ask(input.value); }));
}
