# IncorpoData — Inteligência de terrenos de João Pessoa

Base de dados viva da **oferta de solo** de João Pessoa/PB, cruzando cadastro, zoneamento e
anúncios de venda. Cliente-âncora: **construtoras/incorporadoras**.

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

Casar `anúncio → lote` por geolocalização = "este lote está à venda por R$X, TO 50%, e a altura permitida aqui é N pavimentos".

## Postura legal (vira arquitetura, não opinião)
- **ToS:** sites de anúncio proíbem scraping e têm anti-bot (DataDome/Cloudflare). Uso scraping
  respeitoso + rate-limit; sites blindados via Firecrawl (serviço gerenciado). **Sem burla de anti-bot.**
- **LGPD:** WhatsApp do vendedor = dado pessoal. **Não** estocar lista de telefones para revenda.
  Guardar link do anúncio; **revelar contato sob demanda** (deeplink) ao usuário pagante. Minimização.

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
- `GET /api/lots` — lotes como **GeoJSON FeatureCollection** para o mapa. Filtros: `bairro`, `only_vacant` (só TERRITORIAL/vagos), `a_venda` (com anúncio casado), `area_min`/`area_max`, `sort`, `limit`.
- `GET /api/lots/{id}` — **ficha do lote**: cadastro + viabilidade (TO/TAP, projeção térreo, permeável, recuos, usos) + restrição de altura (rótulo orla/IPHAEP/barreira) + anúncio casado (se houver) + **VGV potencial** (envelope × R$/m² mediano de apartamento do bairro).
- `GET /api/lots/{id}/pdf` — **ficha em PDF** (ReportLab) com o VGV em destaque, levável ao comitê.
- **Auth** (`/api/auth`): `register` · `login` (JWT) · `me`. bcrypt + rate-limit por IP + erro genérico (não revela se e-mail existe). **Registro por convite:** `register` exige `invite_code` válido (env `REGISTER_INVITE_CODE`, 1+ códigos por vírgula); env vazio/ausente = registro **fechado**. Lógica pura testada em `tests/test_auth_invite.py`.
- **Landbank** (`/api/landbank`): CRUD do pipeline de lotes salvos, **escopado por usuário**. Estágios: `triagem → analise → opcao → due_diligence → adquirido/descartado`.
- Viabilidade pura e testada em `src/api/viability.py` (a altura em JP é **espacial**, não vem da zona) — `tests/test_viability.py`.
- **VGV** (`estimar_vgv`, puro/testado): `projeção_térreo × eficiência × R$/m² mediano do bairro`. Headline sólido = **VGV/pavimento** (independe de altura); total usa premissa de pavimentos. R$/m² vem de `market.comps` (comps de venda raspados, bairro canonizado contra `geo.lotes`) via view `market.preco_m2_bairro` (mediana/Q1/Q3/N, outliers saneados).

### Frontend (`frontend/src/`)
- **Explorar** — mapa de lotes (MapLibre) + barra de filtros + lista de resultados.
- **Ficha do lote** — painel com cadastro, viabilidade, **VGV**, restrição de altura e anúncio; botões **+ landbank** e **PDF**.
- **Landbank** — board (kanban) por estágio: mover, anotar e remover lotes salvos (consome `/api/landbank`, JWT).
- **Login/registro** — modal (`AuthModal`) no topo (**Entrar**): login/criar conta via `/api/auth` (JWT em `localStorage`). Explorar é público; o **Landbank** exige login. Token de dev (`python -m src.api.dev_token`) segue válido para debug.

### Schema `app` (Alembic — `migrations/`)
- `app.users` (auth B2B) · `app.landbank_items` (lote salvo + estágio + notas, enum `app.estagio_lote`).
- _Pendente da spec:_ `app.saved_searches`, `app.error_reports` (feature "⚑ reportar erro").

## Ordem de construção
1. [x] Espinha geo: Filipeia (lotes, quadras, zoneamento, bairros) → PostGIS.
2. [x] Camada LUOS: parâmetros da LC 166/2024 por zona → área construível por lote.
3. [x] API read-only (lotes/ficha) + frontend (mapa Bancários + ficha + filtros).
4. [x] Schema `app` + auth (JWT) + landbank (backend).
5. [~] Frontend: **tela Landbank ✓**, **login/registro ✓**; falta "⚑ reportar erro" e saved searches.
6. [ ] Scrapers: ChavesNaMão → normalizar → geocodificar → casar no lote.
7. [x] Comps de venda (`market.comps` + view `preco_m2_bairro`) → **VGV potencial na ficha**.
8. [x] **PDF da ficha** (com VGV). Jobs 2-3 (melhor uso, valor residual) ainda pendentes.
9. [x] **Deploy: Cloud Run (API + frontend, container único) + Neon (Postgres/PostGIS free).**

## Produção
- **No ar:** https://incorpodata-550574336825.southamerica-east1.run.app — projeto GCP `incorpodata-app`, região `southamerica-east1`, banco Neon (free).
- **Redeploy:** `PROJECT=incorpodata-app DATABASE_URL='<neon-url>' JWT_SECRET='<segredo>' bash deploy/deploy_cloudrun.sh` (runbook em `deploy/DEPLOY.md`).
- **Landbank no site:** clique em **Entrar** (topo) → criar conta / login. O token JWT fica no
  navegador e o Landbank passa a salvar por usuário. **Criar conta exige código de convite** —
  defina `REGISTER_INVITE_CODE` no deploy e entregue o código a cada cliente (sem ele, cadastro
  fica fechado).

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
Precedência de coordenada: `fonte` (exata do portal) > `nominatim` (rua) > `fonte_aprox` (pino).
