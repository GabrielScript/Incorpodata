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
- Python 3.12 — `geopandas` (ingest geo), `Playwright` (scraping leve), `Firecrawl` (sites blindados).
- PostgreSQL + **PostGIS** (Docker) — join espacial é o coração.

## Ordem de construção
1. [ ] Espinha geo: baixar Filipeia (lotes, quadras, zoneamento, bairros) → PostGIS.
2. [ ] Camada LUOS: tabelar parâmetros da LC 166/2024 por zona → área construível por lote.
3. [ ] Scrapers: ChavesNaMão → normalizar → geocodificar → casar no lote.
4. [ ] Primeira entrega para 1 construtora.

## Como rodar
```bash
cp .env.example .env          # ajustar credenciais se quiser
docker compose up -d          # sobe PostGIS em localhost:5432
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
psql "$DATABASE_URL" -f sql/schema.sql   # ou rodar via src/db
```
