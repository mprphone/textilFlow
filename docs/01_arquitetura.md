# Arquitetura técnica

## Princípios

- Domínios isolados: identidade, configuração, parceiros, fábrica, produto, custos, produção, inventário e qualidade.
- Regras de negócio em `services/`; as rotas não calculam custos nem produtividade.
- Modelos, schemas, rotas e páginas divididos em ficheiros pequenos e coesos.
- Histórico operacional imutável para auditoria, eventos de produção e stock.
- Multiempresa em todos os registos através de `company_id`.
- Autorização por perfil e empresa.
- API REST documentada automaticamente com OpenAPI.

## Fichas evolutivas

Uma ficha combina campos estruturais estáveis com `custom_data` JSON. `FieldDefinition` descreve campos adicionais, tipo, secção, opções, obrigatoriedade e versão. `FormTemplate` define a organização da ficha e `WorkflowDefinition` define as etapas.

Quando uma ficha é alterada, o estado anterior é guardado em `StyleRevision`. Alterar ou desativar uma definição não destrói os valores históricos.

## Fluxo principal

```text
Cliente → Artigo/Ficha → BOM + Gama → Amostra/Costing
       → Encomenda → Ordem de fabrico → Lote → Atribuição
       → Evento por operador/máquina → Qualidade → Expedição
```

## Recolha de produção

Cada `ProductionEvent` liga uma ordem, lote, operação, funcionário, máquina e linha. Guarda quantidade boa/rejeitada, duração e custo direto. O serviço atualiza automaticamente progresso, WIP, estado e métricas.

Eventos e movimentos são imutáveis. Correções devem ser feitas através de eventos ou movimentos compensatórios, preservando a auditoria.

## Extensões externas

Integrações vivem atrás de adaptadores. O Primavera possui um contrato isolado em `primavera.py`; a ligação concreta depende das credenciais e métodos disponíveis na instalação real.
