export const PIPELINE = [
  ['novo', 'Pedido recebido'],
  ['proposta_cliente', 'Referências e distribuição'],
  ['ficha_tecnica', 'Ficha técnica'],
  ['desenvolvimento_malha', 'Preparação materiais'],
  ['modelagem', 'Modelagem'],
  ['corte', 'Corte'],
  ['confecao', 'Confeção'],
  ['finalizacao', 'Finalização da amostra'],
  ['envio_cliente', 'Envio cliente'],
  ['resposta_cliente', 'Resposta cliente'],
  ['retificacoes', 'Retificações'],
  ['aprovado', 'Aprovado'],
];

export const STAGE_LABELS = Object.fromEntries(PIPELINE);
export const PHASE_ONE = ['novo', 'proposta_cliente'];
export const PHASE_TWO = PIPELINE.filter(([id]) => !PHASE_ONE.includes(id)).map(([id]) => id);

export const STATUS_BADGE = {
  active: {label: 'Em curso', tone: 'sky'},
  waiting_supplier: {label: 'Aguarda fornecedor', tone: 'yellow'},
  waiting_client: {label: 'Aguarda cliente', tone: 'yellow'},
  blocked: {label: 'Bloqueado', tone: 'pink'},
  completed: {label: 'Aprovado', tone: 'mint'},
  rejected: {label: 'Reprovado', tone: 'pink'},
  cancelled: {label: 'Cancelado', tone: 'lilac'},
};

export const TASK_KINDS = {
  ficha: 'Ficha técnica', malha: 'Malha', tingimento: 'Tingimento', grafico_bordado: 'Gráfico/bordado',
  bordado: 'Bordado', aplicacao: 'Aplicações', acessorios: 'Acessórios',
  shopping_modelagem: 'Shopping para modelagem', envio_cliente: 'Envio ao cliente', resposta_cliente: 'Resposta do cliente',
};

export const TASK_STATUSES = {pending: 'Pendente', in_progress: 'Em curso', waiting: 'A aguardar', done: 'Concluída', cancelled: 'Cancelada'};
export const ROLE_NAMES = {principal: 'Principal', parceria: 'Parceria', fitting: 'Fitting', qualidade: 'Qualidade', grafico: 'Gráfico'};
export const SOURCES = [['whatsapp', 'WhatsApp'], ['email', 'Email'], ['reuniao', 'Reunião'], ['telefone', 'Telefone'], ['outro', 'Outro']];

export function isPhaseOne(stage) {
  return PHASE_ONE.includes(stage);
}

export function columnsFor(board) {
  return board === 'portfolio' ? PIPELINE.filter(([id]) => isPhaseOne(id)) : PIPELINE.filter(([id]) => !isPhaseOne(id));
}

export function initials(name = '') {
  return String(name).split(/[\s+]+/).filter(Boolean).map(part => part[0]).slice(0, 2).join('').toUpperCase() || '—';
}
