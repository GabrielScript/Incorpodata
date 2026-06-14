-- Transforma o staging bruto do Filipeia em geo.lotes (tipado, 2D MultiPolygon).
-- Pré-requisito: staging.lotes e staging.bairros carregados (src.ingest.filipeia).

CREATE INDEX IF NOT EXISTS idx_stg_bairros_geom ON staging.bairros USING GIST (geom);

TRUNCATE geo.lotes CASCADE;

INSERT INTO geo.lotes (inscricao, setor, quadra, lote, logradouro, tipo, geom)
SELECT codi_cart, codi_seto, codi_quad, codi_lote, desc_logr, tipo_imove,
       ST_Multi(ST_Force2D(geom))
FROM staging.lotes;

-- Atribui bairro pelo ponto interno do lote dentro do polígono do bairro.
UPDATE geo.lotes l
SET bairro = b.n_bairro
FROM staging.bairros b
WHERE ST_Contains(b.geom, ST_PointOnSurface(l.geom));
