-- server/resources/sql/get_schema_table.sql
-- Comprehensive query to get all details for a specific table
-- Returns a JSON structure with columns, constraints, indexes, and statistics

WITH 
-- Get table information
table_info AS (
    SELECT 
        t.relname AS table_name,
        obj_description(t.oid) AS description,
        pg_stat_get_tuples_inserted(t.oid) AS row_count,
        pg_total_relation_size(t.oid) AS total_size_bytes,
        pg_table_size(t.oid) AS table_size_bytes,
        pg_indexes_size(t.oid) AS indexes_size_bytes,
        t.relkind AS kind
    FROM 
        pg_class t
    JOIN 
        pg_namespace n ON t.relnamespace = n.oid
    WHERE 
        n.nspname = $1
        AND t.relname = $2
        AND t.relkind = 'r'  -- 'r' = regular table
),

-- Get all columns for this table
columns AS (
    SELECT 
        a.attname AS column_name,
        pg_catalog.format_type(a.atttypid, a.atttypmod) AS data_type,
        NOT a.attnotnull AS is_nullable,
        (SELECT pg_catalog.pg_get_expr(adbin, adrelid) FROM pg_catalog.pg_attrdef d
         WHERE d.adrelid = a.attrelid AND d.adnum = a.attnum AND a.atthasdef) AS column_default,
        col_description(a.attrelid, a.attnum) AS description,
        a.attnum AS ordinal_position,
        a.attidentity IN ('a', 'd') AS is_identity,
        CASE 
            WHEN a.attidentity = 'a' THEN 'ALWAYS'
            WHEN a.attidentity = 'd' THEN 'BY DEFAULT'
            ELSE NULL 
        END AS identity_generation,
        a.atthasdef AS has_default,
        a.attisdropped AS is_dropped,
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

-- Get all primary and unique constraints
key_constraints AS (
    SELECT 
        con.conname AS constraint_name,
        con.contype AS constraint_type,
        CASE 
            WHEN con.contype = 'p' THEN 'PRIMARY KEY'
            WHEN con.contype = 'u' THEN 'UNIQUE'
            ELSE 'OTHER'
        END AS constraint_type_desc,
        obj_description(con.oid) AS description,
        pg_get_constraintdef(con.oid) AS definition,
        array_agg(a.attname ORDER BY array_position(con.conkey, a.attnum)) AS column_names
    FROM 
        pg_constraint con
    JOIN 
        pg_namespace n ON n.oid = con.connamespace
    JOIN 
        pg_class t ON t.oid = con.conrelid
    JOIN 
        pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = ANY(con.conkey)
    WHERE 
        n.nspname = $1
        AND t.relname = $2
        AND con.contype IN ('p', 'u')  -- 'p' = primary key, 'u' = unique
    GROUP BY 
        con.conname, con.contype, con.oid
    ORDER BY 
        con.contype, con.conname
),

-- Get all foreign key constraints
foreign_keys AS (
    SELECT 
        con.conname AS constraint_name,
        'f' AS constraint_type,
        'FOREIGN KEY' AS constraint_type_desc,
        obj_description(con.oid) AS description,
        pg_get_constraintdef(con.oid) AS definition,
        array_agg(a.attname ORDER BY array_position(con.conkey, a.attnum)) AS column_names,
        nr.nspname AS referenced_schema,
        ref_table.relname AS referenced_table,
        array_agg(ref_col.attname ORDER BY array_position(con.confkey, ref_col.attnum)) AS referenced_columns,
        CASE con.confdeltype 
            WHEN 'a' THEN 'NO ACTION'
            WHEN 'r' THEN 'RESTRICT'
            WHEN 'c' THEN 'CASCADE'
            WHEN 'n' THEN 'SET NULL'
            WHEN 'd' THEN 'SET DEFAULT'
            ELSE NULL
        END AS delete_rule,
        CASE con.confupdtype
            WHEN 'a' THEN 'NO ACTION'
            WHEN 'r' THEN 'RESTRICT'
            WHEN 'c' THEN 'CASCADE'
            WHEN 'n' THEN 'SET NULL'
            WHEN 'd' THEN 'SET DEFAULT'
            ELSE NULL
        END AS update_rule
    FROM 
        pg_constraint con
    JOIN 
        pg_namespace n ON n.oid = con.connamespace
    JOIN 
        pg_class t ON t.oid = con.conrelid
    JOIN 
        pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = ANY(con.conkey)
    JOIN 
        pg_class ref_table ON ref_table.oid = con.confrelid
    JOIN 
        pg_namespace nr ON nr.oid = ref_table.relnamespace
    JOIN 
        pg_attribute ref_col ON ref_col.attrelid = con.confrelid AND ref_col.attnum = ANY(con.confkey)
    WHERE 
        n.nspname = $1
        AND t.relname = $2
        AND con.contype = 'f'  -- 'f' = foreign key
    GROUP BY 
        con.conname, con.contype, con.oid, nr.nspname, ref_table.relname, con.confdeltype, con.confupdtype
    ORDER BY 
        con.conname
),

-- Get check constraints
check_constraints AS (
    SELECT 
        con.conname AS constraint_name,
        'c' AS constraint_type,
        'CHECK' AS constraint_type_desc,
        obj_description(con.oid) AS description,
        pg_get_constraintdef(con.oid) AS definition
    FROM 
        pg_constraint con
    JOIN 
        pg_namespace n ON n.oid = con.connamespace
    JOIN 
        pg_class t ON t.oid = con.conrelid
    WHERE 
        n.nspname = $1
        AND t.relname = $2
        AND con.contype = 'c'  -- 'c' = check constraint
    ORDER BY 
        con.conname
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
        ix.indisexclusion AS is_exclusion,
        ix.indimmediate AS is_immediate,
        ix.indisclustered AS is_clustered,
        ix.indisvalid AS is_valid,
        i.relpages AS pages,
        i.reltuples AS rows,
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
        i.relname, i.oid, am.amname, ix.indisunique, ix.indisprimary, 
        ix.indisexclusion, ix.indimmediate, ix.indisclustered, ix.indisvalid,
        i.relpages, i.reltuples
    ORDER BY 
        i.relname
),

-- Get table statistics
table_stats AS (
    SELECT 
        seq_scan,
        seq_tup_read,
        idx_scan,
        idx_tup_fetch,
        n_tup_ins,
        n_tup_upd,
        n_tup_del,
        n_tup_hot_upd,
        n_live_tup,
        n_dead_tup,
        n_mod_since_analyze,
        last_vacuum,
        last_autovacuum,
        last_analyze,
        last_autoanalyze,
        vacuum_count,
        autovacuum_count,
        analyze_count,
        autoanalyze_count
    FROM 
        pg_stat_user_tables
    WHERE 
        schemaname = $1
        AND relname = $2
)

-- Main query to build the JSON result
SELECT jsonb_build_object(
    'table',
    jsonb_build_object(
        'name', (SELECT table_name FROM table_info),
        'description', (SELECT description FROM table_info),
        'row_count', (SELECT row_count FROM table_info),
        'size', jsonb_build_object(
            'total_bytes', (SELECT total_size_bytes FROM table_info),
            'table_bytes', (SELECT table_size_bytes FROM table_info),
            'indexes_bytes', (SELECT indexes_size_bytes FROM table_info)
        ),
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
                        'is_identity', c.is_identity,
                        'identity_generation', c.identity_generation,
                        'storage', c.storage_type_desc
                    )
                    ORDER BY c.ordinal_position
                ),
                '[]'::jsonb
            )
            FROM columns c
        ),
        'constraints', jsonb_build_object(
            'primary_keys', (
                SELECT COALESCE(
                    jsonb_agg(
                        jsonb_build_object(
                            'name', kc.constraint_name,
                            'columns', kc.column_names,
                            'definition', kc.definition,
                            'description', kc.description
                        )
                    ),
                    '[]'::jsonb
                )
                FROM key_constraints kc
                WHERE kc.constraint_type = 'p'
            ),
            'unique_constraints', (
                SELECT COALESCE(
                    jsonb_agg(
                        jsonb_build_object(
                            'name', kc.constraint_name,
                            'columns', kc.column_names,
                            'definition', kc.definition,
                            'description', kc.description
                        )
                    ),
                    '[]'::jsonb
                )
                FROM key_constraints kc
                WHERE kc.constraint_type = 'u'
            ),
            'foreign_keys', (
                SELECT COALESCE(
                    jsonb_agg(
                        jsonb_build_object(
                            'name', fk.constraint_name,
                            'columns', fk.column_names,
                            'referenced_schema', fk.referenced_schema,
                            'referenced_table', fk.referenced_table,
                            'referenced_columns', fk.referenced_columns,
                            'delete_rule', fk.delete_rule,
                            'update_rule', fk.update_rule,
                            'definition', fk.definition,
                            'description', fk.description
                        )
                    ),
                    '[]'::jsonb
                )
                FROM foreign_keys fk
            ),
            'check_constraints', (
                SELECT COALESCE(
                    jsonb_agg(
                        jsonb_build_object(
                            'name', cc.constraint_name,
                            'definition', cc.definition,
                            'description', cc.description
                        )
                    ),
                    '[]'::jsonb
                )
                FROM check_constraints cc
            )
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
                        'size', jsonb_build_object(
                            'pages', i.pages,
                            'rows', i.rows
                        ),
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
            FROM table_stats s
        )
    )
) AS table_details;