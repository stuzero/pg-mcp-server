-- server/resources/sql/get_schema_view.sql
-- Comprehensive query to get all details for a specific materialized view
-- Returns a JSON structure with columns, indexes, statistics, and view definition

WITH 
-- Get materialized view information
view_info AS (
    SELECT 
        v.relname AS view_name,
        obj_description(v.oid) AS description,
        pg_stat_get_tuples_inserted(v.oid) AS row_count,
        pg_total_relation_size(v.oid) AS total_size_bytes,
        pg_table_size(v.oid) AS data_size_bytes,
        pg_indexes_size(v.oid) AS indexes_size_bytes,
        v.relkind AS kind,
        -- Get the view definition SQL
        pg_get_viewdef(v.oid) AS view_definition
    FROM 
        pg_class v
    JOIN 
        pg_namespace n ON v.relnamespace = n.oid
    WHERE 
        n.nspname = $1
        AND v.relname = $2
        AND v.relkind = 'm'  -- 'm' = materialized view
),

-- Get all columns for this materialized view
columns AS (
    SELECT 
        a.attname AS column_name,
        pg_catalog.format_type(a.atttypid, a.atttypmod) AS data_type,
        NOT a.attnotnull AS is_nullable,
        (SELECT pg_catalog.pg_get_expr(adbin, adrelid) FROM pg_catalog.pg_attrdef d
         WHERE d.adrelid = a.attrelid AND d.adnum = a.attnum AND a.atthasdef) AS column_default,
        col_description(a.attrelid, a.attnum) AS description,
        a.attnum AS ordinal_position,
        a.attstorage AS storage_type,
        CASE 
            WHEN a.attstorage = 'p' THEN 'plain'
            WHEN a.attstorage = 'e' THEN 'external'
            WHEN a.attstorage = 'm' THEN 'main'
            WHEN a.attstorage = 'x' THEN 'extended'
            ELSE a.attstorage::text
        END AS storage_type_desc
    FROM 
        pg_catalog.pg_attribute a
    JOIN 
        pg_catalog.pg_class c ON c.oid = a.attrelid
    JOIN 
        pg_catalog.pg_namespace n ON n.oid = c.relnamespace
    WHERE 
        n.nspname = $1
        AND c.relname = $2
        AND a.attnum > 0  -- Skip system columns
        AND NOT a.attisdropped  -- Skip dropped columns
    ORDER BY 
        a.attnum
),

-- Get all indexes 
indexes AS (
    SELECT 
        i.relname AS index_name,
        pg_get_indexdef(i.oid) AS index_definition,
        obj_description(i.oid) AS description,
        am.amname AS index_type,
        ix.indisunique AS is_unique,
        ix.indisprimary AS is_primary,
        ix.indisvalid AS is_valid,
        array_agg(a.attname ORDER BY array_position(ix.indkey::int[], a.attnum)) AS column_names,
        array_agg(pg_get_indexdef(i.oid, k.i::int, false) ORDER BY k.i) AS column_expressions
    FROM 
        pg_index ix
    JOIN 
        pg_class i ON i.oid = ix.indexrelid
    JOIN 
        pg_class t ON t.oid = ix.indrelid
    JOIN 
        pg_namespace n ON n.oid = t.relnamespace
    JOIN 
        pg_am am ON i.relam = am.oid
    LEFT JOIN 
        LATERAL unnest(ix.indkey::int[]) WITH ORDINALITY AS k(attnum, i) ON TRUE
    LEFT JOIN 
        pg_attribute a ON a.attrelid = t.oid AND a.attnum = k.attnum
    WHERE 
        n.nspname = $1
        AND t.relname = $2
    GROUP BY 
        i.relname, i.oid, am.amname, ix.indisunique, ix.indisprimary, ix.indisvalid
    ORDER BY 
        i.relname
),

-- Get view statistics
view_stats AS (
    SELECT 
        seq_scan,
        idx_scan,
        n_live_tup
    FROM 
        pg_stat_user_tables
    WHERE 
        schemaname = $1
        AND relname = $2
),

-- Get view refresh information
refresh_info AS (
    SELECT 
        c.relname,
        COALESCE(last_refresh_time, '1970-01-01'::timestamp) AS last_refresh_time
    FROM 
        pg_class c
    LEFT JOIN 
        (SELECT relid, last_refresh_time FROM pg_catalog.pg_stats_ext_matviews) sv ON c.oid = sv.relid
    WHERE 
        c.relkind = 'm'
        AND c.relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = $1)
        AND c.relname = $2
)

-- Main query to build the JSON result
SELECT jsonb_build_object(
    'materialized_view',
    jsonb_build_object(
        'name', (SELECT view_name FROM view_info),
        'description', (SELECT description FROM view_info),
        'row_count', (SELECT row_count FROM view_info),
        'definition', (SELECT view_definition FROM view_info),
        'size', jsonb_build_object(
            'total_bytes', (SELECT total_size_bytes FROM view_info),
            'data_bytes', (SELECT data_size_bytes FROM view_info),
            'indexes_bytes', (SELECT indexes_size_bytes FROM view_info)
        ),
        'last_refresh', (SELECT last_refresh_time FROM refresh_info),
        'columns', (
            SELECT COALESCE(
                jsonb_agg(
                    jsonb_build_object(
                        'name', c.column_name,
                        'type', c.data_type,
                        'nullable', c.is_nullable,
                        'default', c.column_default,
                        'description', c.description,
                        'position', c.ordinal_position,
                        'storage', c.storage_type_desc
                    )
                    ORDER BY c.ordinal_position
                ),
                '[]'::jsonb
            )
            FROM columns c
        ),
        'indexes', (
            SELECT COALESCE(
                jsonb_agg(
                    jsonb_build_object(
                        'name', i.index_name,
                        'type', i.index_type,
                        'definition', i.index_definition,
                        'is_unique', i.is_unique,
                        'is_primary', i.is_primary,
                        'is_valid', i.is_valid,
                        'column_names', i.column_names,
                        'column_expressions', i.column_expressions,
                        'description', i.description
                    )
                ),
                '[]'::jsonb
            )
            FROM indexes i
        ),
        'statistics', (
            SELECT COALESCE(
                jsonb_build_object(
                    'seq_scan', s.seq_scan,
                    'idx_scan', s.idx_scan,
                    'live_tuples', s.n_live_tup
                ),
                '{}'::jsonb
            )
            FROM view_stats s
        )
    )
) AS view_details;