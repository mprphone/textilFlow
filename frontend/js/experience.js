import { esc } from './format.js?v=20260819-5';
import { closeModal, openModal } from './ui.js?v=20260820-5';

const commands = [
  {group:'Ir para', icon:'⌂', label:'Centro de comando', detail:'Prioridades, risco e indicadores', route:'dashboard', keywords:'inicio dashboard resumo'},
  {group:'Ir para', icon:'▤', label:'Rasto das ordens', detail:'Onde está a OF e se foi subcontratada', route:'tracking', keywords:'rasto of distribuicao subcontrato onde esta'},
  {group:'Ir para', icon:'✂', label:'Mapa de corte', detail:'Gantt das mesas, backlog e entrega', route:'corte', keywords:'corte mesa marcador gantt plano estendimento'},
  {group:'Ir para', icon:'▦', label:'Mapa de produção de confeção', detail:'Backlog, Gantt, carga e cenários', route:'confection-map', keywords:'gantt mapa confeção backlog sam horas extra'},
  {group:'Ir para', icon:'⌁', label:'Confeção e capacidade', detail:'Capacidade real, plano, pessoas e execução', route:'confection', keywords:'costura linha sam turno capacidade confeção'},
  {group:'Ir para', icon:'▣', label:'Prioridades de desenvolvimento', detail:'Atrasos, esperas e bloqueios do atelier', route:'design-today', keywords:'hoje designer amostra atraso bloqueio'},
  {group:'Ir para', icon:'▤', label:'Pedidos e referências', detail:'Pedido do cliente e distribuição pelas designers', route:'design-requests', keywords:'pedido referencia briefing cliente designer'},
  {group:'Ir para', icon:'◉', label:'Pipeline de amostras', detail:'Da ficha técnica à aprovação do cliente', route:'design-samples', keywords:'amostra pipeline ficha modelagem confeção'},
  {group:'Ir para', icon:'♙', label:'Organização do desenvolvimento', detail:'Carga por designer e por cliente', route:'design-organization', keywords:'designer cliente distribuicao carga'},
  {group:'Ir para', icon:'◇', label:'Artigos e fichas técnicas', detail:'Produto, materiais e operações', route:'styles', keywords:'modelo ficha produto'},
  {group:'Ir para', icon:'◉', label:'Amostras e aprovações', detail:'Desenvolvimento e passagem à produção', route:'samples', keywords:'amostra aprovar designer produção'},
  {group:'Ir para', icon:'€', label:'Propostas e custos reais', detail:'Margem e orçamentado vs. realizado', route:'costing', keywords:'preço margem costing orçamento'},
  {group:'Ir para', icon:'▤', label:'Encomendas e ordens', detail:'Cliente, OF, lotes e atribuições', route:'orders', keywords:'ordem fabrico of lote'},
  {group:'Ir para', icon:'●', label:'Produção em direto na confeção', detail:'Operadores e linhas de costura', route:'live', keywords:'tempo real fabrica linha'},
  {group:'Ir para', icon:'✓', label:'Qualidade', detail:'Inspeções, defeitos e ações', route:'quality', keywords:'defeito rejeição controlo'},
  {group:'Ir para', icon:'▦', label:'Stocks e compras', detail:'Materiais, lotes e fornecedores', route:'inventory', keywords:'armazem material compra'},
  {group:'Ir para', icon:'▥', label:'Análises', detail:'Pessoas, máquinas e custos', route:'reports', keywords:'relatorio indicador'},
  {group:'Ir para', icon:'◉', label:'Tinturaria', detail:'Cubas, lotes e trabalhos internos', route:'dyeing', keywords:'tinturaria tingimento cubas'},
  {group:'Ir para', icon:'✦', label:'Estamparia', detail:'Mesas, telas e trabalhos internos', route:'printing', keywords:'estamparia serigrafia'},
  {group:'Ir para', icon:'▦', label:'Tecelagem', detail:'Teares e urdideiras', route:'weaving', keywords:'tecelagem tear urdideira'},
  {group:'Ir para', icon:'◎', label:'Fiação', detail:'Cardas e contínuas', route:'spinning', keywords:'fiacao fio carda'},
  {group:'Ir para', icon:'⇄', label:'Subcontratos', detail:'O que está fora, prazos e receção', route:'subcontracts', keywords:'externo fornecedor tingimento bordado estampagem atraso'},
  {group:'Ir para', icon:'▰', label:'Expedição', detail:'Preparação, checklist e saída', route:'shipping', keywords:'expedir transportador documento saída'},
  {group:'Ir para', icon:'↔', label:'ERP', detail:'Primavera, faturas, foto e artigos aprendidos', route:'erp-docs', keywords:'primavera fatura requisição nc nd guia compra venda gemini pdf'},
  {group:'Ação rápida', icon:'▶', label:'Registar produção', detail:'Abrir terminal da linha de confeção', route:'floor', keywords:'produzir peça operador', action:true},
  {group:'Ação rápida', icon:'€', label:'Criar proposta ao cliente', detail:'Calcular custo e margem', route:'costing', keywords:'novo orçamento cliente', action:true},
  {group:'Ação rápida', icon:'▤', label:'Novo pedido de cliente', detail:'Registar briefing e referências para as designers', route:'design-requests', keywords:'pedido amostra referencia briefing', action:true},
  {group:'Ação rápida', icon:'◇', label:'Criar artigo', detail:'Nova ficha técnica adaptativa', route:'styles', keywords:'novo produto modelo', action:true},
  {group:'Ação rápida', icon:'✂', label:'Enviar a subcontrato', detail:'Tinturaria, estamparia ou corte externos', route:'subcontracts', keywords:'cortador tecido tingimento estamparia', action:true},
  {group:'Ação rápida', icon:'!', label:'Registar problema de qualidade', detail:'Inspeção e defeito', route:'quality', keywords:'rejeitar defeito', action:true},
  {group:'Ação rápida', icon:'▦', label:'Movimentar material', detail:'Consumo, receção ou transferência', route:'inventory', keywords:'stock lote receber', action:true},
];
let canNavigate = () => true;

function go(command) {
  if (!canNavigate(command.route)) return;
  closeModal();
  const recent = JSON.parse(localStorage.getItem('tf_recent_commands') || '[]').filter(item => item !== command.route);
  localStorage.setItem('tf_recent_commands', JSON.stringify([command.route, ...recent].slice(0, 5)));
  location.hash = `#/${command.route}`;
}

function commandMarkup(items) {
  let group = '';
  return items.map((command, index) => {
    const heading = command.group !== group ? `<div class="command-group">${esc(command.group)}</div>` : '';
    group = command.group;
    return `${heading}<button class="command-item ${index === 0 ? 'selected' : ''}" data-command-route="${command.route}"><span class="command-icon">${command.icon}</span><span><b>${esc(command.label)}</b><small>${esc(command.detail)}</small></span><kbd>↵</kbd></button>`;
  }).join('');
}

export function openCommandPalette(actionsOnly = false) {
  let visible = commands.filter(command => canNavigate(command.route) && (!actionsOnly || command.action));
  openModal(actionsOnly ? 'O que quer criar ou registar?' : 'Onde quer ir ou o que quer fazer?', `
    <div class="command-palette">
      <div class="command-search"><span>⌕</span><input id="command-search-input" autocomplete="off" placeholder="Escreva, por exemplo: custo, produção, artigo…"></div>
      <div class="command-results" data-command-results>${commandMarkup(visible)}</div>
      <div class="command-hint"><span>↑ ↓ para navegar</span><span>Enter para abrir</span><span>Esc para fechar</span></div>
    </div>`, 'Não precisa de saber em que menu está cada função.');
  const input = document.getElementById('command-search-input');
  const results = document.querySelector('[data-command-results]');
  let selected = 0;
  const draw = () => {
    const query = input.value.toLowerCase().trim();
    visible = commands.filter(command => canNavigate(command.route) && (!actionsOnly || command.action) && `${command.label} ${command.detail} ${command.keywords}`.toLowerCase().includes(query));
    selected = 0;
    results.innerHTML = visible.length ? commandMarkup(visible) : '<div class="command-empty">Não encontrei essa ação. Tente outra palavra.</div>';
  };
  input.addEventListener('input', draw);
  input.addEventListener('keydown', event => {
    if (!visible.length) return;
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault(); selected = (selected + (event.key === 'ArrowDown' ? 1 : -1) + visible.length) % visible.length;
      results.querySelectorAll('.command-item').forEach((item, index) => item.classList.toggle('selected', index === selected));
      results.querySelectorAll('.command-item')[selected]?.scrollIntoView({block:'nearest'});
    }
    if (event.key === 'Enter') { event.preventDefault(); go(visible[selected]); }
  });
  results.addEventListener('click', event => {
    const item = event.target.closest('[data-command-route]');
    if (item) go(visible.find(command => command.route === item.dataset.commandRoute));
  });
  requestAnimationFrame(() => input.focus());
}

export function initExperience(options = {}) {
  if (typeof options.canNavigate === 'function') canNavigate = options.canNavigate;
  document.getElementById('global-command')?.addEventListener('click', () => openCommandPalette(false));
  document.getElementById('quick-action')?.addEventListener('click', () => openCommandPalette(true));
  document.querySelectorAll('[data-shortcut-route]').forEach(button => button.addEventListener('click', () => { location.hash = `#/${button.dataset.shortcutRoute}`; }));
  document.addEventListener('keydown', event => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); openCommandPalette(false); }
  });
}
