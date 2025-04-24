-- server/resources/sql/list_schemas.sql
-- List all non-system schemas in the database
-- Returns a JSON array of schema objects
WITH schemas AS (
    SELECT
        schema_name,
        obj_description(pg_namespace.oid) as description
    FROM information_schema.schemata
    JOIN pg_namespace ON pg_namespace.nspname = schema_name
    WHERE
        schema_name NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
        AND schema_name NOT LIKE 'pg_%'
    ORDER BY schema_name
)
SELECT jsonb_build_object(
    'schemas',
    jsonb_agg(
        jsonb_build_object(
            'name', schema_name,
            'description', description
        )
    )
) AS schema_list
FROM schemas;