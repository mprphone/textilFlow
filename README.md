# TextileFlow AI

Plataforma modular de PLM, ERP e MES para confeção têxtil. A aplicação gere o ciclo completo do artigo: ficha técnica, BOM, gama operatória, amostras, costing, encomenda, planeamento, corte, produção, qualidade, stock e expedição.

## Arranque

Requisitos: Docker Desktop com Docker Compose.

```powershell
.\scripts\start.ps1
```

Ou diretamente:

```powershell
docker compose up --build -d
```

- Aplicação: http://localhost:8080
- API e documentação: http://localhost:8000/docs
- Utilizador inicial: `admin`
- Palavra-passe inicial: `admin123`

Altere a palavra-passe e configure `APP_SECRET` antes de qualquer utilização real.

## Módulos operacionais

- Fichas técnicas adaptativas e versionadas
- Tipos de artigo, variantes, cores e tamanhos
- Materiais, BOM, consumos e desperdício
- Biblioteca de operações, SMV e instruções
- Amostras, tempos e custo real
- Costing por materiais, mão de obra, máquina, subcontrato e indiretos
- Encomendas, ordens de fabrico, lotes e atribuições
- Planeamento de carga e capacidade
- Terminal de chão de fábrica por operador/máquina/operação
- Corte, cortadores, planos, tecido, produção e custo
- WIP e localização da produção em tempo real
- Qualidade, defeitos e ações corretivas
- Stock por lote, movimentos e compras
- Funcionários, competências, linhas, máquinas e manutenção
- Custos gerais e centros de custo
- Relatórios por funcionário e máquina
- Auditoria e permissões por perfil
- Assistente baseado nos dados operacionais
- Adaptador isolado para futura integração Primavera

## Estrutura

O backend está separado por modelos de domínio, rotas, schemas e serviços. O frontend usa módulos ES independentes por página e componentes partilhados.

```text
backend/app/
  api/routes/       rotas HTTP por domínio
  models/           modelo de dados separado por domínio
  schemas/          validação dos pedidos
  services/         regras de negócio e análises
frontend/
  assets/           estilos
  js/pages/         módulos funcionais
  js/*.js           API, estado, formulários e componentes comuns
docs/               arquitetura, operação e pesquisa de produto
scripts/            arranque, paragem, backup e reposição
```

## Backup

```powershell
.\scripts\backup.ps1
```

Os backups são guardados em `backups/`. Para repor:

```powershell
.\scripts\restore.ps1 -BackupPath .\backups\textileflow-AAAAMMDD-HHMMSS.sql
```

## Paragem

```powershell
.\scripts\stop.ps1
```

`docker compose down` mantém os dados. Não use `docker compose down -v` em produção, porque remove a base de dados.

## Limites de integração

A base é funcional localmente e todos os fluxos internos persistem em PostgreSQL. Ligações a máquinas/IoT, leitores óticos, CAD, Primavera, email ou serviços externos exigem os protocolos, credenciais e mapeamentos reais de cada equipamento ou sistema.
