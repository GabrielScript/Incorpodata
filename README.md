# IncorpoData — Inteligência de terrenos de João Pessoa

Base de dados viva da **oferta de solo** de João Pessoa/PB, cruzando cadastro, zoneamento. Cliente-âncora: **construtoras/incorporadoras/Imobiliárias/Corretores**.

## Estratégia (decidida)
- **Cliente-âncora:** construtora.
- **Ordem:** construir o **ativo de dados** primeiro.
- **Moat (núcleo legal e durável):** espinha geo + zoneamento (Filipeia + LUOS).
- **Gatilho de demanda (camada efêmera):** anúncios raspados (preço, "à venda agora", contato sob demanda).

## Os dois layers
1. **Geo/zoneamento (legítimo, baixável):**
   - **Filipeia** — geoportal oficial da PMJP. Download em shapefile/CSV/DWG/PDF.
     - Portal: https://filipeia.joaopessoa.pb.gov.br/
     - Downloads: https://filipeia.joaopessoa.pb.gov.br/files/donwload/
     - SigWEB (viewer): https://filipeia.joaopessoa.pb.gov.br/sigweb/
     - Ficha cadastral/IPTU: https://receita.joaopessoa.pb.gov.br/dsf_jpa_portal/
     - Camadas-chave: **lotes** (geometria, área real), quadras, bairros, logradouros, **zoneamento**.
   - **LUOS — Lei Complementar nº 166/2024** (zoneamento, uso e ocupação do solo).
     - Portal: https://planodiretor.joaopessoa.pb.gov.br/
     - Parâmetros por zona: CA (coef. aproveitamento), TO (taxa ocupação), gabarito, recuos.
     - Anexo II = Mapa de Zoneamento.
2. **Anúncios (efêmero, gatilho de demanda):** ChavesNaMão, VivaReal, ImovelWeb, OLX.

## Cálculo-produto (modelo real de João Pessoa)
A LUOS de JP **não** usa "área × coeficiente de aproveitamento". O que cabe no lote vem de:
- **projeção no térreo** = `TO_máx (Anexo V) × área do lote`
- **área permeável mín** = `TAP_mín × área do lote`
- **altura / nº de pavimentos = ESPACIAL**: faixa de **500m da orla** (Anexo III) + **IPHAEP** (centro histórico) — não é número por zona.
- **usos** dependem da **hierarquia viária** (Anexo IV: local/coletora/arterial/expressa).



## Stack
- **Dados/ingest:** Python 3.12 — `geopandas` (ingest geo), `Playwright` (scraping leve), `Firecrawl` (sites blindados).
- **DB:** PostgreSQL + **PostGIS** (Docker) — join espacial é o coração. SRID interno 31985; a API reprojeta p/ 4326 (mapa).
- **API:** **FastAPI** (Python) — serve dados do lote + regra de viabilidade. JWT (`python-jose`), bcrypt (`passlib`).
- **Frontend:** **Vite + React + TypeScript + MapLibre GL JS** (`frontend/`). App logado, sem SEO → Next descartado.
- **Migrations:** **Alembic** para o schema `app` (stateful: users, landbank).

## Aplicação (app)
Spec completa: `docs/superpowers/specs/2026-06-15-terraiq-app-design.md`. Responde, por lote: **(1) o que cabe construir** (envelope LUOS), depois **(2) melhor uso** e **(3) valor residual** (fases 2-3).

### API (`src/api/`)
- `GET /api/health` — healthcheck.
- `GET /api/bairros` — lista de bairros.
- `GET /api/lots` — lotes como **GeoJSON FeatureCollection** para o mapa. Filtros: `bairro`, `only_vacant` (só TERRITORIAL/vagos), `area_min`/`area_max`, `sort`, `limit`. (`a_venda` existe, mas a camada de anúncios está **desligada** — ver abaixo.)
- `GET /api/lots/{id}` — **ficha do lote**: cadastro + viabilidade (TO/TAP, projeção térreo, permeável, recuos, usos) + restrição de altura (rótulo orla/IPHAEP/barreira) + anúncio casado (se houver) + **VGV potencial** (envelope × R$/m² mediano de apartamento do bairro).
- `GET /api/lots/{id}/pdf` — **ficha em PDF** (ReportLab) com o VGV em destaque, levável ao comitê.
- `GET /api/oportunidades` — **ranking** do recorte por **valor residual** (quanto vale pagar), feature paga. O IncorpoScore ainda é calculado e devolvido, mas **não ordena nem aparece na UI**: sem anúncio casado, 3 dos 4 eixos eram quase só o preço/m² do bairro relido.
- **Anúncios de terreno (`market.anuncios`) desligados por default** (`ANUNCIOS_ATIVOS=0`): sem scraper agendado o dado envelhece e um lote "à venda" já vendido queima credibilidade. Schema, scraper e casamento continuam; religar com `ANUNCIOS_ATIVOS=1` quando houver frescor garantido.
- **Auth** (`/api/auth`): `register` · `login` (JWT) · `me`. bcrypt + rate-limit por IP + erro genérico (não revela se e-mail existe). **Registro por convite:** `register` exige `invite_code` válido (env `REGISTER_INVITE_CODE`, 1+ códigos por vírgula); env vazio/ausente = registro **fechado**. Lógica pura testada em `tests/test_auth_invite.py`. **Sem uso pelo frontend desde 09/2026** (app aberto, ver abaixo); fica para quando os planos pagos forem ligados.
- **Landbank** (`/api/landbank`): CRUD do pipeline de lotes salvos, **escopado por usuário**. Estágios: `triagem → analise → opcao → due_diligence → adquirido/descartado`. Também sem uso pelo frontend hoje — o landbank vive no navegador.
- Viabilidade pura e testada em `src/api/viability.py` (a altura em JP é **espacial**, não vem da zona) — `tests/test_viability.py`.
- **VGV** (`estimar_vgv`, puro/testado): `projeção_térreo × eficiência × R$/m² mediano do bairro`. Headline sólido = **VGV/pavimento** (independe de altura); total usa premissa de pavimentos. R$/m² vem de `market.comps` (comps de venda raspados, bairro canonizado contra `geo.lotes`) via view `market.preco_m2_bairro` (mediana/Q1/Q3/N, outliers saneados).

### Frontend (`frontend/src/`)
- **Oportunidades** (home) — top-20 do recorte ordenado por valor residual, com VGV e % terreno/VGV; clique abre a ficha.
- **Explorar** — mapa de lotes (MapLibre) + barra de filtros + lista de resultados.
- **Ficha do lote** — painel com cadastro, viabilidade, **VGV**, **valor residual** e restrição de altura; botões **+ landbank** e **PDF**.
- **Landbank** — board (kanban) por estágio: mover, anotar e remover lotes salvos. Fica no `localStorage` do navegador de cada pessoa (`incorpodata_landbank`): privado, sem conta, mas não sincroniza entre aparelhos.
- **Sem login:** o app é aberto — quem tem o link acessa tudo (Explorar, Oportunidades, PDF, Landbank). A UI de login (`AuthModal`) saiu em 09/2026; o backend de auth continua disponível.

### Schema `app` (Alembic — `migrations/`)
- `app.users` (auth B2B) · `app.landbank_items` (lote salvo + estágio + notas, enum `app.estagio_lote`).
- _Pendente da spec:_ `app.saved_searches`, `app.error_reports` (feature "⚑ reportar erro").



## Produção
- **No ar:** https://incorpodata-550574336825.southamerica-east1.run.app — projeto GCP `incorpodata-app`, região `southamerica-east1`, banco Neon (free).
- **Redeploy:** `PROJECT=incorpodata-app DATABASE_URL='<neon-url>' JWT_SECRET='<segredo>' bash deploy/deploy_cloudrun.sh` (runbook em `deploy/DEPLOY.md`).
- **Acesso:** aberto, sem login — basta o link. O Landbank salva no navegador de cada pessoa.

## Como rodar
```bash
# 1) Banco PostGIS (schema aplicado automaticamente na 1ª subida)
cp .env.example .env                       # credenciais de dev já funcionam
docker compose up -d                       # 127.0.0.1:5432

# 2) Python + carga da base geo/zoneamento (precisa de data/raw + config/luos_parametros.csv)
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
python -m src.pipeline.load_all            # data/raw + LUOS -> geo.* (idempotente)

# 3) API
uvicorn src.api.main:app --reload          # http://localhost:8000/docs

# 4) Frontend (outro terminal)
cd frontend && npm install && npm run dev  # http://localhost:5173
```

**Atualizar o cadastro de lotes (Filipeia)** sem trocar ids (links e landbank seguem valendo):
baixe o `Lotes.zip` novo no portal (manual: o portal bloqueia robôs) e rode
```bash
python -m src.ingest.sync_lotes --zip data/raw/Lotes.zip            # simula: diff + relatório em data/sync/
python -m src.ingest.sync_lotes --zip data/raw/Lotes.zip --aplicar  # grava numa transação; zona/altura só dos lotes tocados
```
Travas barram base que encolhe (±5%), perde >2% dos lotes ou tem fração de vagos implausível
(`--forcar` ignora). `--wfs` lê o GeoServer público, mas em 09/2026 ele era um recorte **mais
velho** que o portal (faltavam ~9 mil lotes reais) e a trava bloqueia. Histórico em `geo.cadastro_sync`.

Depois de atualizar o cadastro, recalcule os **alertas dos vagos** (construção, água ou rio no
lote, medidos contra EDIFICACOES / MassasDagua / Rios do Filipeia). Lote com alerta sai âmbar
no mapa, com o motivo na ficha, e não entra no ranking de Oportunidades:
```bash
python -m src.ingest.alertas_lotes --simular   # distribuição, sem gravar
python -m src.ingest.alertas_lotes             # refaz geo.lote_alerta (~1 min)
```
A API faz join em `geo.lote_alerta`: a tabela precisa existir antes do deploy do código.

**Demo — camada "à venda":** popula uma amostra de anúncios de *exemplo* (não são comps
reais) casados a lotes de Bancários, para o app mostrar preço + "cabe Y" no térreo:
```bash
docker exec -i terraiq-postgis psql -U terraiq < sql/seed_demo_anuncios.sql
# remover:  docker exec terraiq-postgis psql -U terraiq -c "DELETE FROM market.anuncios WHERE fonte='exemplo';"
```

**Comps reais (R$/m² por bairro → VGV):** ingere `imoveis_jp.json` (raspado) em `market.comps`:
```bash
python -m src.scrapers.load_comps --dry-run   # confere R$/m² por bairro (não grava)
python -m src.scrapers.load_comps             # grava ~28,4k comps; popula a view preco_m2_bairro
```
Na ingestão o bairro é **canonizado contra `geo.lotes`** (whitelist autoritativa, translitera acento):
`neighborhood` que é rua/avenida/fora de JP é descartado (~1,2k de 29,6k) e a grafia bate com a do
lote no join do VGV. Feito isso, a ficha (`GET /api/lots/{id}`) de um lote com zona traz o bloco `vgv`.

**Geocodificação dos comps (mediana por RAIO do lote):** portais entregam ~7,4k comps com *pino
aproximado* (`approx_location` — dezenas de anúncios no mesmo ponto), que ficam **fora** da mediana
espacial (`geo_fonte='fonte_aprox'`); seguem valendo na mediana de bairro. O backfill promove ao
nível de rua (Nominatim/OSM, 1 req/s, cache em `market.geocode_cache` — não repete consulta):
```bash
python -m src.scrapers.geocode_comps --dry-run    # relata pendências (sem rede)
python -m src.scrapers.geocode_comps --limit 300  # geocodifica; re-rodar continua de onde parou
```

