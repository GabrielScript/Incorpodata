-- ============================================================================
-- SEED DE DEMONSTRAÇÃO — anúncios de EXEMPLO casados a lotes reais de Bancários.
--
-- Por quê: o motor de viabilidade é real, mas market.anuncios está vazio. Para o
-- demo mostrar o loop completo ("este lote está à venda E cabe Y no térreo"),
-- criamos uma amostra. Estes NÃO são comps reais — os preços são ILUSTRATIVOS
-- (fonte = 'exemplo', vendedor fictício). Substituir por dados reais via scrapers.
--
-- Idempotente: pode rodar quantas vezes quiser (limpa a execução anterior).
-- Rodar:    docker exec -i terraiq-postgis psql -U terraiq < sql/seed_demo_anuncios.sql
-- Remover:  docker exec terraiq-postgis psql -U terraiq -c "DELETE FROM market.anuncios WHERE fonte='exemplo';"
--           (a cascata remove os vínculos em market.anuncio_lote)
-- ============================================================================
BEGIN;

-- limpa execução anterior do seed (FK ON DELETE CASCADE remove os vínculos)
DELETE FROM market.anuncios WHERE fonte = 'exemplo';

WITH alvo AS (
  SELECT l.id AS lote_id,
         round(l.area_geom_m2)::numeric         AS area,
         (500 + (l.id % 13) * 50)::numeric       AS pm2   -- R$/m² ilustrativo: 500–1100
  FROM geo.lotes l
  JOIN geo.lote_zona lz
    ON lz.lote_id = l.id AND lz.area_projecao_max_m2 IS NOT NULL
  WHERE l.bairro ILIKE 'Bancários'
    AND l.tipo = 'TERRITORIAL'
    AND l.area_geom_m2 BETWEEN 250 AND 1500       -- evita outliers (ZEPA/parques)
  ORDER BY l.area_geom_m2 DESC
  LIMIT 15
),
novos AS (
  INSERT INTO market.anuncios
    (fonte, fonte_id, url, titulo, preco, area_anunc_m2, bairro_texto, vendedor_tipo, ativo)
  SELECT 'exemplo',
         'demo-' || lote_id,
         'https://exemplo.demo/anuncio/' || lote_id,
         'Terreno ' || area || ' m² em Bancários (exemplo)',
         round(area * pm2, -3),                   -- preço arredondado p/ milhar
         area,
         'Bancários',
         CASE WHEN lote_id % 2 = 0 THEN 'proprietario' ELSE 'imobiliaria' END,
         true
  FROM alvo
  RETURNING id, fonte_id
)
INSERT INTO market.anuncio_lote (anuncio_id, lote_id, metodo, score)
SELECT n.id, split_part(n.fonte_id, '-', 2)::bigint, 'manual', 1.0
FROM novos n;

COMMIT;

-- conferência
SELECT count(*) AS anuncios_exemplo FROM market.anuncios WHERE fonte = 'exemplo';
