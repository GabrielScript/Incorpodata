-- IncorpoData — modelo de dados (PostGIS)
-- SRID interno: 31985 (SIRGAS 2000 / UTM 25S) → ST_Area sai em m² direto p/ João Pessoa.

CREATE EXTENSION IF NOT EXISTS postgis;

CREATE SCHEMA IF NOT EXISTS staging;  -- carga bruta dos shapefiles (passthrough)
CREATE SCHEMA IF NOT EXISTS geo;      -- camadas tipadas (moat)
CREATE SCHEMA IF NOT EXISTS zoning;   -- parâmetros LUOS
CREATE SCHEMA IF NOT EXISTS market;   -- anúncios (camada efêmera)

-- ───────────────────────── Zonas (Filipeia zoneamento + LUOS) ─────────────────────────
CREATE TABLE IF NOT EXISTS geo.zonas (
  id     bigserial PRIMARY KEY,
  sigla  text,                 -- ex.: ZR1, ZAP, ZA...
  nome   text,
  fonte  text DEFAULT 'filipeia',
  geom   geometry(MultiPolygon, 31985)
);
CREATE INDEX IF NOT EXISTS idx_zonas_geom  ON geo.zonas USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_zonas_sigla ON geo.zonas (sigla);

-- ───────────────────────── Lotes (cadastro Filipeia) ─────────────────────────
-- A geometria do cadastro dá área e dimensões REAIS (o anúncio costuma mentir).
-- TIPO: TERRITORIAL = lote vago/sem construção (ALVO do negócio) | PREDIAL = construído.
CREATE TABLE IF NOT EXISTS geo.lotes (
  id           bigserial PRIMARY KEY,
  inscricao    text,           -- CODI_CART (código cartográfico)
  setor        text,           -- CODI_SETO
  quadra       text,           -- CODI_QUAD
  lote         text,           -- CODI_LOTE
  logradouro   text,           -- DESC_LOGR
  tipo         text,           -- TIPO_IMOVE: TERRITORIAL | PREDIAL
  bairro       text,           -- via interseção com camada de bairros
  area_cad_m2  numeric,        -- área cadastral (se houver atributo)
  geom         geometry(MultiPolygon, 31985),
  area_geom_m2 numeric GENERATED ALWAYS AS (ST_Area(geom)) STORED
);
CREATE INDEX IF NOT EXISTS idx_lotes_geom      ON geo.lotes USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_lotes_inscricao ON geo.lotes (inscricao);
CREATE INDEX IF NOT EXISTS idx_lotes_tipo      ON geo.lotes (tipo);
CREATE INDEX IF NOT EXISTS idx_lotes_bairro    ON geo.lotes (bairro);

-- ───────────────────────── Parâmetros urbanísticos (LUOS LC 166/2024) ─────────────────────────
-- Preencher de config/luos_parametros.csv (extraído dos anexos da LC 166/2024).
-- Modelo de JP: controle por TO/TAP/recuos (não por coef. de aproveitamento).
-- Altura é ESPACIAL (faixa 500m orla + IPHAEP) → não vive aqui. IA só onde aplicável (SEAV).
CREATE TABLE IF NOT EXISTS zoning.parametros (
  sigla           text PRIMARY KEY,
  nome            text,
  to_max_pct      numeric,     -- taxa de ocupação máxima (%)         [Anexo V]
  tap_min_pct     numeric,     -- taxa de área permeável mínima (%)   [Anexo V]
  recuo_frontal_m numeric,     -- recuo frontal mínimo (m)
  recuo_lateral   text,        -- fórmula por pavimento (ex.: DE=3,00+[(N-4)x0,30])
  recuo_fundo     text,        -- fórmula por pavimento
  ia_max          numeric,     -- índice de aproveitamento máx (só onde aplicável, ex.: SEAV)
  gabarito_obs    text,        -- nota de altura (espacial: orla 500m + IPHAEP)
  usos_obs        text,        -- usos dependem da hierarquia viária (Anexo IV)
  notas           text,        -- footnotes (F)(G)(H)... — valores a CONFERIR na lei
  fonte           text DEFAULT 'LC 166/2024 Anexo V'
);

-- ───────────────────────── Viabilidade por lote (join espacial + cálculo) ─────────────────────────
CREATE TABLE IF NOT EXISTS geo.lote_zona (
  lote_id               bigint PRIMARY KEY REFERENCES geo.lotes(id) ON DELETE CASCADE,
  sigla                 text,
  area_lote_m2          numeric,
  area_projecao_max_m2  numeric,  -- TO_máx × área (footprint máx no térreo)
  area_permeavel_min_m2 numeric,  -- TAP_mín × área
  -- área construível TOTAL e nº de pavimentos dependem da altura ESPACIAL (orla 500m + IPHAEP)
  atualizado_em         timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_lote_zona_sigla ON geo.lote_zona (sigla);

-- ───────────────────────── Restrições de altura (espacial: orla + patrimônio) ─────────────────────────
-- Em JP a altura/nº de pavimentos é controlada por restrições ESPACIAIS, não pela zona.
CREATE TABLE IF NOT EXISTS geo.restricao_altura (
  id     bigserial PRIMARY KEY,
  tipo   text,   -- faixa_orla | centro_historico | barreira_cabo_branco
  rotulo text,   -- ex.: faixa '1ª'..'9ª'
  geom   geometry(MultiPolygon, 31985)
);
CREATE INDEX IF NOT EXISTS idx_restricao_geom ON geo.restricao_altura USING GIST (geom);

CREATE TABLE IF NOT EXISTS geo.lote_restricao (
  lote_id             bigint PRIMARY KEY REFERENCES geo.lotes(id) ON DELETE CASCADE,
  faixa_orla          text,                 -- faixa de escalonamento da orla (1ª..9ª) ou NULL
  em_centro_historico boolean DEFAULT false,
  em_barreira         boolean DEFAULT false,
  altura_livre        boolean               -- sem restrição espacial → vertical limitada só por recuos
);

-- ───────────────────────── Anúncios (efêmero, gatilho de demanda) ─────────────────────────
-- LGPD: NÃO estocar telefone do vendedor para revenda. Guardamos a URL (ponteiro) e
-- revelamos contato sob demanda ao usuário pagante.
CREATE TABLE IF NOT EXISTS market.anuncios (
  id             bigserial PRIMARY KEY,
  fonte          text NOT NULL,            -- chavesnamao | vivareal | imovelweb | olx
  fonte_id       text NOT NULL,            -- id do anúncio na origem
  url            text NOT NULL,            -- ponteiro p/ contato sob demanda
  titulo         text,
  preco          numeric,
  area_anunc_m2  numeric,
  preco_m2       numeric GENERATED ALWAYS AS
                   (CASE WHEN area_anunc_m2 > 0 THEN preco / area_anunc_m2 END) STORED,
  bairro_texto   text,
  vendedor_tipo  text,                     -- proprietario | imobiliaria
  lat            double precision,
  lon            double precision,
  geom           geometry(Point, 31985),
  primeiro_visto timestamptz DEFAULT now(),
  ultimo_visto   timestamptz DEFAULT now(),
  ativo          boolean DEFAULT true,
  UNIQUE (fonte, fonte_id)
);
CREATE INDEX IF NOT EXISTS idx_anuncios_geom  ON market.anuncios USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_anuncios_ativo ON market.anuncios (ativo);

-- Camada "À venda" alimentada pelo inventário do BestPlaces (terrenos + casas; load_bestplaces).
-- LGPD: anunciante = nome + CRECI (dado profissional público); telefone continua FORA.
ALTER TABLE market.anuncios ADD COLUMN IF NOT EXISTS tipo              text;     -- Lote/Terreno | Casa | ...
ALTER TABLE market.anuncios ADD COLUMN IF NOT EXISTS business          text DEFAULT 'SALE';
ALTER TABLE market.anuncios ADD COLUMN IF NOT EXISTS quartos           int;
ALTER TABLE market.anuncios ADD COLUMN IF NOT EXISTS banheiros         int;
ALTER TABLE market.anuncios ADD COLUMN IF NOT EXISTS suites            int;
ALTER TABLE market.anuncios ADD COLUMN IF NOT EXISTS vagas             int;
ALTER TABLE market.anuncios ADD COLUMN IF NOT EXISTS iptu              numeric;  -- R$/ano como anunciado
ALTER TABLE market.anuncios ADD COLUMN IF NOT EXISTS condominio        numeric;  -- R$/mês
ALTER TABLE market.anuncios ADD COLUMN IF NOT EXISTS area_terreno_m2   numeric;  -- casa: terreno lido do texto
ALTER TABLE market.anuncios ADD COLUMN IF NOT EXISTS anunciante_nome   text;
ALTER TABLE market.anuncios ADD COLUMN IF NOT EXISTS anunciante_creci  text;
ALTER TABLE market.anuncios ADD COLUMN IF NOT EXISTS loc_aproximada    boolean;
ALTER TABLE market.anuncios ADD COLUMN IF NOT EXISTS imagem_url        text;
ALTER TABLE market.anuncios ADD COLUMN IF NOT EXISTS fontes            text[];   -- portais onde o imóvel aparece
ALTER TABLE market.anuncios ADD COLUMN IF NOT EXISTS scraped_at        timestamptz;
-- Oportunidade (preço pedido × esperado): LightGBM do BestPlaces (casa) ou hedônico (terreno).
ALTER TABLE market.anuncios ADD COLUMN IF NOT EXISTS preco_esperado    numeric;
ALTER TABLE market.anuncios ADD COLUMN IF NOT EXISTS preco_esperado_lo numeric;  -- faixa típica (q25)
ALTER TABLE market.anuncios ADD COLUMN IF NOT EXISTS preco_esperado_hi numeric;  -- faixa típica (q75)
ALTER TABLE market.anuncios ADD COLUMN IF NOT EXISTS desconto_pct      numeric;  -- (esperado − pedido)/esperado
ALTER TABLE market.anuncios ADD COLUMN IF NOT EXISTS confiabilidade    numeric;  -- 0–1
ALTER TABLE market.anuncios ADD COLUMN IF NOT EXISTS suspeito          boolean;  -- |z| > 3: bom/ruim demais
ALTER TABLE market.anuncios ADD COLUMN IF NOT EXISTS oportunidade_tier text;     -- rara | boa | mercado | acima | suspeito
ALTER TABLE market.anuncios ADD COLUMN IF NOT EXISTS oportunidade_modelo text;   -- lightgbm | hedonico
ALTER TABLE market.anuncios ADD COLUMN IF NOT EXISTS logradouro_texto  text;     -- rua anunciada (confere o pino)

-- Séries de mercado (BCB SGS: juros do financiamento imobiliário; FipeZAP etc.). Mensal.
CREATE TABLE IF NOT EXISTS market.indicadores (
  serie        text NOT NULL,          -- ex.: financ_imob_pf_mercado_aa
  data         date NOT NULL,          -- 1º dia do mês de referência
  valor        numeric NOT NULL,
  fonte        text,                   -- ex.: 'BCB SGS 20772'
  carregado_em timestamptz DEFAULT now(),
  PRIMARY KEY (serie, data)
);

-- Bairro sem acento p/ comparar portal × cadastro ("Bancarios" = "Bancários"); usado no
-- casamento por área+raio (src/scrapers/match_anuncio_lote.py). Sem depender da extensão unaccent.
CREATE OR REPLACE FUNCTION market.unaccent_bairro(s text) RETURNS text
LANGUAGE sql IMMUTABLE AS $$
  SELECT upper(translate(coalesce(s, ''),
    'áàâãäéèêëíìîïóòôõöúùûüçÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇ',
    'aaaaaeeeeiiiiooooouuuucAAAAAEEEEIIIIOOOOOUUUUC'))
$$;

-- Chave p/ comparar a rua do anúncio ("Rua das Cortiças") com o logradouro do cadastro
-- ("CORTIÇAS, DAS"; "JOAO CIRILO DA SILVA, 1700 - RES. VILA REAL"; "X - PARK COWBOY"): corta
-- no 1º ", " e no " - " (número, condomínio, artigo invertido), tira tipo de via, preposição,
-- acento e pontuação. NULL se não sobra nada.
-- Usado p/ conferir o pino no casamento (src/scrapers/match_anuncio_lote.py).
CREATE OR REPLACE FUNCTION market.chave_rua(s text) RETURNS text
LANGUAGE sql IMMUTABLE AS $$
  SELECT nullif(regexp_replace(regexp_replace(regexp_replace(
    split_part(regexp_replace(market.unaccent_bairro(s), '\s+-\s.*$', ''), ',', 1),
      '^\s*(RUA|R|AVENIDA|AV|AVE|TRAVESSA|TV|TRAV|ALAMEDA|AL|ESTRADA|RODOVIA|ROD|PRACA|VIA|BECO)\.?\s+', ''),
    '\m(DA|DE|DO|DAS|DOS|E)\M', '', 'g'),
    '[^A-Z0-9]', '', 'g'), '')
$$;

-- ───────────────────────── Casamento anúncio → lote (enriquecimento) ─────────────────────────
CREATE TABLE IF NOT EXISTS market.anuncio_lote (
  anuncio_id bigint REFERENCES market.anuncios(id) ON DELETE CASCADE,
  lote_id    bigint REFERENCES geo.lotes(id)       ON DELETE CASCADE,
  metodo     text,        -- ponto_no_lote | endereco | manual
  score      numeric,
  PRIMARY KEY (anuncio_id, lote_id)
);
-- A PK começa por anuncio_id: sem este índice o "anúncio do lote" (LATERAL em /lots e nos
-- tiles) varria a tabela inteira por lote — tile z14 com todos os lotes: 0,8 s → ms.
CREATE INDEX IF NOT EXISTS idx_anuncio_lote_lote ON market.anuncio_lote (lote_id);

-- ───────────────────────── Comps de mercado (referência de preço, base do VGV) ─────────────────────────
-- Distinto de market.anuncios: comps são a NUVEM de preços de venda (apto/casa/lote) que
-- vira R$/m² por bairro. Não casamos comp→lote nem expomos contato (não é gatilho de demanda,
-- é benchmark estatístico). Tabela fiel ao raspado; o saneamento de outliers vive na view.
CREATE TABLE IF NOT EXISTS market.comps (
  id           bigserial PRIMARY KEY,
  source       text NOT NULL,           -- vivareal | ...
  source_id    text NOT NULL,           -- id do anúncio na origem
  tipo         text,                    -- Apartamento | Casa | Lote/Terreno | ...
  business     text DEFAULT 'SALE',
  preco        numeric,
  area_m2      numeric,
  preco_m2     numeric GENERATED ALWAYS AS
                 (CASE WHEN area_m2 > 0 THEN preco / area_m2 END) STORED,
  quartos      int,
  vagas        int,
  bairro       text,
  lat          double precision,
  lon          double precision,
  geom         geometry(Point, 31985),  -- p/ mediana espacial futura (raio do lote)
  scraped_at   timestamptz,
  carregado_em timestamptz DEFAULT now(),
  UNIQUE (source, source_id)
);
CREATE INDEX IF NOT EXISTS idx_comps_bairro ON market.comps (bairro);
CREATE INDEX IF NOT EXISTS idx_comps_tipo   ON market.comps (tipo);
CREATE INDEX IF NOT EXISTS idx_comps_geom   ON market.comps USING GIST (geom);

-- Geocodificação de comps sem coordenada (backfill Nominatim — src/scrapers/geocode_comps).
-- ALTER IF NOT EXISTS: schema.sql é idempotente e também atualiza bancos já existentes.
ALTER TABLE market.comps ADD COLUMN IF NOT EXISTS endereco  text;  -- street do anúncio (entrada do geocoder)
ALTER TABLE market.comps ADD COLUMN IF NOT EXISTS geo_fonte text;  -- 'fonte' (scraper) | 'nominatim'
-- Atributos que o inventário multi-portal traz (BestPlaces) e o hedônico pode usar.
ALTER TABLE market.comps ADD COLUMN IF NOT EXISTS banheiros  int;
ALTER TABLE market.comps ADD COLUMN IF NOT EXISTS suites     int;
ALTER TABLE market.comps ADD COLUMN IF NOT EXISTS iptu       numeric;
ALTER TABLE market.comps ADD COLUMN IF NOT EXISTS condominio numeric;

-- Cache de consultas ao Nominatim (1 req/s): nunca repetir consulta, nem as que falharam.
CREATE TABLE IF NOT EXISTS market.geocode_cache (
  chave        text PRIMARY KEY,     -- cache_key(endereco, bairro) — normalizada
  consulta     text NOT NULL,        -- query enviada (auditoria/debug)
  lat          double precision,
  lon          double precision,
  ok           boolean NOT NULL,     -- false = Nominatim não achou/fora de JP (não re-tentar)
  resolvido_em timestamptz DEFAULT now()
);

-- R$/m² por bairro e tipo: mediana + quartis + N. Outliers saneados (faixa plausível de
-- venda) para a mediana não ser puxada por erro de digitação/área. É o número que o VGV usa.
CREATE OR REPLACE VIEW market.preco_m2_bairro AS
SELECT
  bairro,
  tipo,
  count(*)                                               AS n,
  percentile_cont(0.5)  WITHIN GROUP (ORDER BY preco_m2) AS preco_m2_mediana,
  percentile_cont(0.25) WITHIN GROUP (ORDER BY preco_m2) AS preco_m2_q1,
  percentile_cont(0.75) WITHIN GROUP (ORDER BY preco_m2) AS preco_m2_q3
FROM market.comps
WHERE business = 'SALE'
  AND preco_m2 BETWEEN 800 AND 30000
GROUP BY bairro, tipo;
