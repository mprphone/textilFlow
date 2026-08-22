# Guia de operação

## Configuração inicial

1. Em **Configuração**, crie tipos de artigo, modelos, campos e fluxos.
2. Em **Clientes e fornecedores**, introduza parceiros e certificações.
3. Em **Máquinas e linhas**, configure unidades, departamentos, linhas e equipamentos.
4. Em **Funcionários**, introduza custos/hora e competências.
5. Em **Operações e tempos**, crie a biblioteca de métodos e SMV.
6. Em **Stocks e compras**, configure materiais, custos e lotes.

## Do artigo à produção

1. Crie o artigo em **Artigos e fichas**.
2. Abra a ficha e preencha BOM, gama, variantes e amostras.
3. Crie a folha de custo e use **Recalcular** para ler BOM e gama.
4. Crie a encomenda e as respetivas linhas.
5. Crie a ordem de fabrico, lotes e atribuições.
6. Registe corte e consumos.
7. No **Terminal de produção**, selecione a tarefa, cronometre e registe peças boas/rejeitadas.
8. Registe inspeções no módulo de qualidade.
9. Consulte WIP, localização e desempenho em **Produção em direto** e **Análises**.

## Fórmulas principais

- Eficiência do funcionário = minutos-padrão ganhos / minutos reais × 100.
- Custo de mão de obra = custo/hora do funcionário / 60 × minutos reais.
- Custo de máquina = custo/hora da máquina / 60 × minutos reais.
- Material na BOM = quantidade × (1 + desperdício %) × custo unitário.
- Margem = (preço de venda − custo total) / preço de venda × 100.

## Segurança dos históricos

Auditoria, eventos de produção, revisões e movimentos de stock não podem ser editados ou eliminados pela API genérica. Use registos compensatórios para corrigir quantidades.
