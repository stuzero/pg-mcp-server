-- server/resources/sql/get_schema.sql
-- Get top-level information about a specific schema including basic schema metadata,
-- extensions installed in the schema, table information, and materialized views
-- Returns a simplified JSON object with schema information

WITH 
-- Get schema information
schema_info AS (
    SELECT 
        n.nspname AS schema_name,
        obj_description(n.oid) AS description
    FROM 
        pg_namespace n
    WHERE 
        n.nspname = $1
),

-- Get extensions installed in this schema
extensions AS (
    SELECT 
        e.extname AS name,
        e.extversion AS version,
        obj_description(e.oid) AS description
    FROM 
        pg_extension e
    JOIN 
        pg_namespace n ON n.oid = e.extnamespace
    WHERE 
        n.nspname = $1
    ORDER BY 
        e.extname
),

-- Get all tables in this schema with basic information
tables AS (
    SELECT 
        t.relname AS table_name,
        obj_description(t.oid) AS description,
        pg_stat_get_tuples_inserted(t.oid) AS row_count,
        pg_total_relation_size(t.oid) AS total_size_bytes
    FROM 
        pg_class t
    JOIN 
        pg_namespace n ON t.relnamespace = n.oid
    WHERE 
        n.nspname = $1
        AND t.relkind = 'r'  -- 'r' = regular table
    ORDER BY
        t.relname
),

-- Get all materialized views in this schema
materialized_views AS (
    SELECT 
        m.relname AS view_name,
        obj_description(m.oid) AS description,
        pg_stat_get_tuples_inserted(m.oid) AS row_count,
        pg_total_relation_size(m.oid) AS total_size_bytes
    FROM 
        pg_class m
    JOIN 
        pg_namespace n ON m.relnamespace = n.oid
    WHERE 
        n.nspname = $1
        AND m.relkind = 'm'  -- 'm' = materialized view
    ORDER BY
        m.relname
)

-- Main query to return all data in JSON format
SELECT jsonb_build_object(
    'schema_info',
    jsonb_build_object(
        'name', (SELECT schema_name FROM schema_info),
        'description', (SELECT description FROM schema_info),
        'extensions', (
            SELECT COALESCE(
                jsonb_agg(
                    jsonb_build_object(
                        'name', e.name,
                        'version', e.version,
                        'description', e.description
                    )
                ),
                '[]'::jsonb
            )
            FROM extensions e
        ),
        'tables', (
            SELECT COALESCE(
                jsonb_agg(
                    jsonb_build_object(
                        'name', t.table_name,
                        'description', t.description,
                        'row_count', t.row_count,
                        'size_bytes', t.total_size_bytes
                    ) ORDER BY t.table_name
                ),
                '[]'::jsonb
            )
            FROM tables t
        ),
        'materialized_views', (
            SELECT COALESCE(
                jsonb_agg(
                    jsonb_build_object(
                        'name', mv.view_name,
                        'description', mv.description,
                        'row_count', mv.row_count,
                        'size_bytes', mv.total_size_bytes
                    ) ORDER BY mv.view_name
                ),
                '[]'::jsonb
            )
            FROM materialized_views mv
        )
    )
) AS schema_info;