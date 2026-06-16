-- Restrições de altura (espacial) e flag por lote.
-- Pré-requisito: staging.faixas, staging.centrohist, staging.barreira + geo.lotes + tabelas criadas.

TRUNCATE geo.restricao_altura RESTART IDENTITY;
INSERT INTO geo.restricao_altura (tipo, rotulo, geom)
  SELECT 'faixa_orla', faixas, ST_Multi(ST_Force2D(geom)) FROM staging.faixas;
INSERT INTO geo.restricao_altura (tipo, rotulo, geom)
  SELECT 'centro_historico', 'centro_historico', ST_Multi(ST_Force2D(geom)) FROM staging.centrohist;
INSERT INTO geo.restricao_altura (tipo, rotulo, geom)
  SELECT 'barreira_cabo_branco', 'barreira', ST_Multi(ST_Force2D(geom)) FROM staging.barreira;

-- Flag por lote: faixa da orla (se houver), patrimônio, barreira.
TRUNCATE geo.lote_restricao;
INSERT INTO geo.lote_restricao (lote_id, faixa_orla, em_centro_historico, em_barreira)
SELECT l.id,
       max(rf.rotulo) FILTER (WHERE rf.tipo = 'faixa_orla'),
       COALESCE(bool_or(rf.tipo = 'centro_historico'), false),
       COALESCE(bool_or(rf.tipo = 'barreira_cabo_branco'), false)
FROM geo.lotes l
LEFT JOIN geo.restricao_altura rf
       ON ST_Contains(rf.geom, ST_PointOnSurface(l.geom))
GROUP BY l.id;

UPDATE geo.lote_restricao
SET altura_livre = (faixa_orla IS NULL AND NOT em_centro_historico AND NOT em_barreira);
