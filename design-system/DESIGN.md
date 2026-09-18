# IncorpoData — Design System

Sistema visual do frontend (React + TypeScript + MapLibre). Fonte da verdade dos tokens:
`frontend/src/index.css` (`:root`) — espelhado em `design-system/design-tokens.json`.

Gerado/auditado em 2026-06-16 aplicando as skills `ui-ux-pro-max` e `design-system`.

## Princípios

- **Software técnico, claro e quieto.** A informação (lote, viabilidade, preço) é a estrela; a
  UI não compete. Flat/minimal, um único accent (teal), zero decoração gratuita.
- **Dado legível.** Números sempre em `tabular-nums` para não "pular" ao ordenar/atualizar.
- **Honestidade visual.** Estados de carregando/vazio/erro explícitos; o que é fase futura é
  marcado (`▸ fase 2/3`), não inventado.
- **Light-only por decisão.** Ferramenta de uso diurno (escritório/campo); dark mode não é meta
  do MVP — ausência é intencional, não trabalho pela metade.

## Tokens

### Cor (todas via variável; contraste verificado em branco)

| Token | Hex | Uso | Contraste |
|-------|-----|-----|-----------|
| `--ink` | `#181c1f` | texto principal | 15.9:1 (AAA) |
| `--muted` | `#6a747b` | texto secundário | 4.96:1 (AA) |
| `--muted-2` | `#6c767c` | texto terciário | 4.65:1 (AA) |
| `--accent` | `#0f766e` | marca, CTA, à venda | — |
| `--accent-ink` | `#0b524c` | texto/preço sobre claro | 7.9:1 (AAA) |
| `--accent-soft` | `#e7f1ef` | destaque (linha ativa, faixa altura) | — |
| `--bg` / `--surface` / `--surface-2` | `#f5f6f7` / `#fff` / `#fbfcfc` | fundos | — |
| `--border` / `--border-strong` | `#e4e7e9` / `#d2d7da` | divisores / controles | — |
| `--danger` | `#b91c1c` | erro | 5.9:1 (AA) |

> `--muted-2` era `#9aa2a8` (2.6:1, **reprovava** AA). Escurecido para `#6c767c` mantendo a hierarquia.

### Tipografia
- Stack do sistema (sem fonte custom — performance + neutralidade técnica).
- Base **14px** / line-height **1.45**. Escala: 11.5 · 12 · 12.5 · 13 · 13.5 · **14** · 16 · 20.
- Pesos: 400 corpo · 600 rótulos/títulos · 700 marca/destaque.
- No mobile, `select`/inputs sobem para **16px** (evita o auto-zoom do iOS).

### Espaço / Raio / Layout
- Ritmo base **8px** (4/8/12/16/24); 6/10/14/18 em controles densos.
- Raio: `--radius` 8px, `--radius-sm` 6px.
- Painel lateral 380px; breakpoint mobile 720px (painel full-width, mapa empilha em `45dvh`).

### Movimento
- Micro-interações **130ms ease** (hover de linha/botão).
- Mapa `fitBounds` 600ms — **0ms** sob `prefers-reduced-motion` (respeitado globalmente).

## Componentes (inventário)
- **Topbar** — marca (`h1`) + `FiltersBar` (bairro, área min/máx, **ordenar por**, só vagos, à venda).
- **MapView** — MapLibre + basemap CARTO Positron; fill/line por `a_venda`; **legenda** (vago/à venda).
- **ResultsList** — cabeçalho com contagem + **ordenação ativa**; linha com logradouro, área, zona,
  tag **à venda** (texto+cor), projeção e **preço/m²**.
- **LotFichaPanel** — abas Resumo/Completo; cards; **faixa de altura** ("Quanto pode subir");
  termos com glossário (sublinhado accent → tooltip).

## Auditoria (design-system Mode 2 · 0–10)

| Dimensão | Nota | Nota |
|----------|:----:|------|
| Consistência de cor | 9 | tudo via token; hex cru só em expressões de paint do mapa |
| Hierarquia tipográfica | 8 | escala clara; sem display font (proposital) |
| Ritmo de espaço | 7 | base 8px com alguns valores ímpares (6/10/14/18) |
| Consistência de componente | 9 | — |
| Responsivo | 8 | breakpoint 720px; `dvh` no mapa mobile |
| Dark mode | N/A | light-only por decisão de produto |
| Animação | 8 | sutil, com `reduced-motion` |
| Acessibilidade | 8 | contraste AA, labels, foco visível, cor≠único sinal, legenda |
| Densidade de informação | 8 | limpo |
| Polish | 8 | hover/ativo/loading/vazio/erro; preço; legenda |

**AI-slop check (Mode 3): aprovado** — sem gradiente gratuito, sem glassmorphism, sem roxo→azul
default, sem hero genérico. Paleta única coerente e intencional.

## Pendências (próximo passo de qualidade)
- **Virtualizar a lista** quando >50 itens (`/api/lots` traz até 2000) — risco de jank no DOM.
- **Code-split do MapLibre** (bundle ~962kB) via `import()` dinâmico.
- Padronizar valores de espaço ímpares no ritmo 4/8.
