export const esc = value => String(value ?? '').replace(/[&<>'"]/g, char => ({ '&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;' }[char]));
export const finiteNumber = (value, fallback = 0) => {
  const parsed = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
};
export const number = value => finiteNumber(value).toLocaleString('pt-PT', { maximumFractionDigits: 2 });
export const precise = value => finiteNumber(value).toLocaleString('pt-PT', { minimumFractionDigits: 2, maximumFractionDigits: 4 });
export const money = value => finiteNumber(value).toLocaleString('pt-PT', { style: 'currency', currency: 'EUR', minimumFractionDigits: 2, maximumFractionDigits: 2 });
export const preciseMoney = money;
export const percent = value => `${finiteNumber(value).toLocaleString('pt-PT', { maximumFractionDigits: 1 })}%`;
function safeDate(value, options = undefined, dateOnly = false) {
  if (!value) return '—';
  const parsed = new Date(dateOnly ? `${String(value).slice(0, 10)}T12:00:00` : value);
  if (Number.isNaN(parsed.getTime())) return '—';
  return new Intl.DateTimeFormat('pt-PT', options).format(parsed);
}
export const date = value => safeDate(value, undefined, true);
export const datetime = value => safeDate(value, { dateStyle: 'short', timeStyle: 'short' });

const labels = {
  draft:'Rascunho', approved:'Aprovado', obsolete:'Obsoleto', development:'Em desenvolvimento', production:'Em produção', inactive:'Inativo',
  prepared:'Preparado', posted:'Lançado', converted:'Transformado',
  requisition:'Requisição', supplier_transport:'Guia fornecedor', stock_receipt:'Entrada stock',
  purchase_invoice:'Fatura compra', purchase_credit:'NC compra', purchase_debit:'ND compra',
  sales_invoice:'Fatura venda', sales_credit:'NC cliente', sales_debit:'ND cliente', sales_delivery:'Guia cliente',
  planned:'Planeado', released:'Libertado', queued:'Em fila', in_progress:'Em curso', paused:'Em pausa', completed:'Concluído', cancelled:'Cancelado',
  synced:'Sincronizado', local:'Só local', failed:'Falhou',
  confirmed:'Confirmado', ready:'Pronto', shipped:'Expedido', waiting:'Em espera', blocked:'Bloqueado', running:'Em funcionamento', stopped:'Parado',
  active:'Ativo', available:'Disponível', quarantine:'Em quarentena', consumed:'Consumido', valid:'Válido', expired:'Expirado', sent:'Enviado', partial:'Parcial', received:'Recebido', problem:'Incidência',
  material:'Materiais', labor:'Mão de obra', machine:'Máquinas', subcontract:'Serviços externos', overhead:'Custos gerais', other:'Outros',
  fabric:'Tecido / malha', thread:'Linhas', trim:'Acessórios', label:'Etiquetas', packaging:'Embalagem', chemical:'Químicos',
  dyeing:'Tinturaria', printing:'Estamparia', sewing:'Confeção', embroidery:'Bordado', laundry:'Lavandaria', finishing:'Acabamento', transport:'Transporte', cutting:'Corte',
  issue:'Saída para produção', consume:'Consumo', receipt:'Receção', return:'Devolução', transfer_in:'Transferência de entrada', transfer_out:'Transferência de saída', adjustment_in:'Acerto de entrada', adjustment_out:'Acerto de saída',
  online:'Em linha', objective:'No objetivo', below:'Abaixo do objetivo', concept:'Conceito', proto:'Protótipo', fitting:'Prova', size_set:'Grade de tamanhos', pps:'Amostra pré-produção', archived:'Arquivado',
  novo:'Pedido recebido', proposta_cliente:'Referências e distribuição', ficha_tecnica:'Ficha técnica', desenvolvimento_malha:'Preparação materiais', modelagem:'Modelagem', confecao:'Confeção', finalizacao:'Finalização da amostra', envio_cliente:'Envio cliente', resposta_cliente:'Resposta cliente', retificacoes:'Retificações', aprovado:'Aprovado',
  waiting_supplier:'Aguarda fornecedor', waiting_client:'Aguarda cliente', rejected:'Reprovado', high:'Risco alto', medium:'Risco médio', low:'Sem risco',
  ficha:'Ficha técnica', malha:'Malha', tingimento:'Tingimento', grafico_bordado:'Gráfico/bordado', bordado:'Bordado', aplicacao:'Aplicações', acessorios:'Acessórios', shopping_modelagem:'Shopping para modelagem',
  principal:'Principal', parceria:'Parceria', qualidade:'Qualidade', grafico:'Gráfico',
  whatsapp:'WhatsApp', reuniao:'Reunião', telefone:'Telefone',
  forecast:'Proposta provável', third_party:'Produção para terceiros', internal:'Interna', external:'Externa',
  absence:'Falta', holiday:'Feriado', vacation:'Férias', training:'Formação', meeting:'Reunião', maintenance:'Manutenção', overtime:'Horas extra',
  limited:'Limitada', unavailable:'Indisponível', adaptive:'Adaptativa', fixed:'Fixa',
};

export function humanize(value) {
  if (value === null || value === undefined || value === '') return '—';
  const raw = String(value);
  const key = raw.toLowerCase();
  return labels[key] || raw.replaceAll('_', ' ').replace(/^./, char => char.toUpperCase());
}

export function badge(value) {
  const raw = String(value ?? '—');
  const key = raw.toLowerCase();
  const color = ['completed','approved','aprovad','active','available','valid','concluído','running','ready','received','objective','synced','sincronizado'].some(word => key.includes(word)) ? 'green'
    : ['rejected','cancelled','blocked','overdue','danger','parada','expired','risk','failed','falhou'].some(word => key.includes(word)) ? 'red'
    : ['in_progress','confirmed','sent','conditional','warning','produção','partial','paused','waiting'].some(word => key.includes(word)) ? 'amber' : 'blue';
  return `<span class="badge ${color}">${esc(humanize(raw))}</span>`;
}

export function progress(value, color = '') {
  const safe = Math.max(0, Math.min(100, finiteNumber(value)));
  return `<div class="progress ${color}"><span style="width:${safe}%"></span></div><small>${safe.toFixed(1)}%</small>`;
}
