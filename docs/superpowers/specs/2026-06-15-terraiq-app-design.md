# TerraIQ — App de viabilidade de terrenos (spec)

Data: 2026-06-15 · Status: aprovado p/ implementação

## Visão
App web que responde, por lote de João Pessoa: **(1) o que cabe construir** (envelope LUOS),
**(2) qual o melhor uso**, **(3) quanto vale pagar** (valor residual). Objetivo: otimizar,
agilizar e baratear a *avaliação* e a *originação* de terreno para construtora/incorporadora.
Não baixa o preço do dono — reduz custo/risco de avaliar e evita pagar caro demais.

Contexto de mercado e concorrência: ver memória `terraiq-market-competition`. Nicho (envelope
por lote + "à venda agora" + workflow) está aberto em JP.

## Os 3 jobs (sequência por dificuldade/defensibilidade)
| Job | Saída | Depende de | Fase |
|-----|-------|------------|------|
| 1. Cabe Y | projeção térreo, permeável, altura, usos | LUOS + geo (já existe) | **MVP** |
| 2. Melhor uso | uso recomendado | Job 1 + demanda | 2 |
| 3. Valor W | valor residual ótimo | Job 2 + custos + comps | 2-3 |

## Usuários
- **Decisor/sócio** — vista Resumo (3 respostas, mobile). Recebe PDF.
- **Analista de terras** — vista Completa: mapa + filtros + tabela + landbank (power-user).

## Interface (3 telas)
1. **Explorar** — mapa de lotes (pan/zoom/click) + filtros + lista de resultados.
2. **Ficha do lote** — toggle `Resumo | Completo`.
3. **Landbank** — pipeline (triagem→análise→opção→due diligence→adquirido/descartado).

## Stack
- **Frontend:** Vite + React + TypeScript + **MapLibre GL JS**. (Next descartado: app logado, SEO irrelevante, backend é Python.)
- **API:** FastAPI (Python) — serve dados do lote + regra de viabilidade.
- **DB:** PostgreSQL + PostGIS (já existe). Tiles de lote via **Martin/pg_tileserv** quando escalar.
- **Migrations:** Alembic para o schema `app` (stateful: users, landbank). Skill `database-migrations`.

## Dados (já existe)
`geo.lotes`, `geo.zonas`, `zoning.parametros`, `geo.lote_zona` (projeção/permeável),
`geo.lote_restricao` (faixa orla/IPHAEP/barreira → `altura_livre`), `market.anuncios` +
`market.anuncio_lote`. SRID interno 31985; API reprojeta p/ 4326 (MapLibre).

### Novo (Fase 3, via migration) — schema `app`
- `app.users` (auth B2B)
- `app.landbank_items` (lote salvo + estágio do pipeline + notas)
- `app.saved_searches`
- `app.error_reports` ("⚑ reportar erro" — realimenta acurácia/moat)

## Fases
1. **API read-only** — `/api/lots` (GeoJSON), `/api/lots/{id}` (ficha), `/api/bairros`. ← agora
2. **Frontend** — mapa Bancários + ficha (2 densidades) + filtros. (claude-design, frontend-patterns)
3. **App schema + auth + landbank** — Alembic. (database-migrations)
4. **PDF, saved searches, polish.** Depois: tiles (Martin), Jobs 2-3.

## MVP
Bairro **Bancários**, **Job 1**. Bancários é interior → quase tudo `altura_livre`, evitando o
escalonamento da orla (a parte mais difícil) e ainda provando o motor ponta a ponta.

## Princípios
- Acurácia é existencial → lógica de viabilidade testada; `reportar erro` no produto.
- Honestidade: não inventar nº de pavimentos/unidades sem base; marcar Jobs 2-3 como "▸ fase".
- LGPD: não estocar telefone; revelar contato do anúncio sob demanda (guardar só ponteiro).
