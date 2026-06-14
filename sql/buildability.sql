-- Viabilidade por lote — modelo REAL de João Pessoa (LUOS LC 166/2024).
-- Em JP NÃO se usa "área × coeficiente de aproveitamento". O envelope vem de:
--   projeção máx no térreo = TO_máx (Anexo V) × área do lote
--   área permeável mín     = TAP_mín (Anexo V) × área do lote
-- A área construível TOTAL e o nº de pavimentos dependem da ALTURA, que é ESPACIAL
-- (faixa de 500m da orla, Anexo III, + IPHAEP no centro histórico) — calculada quando a
-- camada de restrição de altura for carregada. Aqui derivamos projeção e permeável.
-- Pré-requisito: geo.lotes, geo.zonas e zoning.parametros carregados.

TRUNCATE geo.lote_zona;

INSERT INTO geo.lote_zona (lote_id, sigla, area_lote_m2, area_projecao_max_m2, area_permeavel_min_m2)
SELECT
  z.lote_id,
  z.sigla,
  z.area_lote_m2,
  z.area_lote_m2 * (p.to_max_pct  / 100.0) AS area_projecao_max_m2,
  z.area_lote_m2 * (p.tap_min_pct / 100.0) AS area_permeavel_min_m2
FROM (
  SELECT DISTINCT ON (l.id)
         l.id           AS lote_id,
         l.area_geom_m2 AS area_lote_m2,
         zo.sigla       AS sigla
  FROM geo.lotes l
  JOIN geo.zonas zo ON ST_Intersects(l.geom, zo.geom)
  ORDER BY l.id, ST_Area(ST_Intersection(l.geom, zo.geom)) DESC
) z
-- normaliza siglas: GeoServer usa 'ZH1', a LUOS/CSV usa 'ZH-1'
LEFT JOIN zoning.parametros p
  ON regexp_replace(upper(p.sigla), '[^A-Z0-9]', '', 'g')
   = regexp_replace(upper(z.sigla), '[^A-Z0-9]', '', 'g');
