# IncorpoData — Valor Residual + IncorpoScore (spec)

Data: 2026-06-27 · Status: aprovado p/ implementação · Depende de: `2026-06-15-terraiq-app-design.md`

## Visão

Hoje o app **mostra** lotes; o decisor quer que ele **ranqueie negócios**. Duas entregas
fecham os Jobs 2–3 do spec original e transformam consulta em decisão:

1. **Valor Residual** ("quanto pagar") — método involutivo. Inverte o `estimar_vgv` que já
   existe. É o número-herói que vai ao comitê. Preenche o placeholder `▸ fase 3` em
   `LotFichaPanel.tsx:238`.
2. **IncorpoScore** — nota 0–100 + decomposição em 4 eixos, para **ordenar** o recorte e
   surfacear as melhores oportunidades sem abrir lote por lote.

Princípio herdado do projeto: **honestidade > precisão falsa**. Toda nota mostra decomposição
e premissas; nada de caixa-preta. O score **nunca** sobrepõe o portão legal/altura.

## Premissas (decididas — 2026-06-27)

| Premissa | Default | Observação |
|----------|---------|------------|
| Margem-alvo do incorporador | **20%** | sobre VGV; resulta em terreno ~15–20% do VGV (benchmark Sienge/Swiss Capital) |
| Impostos s/ receita | 6% | RET incorporação afetada (~4%) + extras |
| Comercialização | 5% | corretagem + marketing |
| Indiretos | 5% | projetos, legalização, incorporação, admin de obra |
| **Custos não-obra (soma)** | **16% do VGV** | os três acima; editável |
| Custo de obra | **R$ 2.700/m²** construído | CUB-PB R8-N R$ 1.692/m² (Sinduscon-PB, maio/2026) × ~1,6 (BDI + elevador + fundação + projetos, não inclusos no CUB). Premissa **mais sensível** → exibir sempre |
| Formato do score | número 0–100 **+** decomposição | confirmado |

---

## Parte A — Valor Residual (método involutivo)

### Fórmula

```
fator_vgv      = 1 − custos_pct − margem_alvo            # default = 1 − 0,16 − 0,20 = 0,64
residual_pp    = vgv_por_pavimento × fator_vgv − area_projecao × custo_obra_m2
residual_total = residual_pp × pavimentos
               = vgv_total × fator_vgv − area_construida × custo_obra_m2   (idêntico)
```

- **Por pavimento** = headline robusto: independe da premissa de altura (espacial em JP),
  exatamente como o `vgv_por_pavimento` já faz.
- **Total** = sob a premissa de `pavimentos`.
- **Faixa Q1–Q3**: o custo de obra é fixo (não depende do preço de venda), então
  `residual_min = vgv_total_min × fator_vgv − custo_obra`. A faixa **alarga** e pode cruzar o
  zero — honestidade sobre incerteza (lote pode ser inviável no piso da faixa).
- **terreno_pct_vgv** = `residual_total / vgv_total` → comparar com a régua 15–20%. Negativo =
  inviável às premissas (marca "inviável", não inventa número).
- **Barganha** (só com anúncio casado): `gap_pct = (residual_total − preco_pedido) / residual_total`.
  `> 0` cabe no bolso (margem de negociação); `< 0` caro demais p/ a margem-alvo.

### Código (`src/api/viability.py`) — função pura, testável (o moat)

```python
# Premissas do involutivo (o incorporador ajusta; defaults transparentes p/ ranquear em massa).
MARGEM_ALVO_PADRAO         = 0.20
IMPOSTOS_PCT_PADRAO        = 0.06
COMERCIALIZACAO_PCT_PADRAO = 0.05
INDIRETOS_PCT_PADRAO       = 0.05
# Custo de obra p/ ranquear lotes SEM custo informado. CALIBRAR ao CUB-PB + BDI.
# É a premissa mais sensível do residual → sempre exibida na ficha.
CUSTO_OBRA_M2_PADRAO       = 3800.0   # R$/m² construído (médio padrão JP) — A CALIBRAR

@dataclass(frozen=True)
class ResidualEstimate:
    custo_obra_m2: float
    margem_alvo: float
    custos_indiretos_pct: float          # soma impostos+comerc+indiretos
    residual_por_pavimento: float
    residual_por_pavimento_min: float | None
    residual_por_pavimento_max: float | None
    residual_total: float
    residual_total_min: float | None
    residual_total_max: float | None
    terreno_pct_vgv: float | None        # residual_total / vgv_total
    preco_pedido: float | None
    gap_pct: float | None
    cabe_no_bolso: bool | None

def estimar_residual(
    vgv: VGVEstimate,
    custo_obra_m2: float = CUSTO_OBRA_M2_PADRAO,
    margem_alvo: float = MARGEM_ALVO_PADRAO,
    impostos_pct: float = IMPOSTOS_PCT_PADRAO,
    comercializacao_pct: float = COMERCIALIZACAO_PCT_PADRAO,
    indiretos_pct: float = INDIRETOS_PCT_PADRAO,
    preco_pedido: float | None = None,
) -> ResidualEstimate:
    """Máximo a pagar pelo terreno p/ atingir a margem-alvo. Inverso do VGV (involutivo)."""
    custos_pct = impostos_pct + comercializacao_pct + indiretos_pct
    fator = 1.0 - custos_pct - margem_alvo
    obra_pp = vgv.area_projecao_m2 * custo_obra_m2
    res_pp = vgv.vgv_por_pavimento * fator - obra_pp
    res_total = res_pp * vgv.pavimentos
    # faixa: custo de obra é fixo; só o VGV varia com Q1/Q3
    res_pp_min = vgv.vgv_por_pavimento_min * fator - obra_pp if vgv.vgv_por_pavimento_min is not None else None
    res_pp_max = vgv.vgv_por_pavimento_max * fator - obra_pp if vgv.vgv_por_pavimento_max is not None else None
    res_total_min = res_pp_min * vgv.pavimentos if res_pp_min is not None else None
    res_total_max = res_pp_max * vgv.pavimentos if res_pp_max is not None else None
    terreno_pct = res_total / vgv.vgv_total if vgv.vgv_total else None
    gap = cabe = None
    if preco_pedido is not None and res_total > 0:
        gap = (res_total - preco_pedido) / res_total
        cabe = gap >= 0
    return ResidualEstimate(custo_obra_m2, margem_alvo, custos_pct, res_pp, res_pp_min,
        res_pp_max, res_total, res_total_min, res_total_max, terreno_pct, preco_pedido, gap, cabe)
```

**Não** mexer em `estimar_vgv` (preserva os 23 testes atuais). A `margem` simples que ele já
calcula vira detalhe secundário; o residual é o número de decisão.

---

## Parte B — IncorpoScore (ranking 0–100)

Composto de 4 eixos, cada um normalizado 0–1 por **função de transferência com âncoras
explícitas** (não percentil) — assim a nota de um lote é estável e calculável sozinho, sem
depender da coorte. As âncoras seguem o mesmo playbook do `AREA_LOTE_SUSPEITA_M2`: calibrar
da distribuição real de JP (`viability.py:15-20` é o precedente).

```
IncorpoScore = 100 × (0,35·Rentabilidade + 0,25·Aproveitamento
                    + 0,25·Localização   + 0,15·Confiança)
               × penalidades_multiplicativas
```

| Eixo | Peso | Sinal (dado atual) | Transferência → 0–1 |
|------|------|--------------------|---------------------|
| **Rentabilidade** | 35% | com anúncio: `gap_pct`; sem: `terreno_pct_vgv` | barganha: `clamp(0,5 + gap/0,40)` · estrutural: `clamp(terreno_pct_vgv/0,20)` |
| **Aproveitamento** | 25% | `vgv_por_pavimento / area_lote` (R$ VGV/pavto por m² de terreno; robusto a altura) | `clamp((x − LOW)/(HIGH − LOW))`, âncoras A CALIBRAR |
| **Localização** | 25% | nível `preco_m2` (raio/bairro) + tendência (`scraped_at`, ▸ fase C) | nível normalizado; tendência renormaliza quando existir |
| **Confiança** | 15% | `n_comps` (log) + IQR relativo `(q3−q1)/mediana` | n: 5→0,3 … 30→1,0 · IQR: 0→1, 0,6→0 |

**Penalidades multiplicativas** (portão de risco):
- `geometria_suspeita` ou **sem zona/sigla** → **não ranqueia** (sem envelope confiável).
- altura restrita (IPHAEP/barreira) → ×0,7 (produto vertical limitado).

**Transparência:** cada eixo vira nota 0–10 na ficha + `nota_metodo` ("relativo às premissas,
preliminar; não substitui projeto/avaliação"). Tendência de valorização aparece como `▸ fase`
até a série de `scraped_at` existir.

> v2 (refino): trocar âncoras por **percentil empírico dentro do bairro**. Mais robusto, exige
> coorte calculada. v1 entrega com âncoras calibradas da distribuição real (1 query de quantis).

---

## Schemas (`src/api/schemas.py`)

```python
class Residual(BaseModel):
    custo_obra_m2: float
    margem_alvo: float
    custos_indiretos_pct: float
    residual_por_pavimento: float
    residual_por_pavimento_min: float | None = None
    residual_por_pavimento_max: float | None = None
    residual_total: float
    residual_total_min: float | None = None
    residual_total_max: float | None = None
    terreno_pct_vgv: float | None = None
    preco_pedido: float | None = None
    gap_pct: float | None = None
    cabe_no_bolso: bool | None = None
    premissas: str

class ScoreEixo(BaseModel):
    nota: float            # 0–10
    label: str
    detalhe: str | None = None

class Score(BaseModel):
    total: float           # 0–100
    rentabilidade: ScoreEixo
    aproveitamento: ScoreEixo
    localizacao: ScoreEixo
    confianca: ScoreEixo
    nota_metodo: str

# LotFicha ganha:
#   residual: Residual | None = None
#   score: Score | None = None
#   residual_bloqueado: bool = False   # gate freemium, igual vgv_bloqueado
```

Gate: residual + score atrás do flag de plano `vgv_detalhado` (mesmo padrão de `lots.py:333-336`).

## API

- `_load_ficha` (`src/api/lots.py`): após montar o `vgv`, chamar `estimar_residual(est, preco_pedido=listing.preco)` e o score; anexar à ficha. Respeitar a guarda de geometria suspeita (residual suprimido junto do VGV).
- **Novo** `GET /api/oportunidades?bairro=&limit=20&margem_alvo=&custo_obra_m2=` — calcula VGV+residual+score para o recorte filtrado (cap de segurança no nº de lotes), ordena por score desc, devolve linha enxuta (`lot_id, logradouro, bairro, area, vgv_total, residual_total, terreno_pct_vgv, gap_pct, score`). Feature paga.
- `_ORDER` de `/api/lots` **não** ganha `score` (precisa de cálculo cross-lote, não é coluna SQL). Ranking vive no endpoint novo. Caminho de escala: materializar `geo.lote_score` em refresh periódico.

## Testes (`tests/test_viability.py`) — puros, sem DB

- `residual` básico com números conhecidos (espelhar `test_vgv_*`).
- faixa Q1–Q3 propaga; custo fixo → banda alarga.
- residual negativo → `terreno_pct_vgv < 0`, `cabe_no_bolso` coerente.
- `gap_pct`: preço pedido abaixo (>0, cabe) e acima (<0, caro) do residual.
- score: eixos clampados 0–1; `geometria_suspeita`/sem-zona não ranqueia; monotonia (maior gap → maior rentabilidade); penalidade altura ×0,7.

## Frontend

- **types.ts**: tipos `Residual`, `Score`, `ScoreEixo`; campos em `LotFicha`.
- **LotFichaPanel — Resumo**: herói "Quanto pagar: **até R$ X**" ao lado do VGV; badge de barganha quando `gap_pct > 0` ("**−22%** vs pedido"); decomposição do score em 4 mini-barras.
- **LotFichaPanel — Completo**: trocar `"Valor residual" ▸ fase 3` (linha 238) pelo residual real (total + faixa + terreno%VGV + premissas).
- **Nova view "Oportunidades"**: tabela ranqueada do recorte (score, residual, gap, área) → clique abre a ficha. É o que vira "lista de negócios".
- **client.ts**: `getOportunidades(params)`.

## Fases (ordem de alavancagem)

| Fase | Entrega | Risco |
|------|---------|-------|
| **A** | `estimar_residual` + schema + ficha "quanto pagar" + testes | baixo — exato, sem calibração; preenche `▸ fase 3` |
| **B** | IncorpoScore + `/api/oportunidades` + view Oportunidades | médio — calibrar âncoras da distribuição real de JP |
| **C** | Valorização (série `scraped_at`) → eixo Localização | médio — depende de acumular snapshots |

Começar pela **Fase A**: é o coração do pedido ("quanto pagar"), é exata (sem risco de
calibração) e destrava o PDF de comitê com o número que decide.
