# TerraIQ — Inteligência de terrenos de João Pessoa

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
- `GET /api/lots/{id}` — **ficha do lote**: cadastro + viabilidade (TO/TAP, projeção térreo, permeável, recuos, usos) + restrição de altura (rótulo orla/IPHAEP/barreira) + anúncio casado (se houver).
- **Auth** (`/api/auth`): `register` · `login` (JWT) · `me`. bcrypt + rate-limit por IP + erro genérico (não revela se e-mail existe). _Registro ainda aberto — fechar (convite/admin) antes de produção._
- **Landbank** (`/api/landbank`): CRUD do pipeline de lotes salvos, **escopado por usuário**. Estágios: `triagem → analise → opcao → due_diligence → adquirido/descartado`.
- Viabilidade pura e testada em `src/api/viability.py` (a altura em JP é **espacial**, não vem da zona) — `tests/test_viability.py`.

### Frontend (`frontend/src/`)
- **Explorar** — mapa de lotes (MapLibre) + barra de filtros + lista de resultados.
- **Ficha do lote** — painel com cadastro, viabilidade, restrição de altura e anúncio.
- _Pendente:_ tela **Landbank** e **UI de login** (backend pronto, frontend ainda não consome).

### Schema `app` (Alembic — `migrations/`)
- `app.users` (auth B2B) · `app.landbank_items` (lote salvo + estágio + notas, enum `app.estagio_lote`).
- _Pendente da spec:_ `app.saved_searches`, `app.error_reports` (feature "⚑ reportar erro").

## Ordem de construção
1. [x] Espinha geo: Filipeia (lotes, quadras, zoneamento, bairros) → PostGIS.
2. [x] Camada LUOS: parâmetros da LC 166/2024 por zona → área construível por lote.
3. [x] API read-only (lotes/ficha) + frontend (mapa Bancários + ficha + filtros).
4. [x] Schema `app` + auth (JWT) + landbank (backend).
5. [ ] Frontend: tela Landbank + login; "⚑ reportar erro"; saved searches.
6. [ ] Scrapers: ChavesNaMão → normalizar → geocodificar → casar no lote.
7. [ ] PDF da ficha; Jobs 2-3 (melhor uso, valor residual). Primeira entrega p/ 1 construtora.

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
