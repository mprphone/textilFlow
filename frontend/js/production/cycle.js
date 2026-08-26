import { humanize } from '../format.js?v=20260826-3';

const STAGE_LABEL = {
  planning: 'Planeamento',
  'à espera de malha': 'À espera de malha',
  'malha em stock': 'Malha em stock',
  corte: 'Corte',
  'confeção': 'Confeção',
  acabamento: 'Acabamento',
  'expedição': 'Expedição',
  production: 'Em produção',
  completed: 'Concluída',
};

export function stageLabel(stage) {
  if (!stage) return humanize(stage);
  return STAGE_LABEL[String(stage).toLowerCase()] || humanize(stage);
}
