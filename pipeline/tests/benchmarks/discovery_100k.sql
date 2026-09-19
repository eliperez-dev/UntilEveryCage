-- Synthetic-only query-shape benchmark. This intentionally does not touch uec.
DROP TABLE IF EXISTS bench_discovery_100k;
CREATE TABLE bench_discovery_100k AS
SELECT
  n AS ordinal,
  format('00000000-0000-4000-8000-%s', lpad(n::text, 12, '0'))::uuid AS facility_id,
  format('Synthetic facility %s', n) AS canonical_name,
  CASE WHEN n % 2 = 0 THEN 'DK' ELSE 'SE' END::text AS country_code,
  format('Synthetic region %s', n % 100) AS region,
  CASE n % 4 WHEN 0 THEN 'slaughter' WHEN 1 THEN 'fish_processing'
    WHEN 2 THEN 'logistics_and_storage' ELSE 'retail_and_prepared_food' END AS category,
  CASE n % 3 WHEN 0 THEN 'official' WHEN 1 THEN 'secondary' ELSE 'user_submitted' END AS source_type,
  CASE n % 3 WHEN 0 THEN 'exact' WHEN 1 THEN 'city' ELSE 'unmapped' END AS display_precision,
  ST_SetSRID(ST_Point(-10 + (n % 2000) / 100.0, 45 + (n % 1000) / 100.0), 4326)::geography AS location
FROM generate_series(1, 100000) AS n;
CREATE INDEX bench_discovery_cursor ON bench_discovery_100k (country_code, facility_id);
CREATE INDEX bench_discovery_name ON bench_discovery_100k USING GIN (lower(canonical_name) gin_trgm_ops);
CREATE INDEX bench_discovery_location ON bench_discovery_100k USING GIST (location);
ANALYZE bench_discovery_100k;

EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
SELECT * FROM bench_discovery_100k WHERE country_code = 'DK' ORDER BY facility_id LIMIT 50;
EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
SELECT * FROM bench_discovery_100k WHERE country_code = 'DK' AND facility_id > '00000000-0000-4000-8000-000000050000'::uuid ORDER BY facility_id LIMIT 50;
EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
SELECT * FROM bench_discovery_100k WHERE lower(canonical_name) LIKE '%facility 999%' ORDER BY facility_id LIMIT 50;
EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
SELECT * FROM bench_discovery_100k WHERE location && ST_MakeEnvelope(8, 54, 13, 58, 4326)::geography ORDER BY facility_id LIMIT 50;
EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
SELECT * FROM bench_discovery_100k WHERE ST_DWithin(location, ST_SetSRID(ST_Point(10, 56), 4326)::geography, 50000) ORDER BY facility_id LIMIT 50;
EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
SELECT * FROM bench_discovery_100k WHERE facility_id = '00000000-0000-4000-8000-000000050000'::uuid;
