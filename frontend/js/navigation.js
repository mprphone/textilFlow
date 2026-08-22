export const CORE_MODULE_IDS = ['overview','commercial','design','production','corte','confection','subcontracting','shipping','erp','tables','management'];
export const PLANT_MODULE_IDS = ['dyeing','printing','weaving','spinning','laundry','embroidery','finishing'];
export const DEFAULT_ENABLED_MODULES = [...CORE_MODULE_IDS];

function plantRoutes(id, extra = []) {
  return [
    [id, 'Controlo', '▣'],
    ...extra,
    ['people', 'Pessoas', '♙', 'recursos'],
    ['machines', 'Máquinas e planta', '⚙', 'recursos'],
    ['operations', 'Operações e tempos', '≋', 'recursos'],
  ];
}

export const MODULES = [
  {
    id:'overview', label:'Visão Geral', shortLabel:'Visão Geral', icon:'◫', home:'dashboard',
    defaultRoles:['admin','manager','planner','supervisor','viewer'],
    routes:[['dashboard','Centro de comando','◫'],['reports','Análises e indicadores','▥']],
    quick:[['dashboard','Atualizar centro de comando'],['reports','Abrir análises']],
  },
  {
    id:'commercial', label:'Produto Comercial', shortLabel:'Comercial', icon:'€', home:'costing',
    defaultRoles:['admin','manager','commercial','planner'],
    routes:[['costing','Propostas e custos','€'],['orders','Encomendas de clientes','▤'],['partners','Clientes e fornecedores','♧']],
    quick:[['costing','Criar proposta'],['orders','Abrir encomendas']],
  },
  {
    id:'design', label:'Desenvolvimento', shortLabel:'Designer', icon:'◇', home:'design-today',
    defaultRoles:['admin','manager','designer','planner'],
    navGroups:[
      {id:'pipeline', title:'Pipeline', hint:'Pedidos do cliente e percurso da amostra até à aprovação.'},
      {id:'controlo', title:'Controlo', hint:'O que está atrasado, à espera ou bloqueado.'},
      {id:'organizacao', title:'Organização', hint:'Distribuição do trabalho por designer e cliente.'},
      {id:'desenvolvimento', title:'Desenvolvimento', hint:'Fichas técnicas, amostras e passagem à produção.'},
    ],
    routes:[
      ['design-requests','Pedidos e referências','▤','pipeline'],
      ['design-samples','Desenvolvimento de amostras','◉','pipeline'],
      ['design-today','Prioridades de hoje','▣','controlo'],
      ['design-report','Relatório','▥','controlo'],
      ['design-organization','Por designer e cliente','♙','organizacao'],
      ['styles','Artigos e fichas técnicas','◇','desenvolvimento'],
      ['samples','Amostras e aprovações','◉','desenvolvimento'],
    ],
    quick:[['design-requests','Novo pedido de cliente'],['styles','Novo artigo'],['samples','Aprovar amostra']],
  },
  {
    id:'production', label:'Produção', shortLabel:'Produção', icon:'▶', home:'tracking',
    defaultRoles:['admin','manager','planner','supervisor','operator','quality'],
    routes:[['tracking','Controlo da produção','▤'],['quality','Qualidade','✓']],
    quick:[['tracking','Ver OF ativas'],['corte','Planear corte'],['confection-map','Planear confeção'],['subcontracts','Ver o que está fora']],
  },
  {
    id:'corte', label:'Corte', shortLabel:'Corte', icon:'✂', home:'corte',
    defaultRoles:['admin','manager','planner','supervisor','operator'],
    navGroups:[
      {id:'planear', title:'Planear', hint:'Corta primeiro. Sem peça cortada não há confeção.'},
      {id:'producao', title:'Chão de fábrica', hint:'Estendimentos e o que já saiu da mesa.'},
      {id:'config', title:'Configurar', hint:'Mesas e máquinas do corte.', collapsed:true},
    ],
    routes:[
      ['corte','Mapa e backlog','▦','planear'],
      ['cutting','Estendimentos','✂','producao'],
      ['corte-jobs','Controlo','▣','producao'],
      ['corte-lines','Mesas de corte','☰','config'],
      ['people','Pessoas','♙','config'],
      ['machines','Máquinas e planta','⚙','config'],
      ['operations','Operações e tempos','≋','config'],
    ],
    quick:[['corte','Planear o corte'],['cutting','Registar estendimento']],
  },
  {
    id:'confection', label:'Confeção', shortLabel:'Confeção', icon:'⌁', home:'confection-map',
    defaultRoles:['admin','manager','planner','supervisor','operator'],
    navGroups:[
      {id:'planear', title:'Planear', hint:'Programar OFs no mapa e ver se a linha aguenta.'},
      {id:'producao', title:'Produção e custos', hint:'O que saiu hoje e quanto custou.'},
      {id:'config', title:'Configurar a fábrica', hint:'Linhas, pessoas e máquinas. Só quando mudar.', collapsed:true},
    ],
    routes:[
      ['confection-map','Mapa e backlog','▦','planear'],
      ['confection','Capacidade','⌁','planear'],
      ['confection-plans','Plano por linha','▤','planear'],
      ['live','Em direto','●','producao'],
      ['confection-diary','Produção do dia','▶','producao'],
      ['floor','Posto na linha','▣','producao'],
      ['confection-costs','Custo por OF','€','producao'],
      ['confection-lines','Linhas de produção','☰','config'],
      ['people','Pessoas','♙','config'],
      ['machines','Máquinas e planta','⚙','config'],
      ['confection-machine-types','Tipos de máquina','⚙','config'],
      ['operations','Operações e tempos','≋','config'],
      ['confection-skills','Competências','♙','config'],
      ['confection-contractors','Confeçionadores','⇄','config'],
      ['confection-shifts','Turnos','◷','config'],
    ],
    quick:[['confection-map','Planear a semana'],['confection-diary','Registar produção do dia']],
  },
  {
    id:'dyeing', label:'Tinturaria', shortLabel:'Tinturaria', icon:'◉', home:'dyeing', plant:true,
    defaultRoles:['admin','manager','planner','supervisor','operator'],
    routes:plantRoutes('dyeing'),
    quick:[['dyeing','Abrir tinturaria'],['subcontracts','Ver o que está fora']],
  },
  {
    id:'printing', label:'Estamparia', shortLabel:'Estamparia', icon:'✦', home:'printing', plant:true,
    defaultRoles:['admin','manager','planner','supervisor','operator'],
    routes:plantRoutes('printing'),
    quick:[['printing','Abrir estamparia'],['subcontracts','Ver o que está fora']],
  },
  {
    id:'weaving', label:'Tecelagem', shortLabel:'Tecelagem', icon:'▦', home:'weaving', plant:true,
    defaultRoles:['admin','manager','planner','supervisor','operator'],
    routes:plantRoutes('weaving'),
    quick:[['weaving','Abrir tecelagem']],
  },
  {
    id:'spinning', label:'Fiação', shortLabel:'Fiação', icon:'◎', home:'spinning', plant:true,
    defaultRoles:['admin','manager','planner','supervisor','operator'],
    routes:plantRoutes('spinning'),
    quick:[['spinning','Abrir fiação']],
  },
  {
    id:'laundry', label:'Lavandaria', shortLabel:'Lavandaria', icon:'💧', home:'laundry', plant:true,
    defaultRoles:['admin','manager','planner','supervisor','operator'],
    routes:plantRoutes('laundry'),
    quick:[['laundry','Abrir lavandaria']],
  },
  {
    id:'embroidery', label:'Bordado', shortLabel:'Bordado', icon:'✳', home:'embroidery', plant:true,
    defaultRoles:['admin','manager','planner','supervisor','operator'],
    routes:plantRoutes('embroidery'),
    quick:[['embroidery','Abrir bordado']],
  },
  {
    id:'finishing', label:'Acabamento', shortLabel:'Acabamento', icon:'▣', home:'finishing', plant:true,
    defaultRoles:['admin','manager','planner','supervisor','operator'],
    routes:plantRoutes('finishing'),
    quick:[['finishing','Abrir acabamento']],
  },
  {
    id:'subcontracting', label:'Subcontratos', shortLabel:'Subcontratos', icon:'⇄', home:'subcontracts',
    defaultRoles:['admin','manager','commercial','planner','supervisor'],
    routes:[['subcontracts','Controlo de envios','⇄']],
    quick:[['subcontracts','Enviar ou receber trabalho']],
  },
  {
    id:'shipping', label:'Expedição', shortLabel:'Expedição', icon:'▰', home:'shipping',
    defaultRoles:['admin','manager','warehouse','commercial','planner'],
    routes:[['shipping','Cockpit de expedição','▰'],['inventory','Stocks e compras','▦']],
    quick:[['shipping','Preparar expedição'],['inventory','Consultar stock']],
  },
  {
    id:'erp', label:'ERP', shortLabel:'ERP', icon:'↔', home:'erp-docs',
    defaultRoles:['admin','manager','commercial','warehouse','planner'],
    routes:[
      ['erp-docs','Documentos','↔'],
      ['erp-capture','Ler fatura (foto / PDF)','◉'],
      ['erp-map','Artigos aprendidos','▣'],
      ['settings-primavera','Ligação Primavera','⚙'],
    ],
    quick:[['erp-capture','Fotografar fatura do fornecedor'],['erp-docs','Ver documentos']],
  },
  {
    id:'tables', label:'Tabelas', shortLabel:'Tabelas', icon:'▦', home:'tables-customers',
    defaultRoles:['admin','manager','commercial','planner','warehouse'],
    routes:[
      ['tables-customers','Clientes','♧'],
      ['tables-suppliers','Fornecedores','⇄'],
      ['tables-items','Artigos','▣'],
      ['tables-banks','Bancos','€'],
    ],
    quick:[['tables-customers','Abrir clientes'],['tables-items','Abrir artigos']],
  },
  {
    id:'management', label:'Gestão', shortLabel:'Gestão', icon:'⚙', home:'overheads',
    defaultRoles:['admin','manager'],
    routes:[['overheads','Custos gerais','◈'],['settings-users','Utilizadores e acessos','♙'],['settings-companies','Empresas e módulos','▣'],['settings-primavera','Integração Primavera','↔'],['settings','Configuração avançada','⚙']],
    quick:[['settings-companies','Definir módulos da empresa'],['settings-users','Gerir acessos']],
  },
];

export const MODULE_ACCESS_OPTIONS = MODULES.map(({id,label,plant})=>({id,label,plant:Boolean(plant)}));
