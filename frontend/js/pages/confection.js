import { renderOverview } from '../confection/overview.js?v=20260822-1';
import { renderConfectionTable } from '../confection/tables.js?v=20260822-7';
import { renderProductionMap } from '../confection/map.js?v=20260822-15';
import { renderDailyProduction } from '../confection/diary.js?v=20260821-25';
import { renderControls } from '../costing/control.js?v=20260819-8';
import { pageHeader } from '../ui.js?v=20260820-5';

const tabs = [
  ['overview','Capacidade'],['plans','Plano por linha'],
  ['lines','Linhas de produção'],['skills','Competências'],['machineTypes','Tipos de máquina'],
  ['contractors','Confeçionadores'],['shifts','Turnos'],
];

export async function render(container, initial='overview') {
  if (initial === 'map') {
    await renderProductionMap(container);
    return;
  }
  if (initial === 'diary') {
    await renderDailyProduction(container);
    return;
  }
  if (initial === 'costs') {
    await renderControls(container);
    return;
  }
  const sectionLabel=tabs.find(([key])=>key===initial)?.[1]||'Capacidade';
  container.innerHTML = pageHeader(`Confeção · ${sectionLabel}`, 'Planear a carga, acompanhar o que está a sair e ver o custo de cada ordem.', '<a class="btn primary" href="#/confection-diary">＋ Inserir produção</a><a class="btn" href="#/confection-map">Mapa</a>') + `<div data-confection-panel></div>`;
  const panel = container.querySelector('[data-confection-panel]');
  const open = async key => {
    panel.innerHTML='<div class="loading">A calcular capacidade…</div>';
    if(key==='overview')await renderOverview(panel);else await renderConfectionTable(panel,key);
  };
  await open(initial);
}
