-- server/resources/sql/db_get_database.sql

-- Comprehensive database structure query
-- Retrieve complete database schema information as JSON

-- Get all non-system schemas
WITH schemas AS (
    SELECT 
        n.nspname AS schema_name,
        obj_description(n.oid) AS description
    FROM 
        pg_namespace n
    WHERE 
        n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
        AND n.nspname NOT LIKE 'pg_%'
),

-- Get all tables for each schema
tables AS (
    SELECT 
        s.schema_name,
        t.relname AS table_name,
        obj_description(t.oid) AS description,
        pg_stat_get_tuples_inserted(t.oid) AS row_count
    FROM 
        schemas s
    JOIN 
        pg_class t ON t.relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = s.schema_name)
    WHERE 
        t.relkind = 'r'  -- 'r' = regular table
),

-- Get all columns for all tables
columns AS (
    SELECT 
        t.schema_name,
        t.table_name,
        a.attname AS column_name,
        pg_catalog.format_type(a.atttypid, a.atttypmod) AS data_type,
        NOT a.attnotnull AS is_nullable,
        (SELECT pg_catalog.pg_get_expr(adbin, adrelid) FROM pg_catalog.pg_attrdef d
         WHERE d.adrelid = a.attrelid AND d.adnum = a.attnum AND a.atthasdef) AS column_default,
        col_description(a.attrelid, a.attnum) AS description,
        a.attnum AS ordinal_position
    FROM 
        tables t
    JOIN 
        pg_catalog.pg_class c ON c.relname = t.table_name
        AND c.relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = t.schema_name)
    JOIN 
        pg_catalog.pg_attribute a ON a.attrelid = c.oid
    WHERE 
        a.attnum > 0  -- Skip system columns
        AND NOT a.attisdropped  -- Skip dropped columns
),

-- Get all primary and unique constraints
key_constraints AS (
    SELECT 
        t.schema_name,
        t.table_name,
        con.conname AS constraint_name,
        con.contype AS constraint_type,
        CASE 
            WHEN con.contype = 'p' THEN 'PRIMARY KEY'
            WHEN con.contype = 'u' THEN 'UNIQUE'
            ELSE 'OTHER'
        END AS constraint_type_desc,
        array_agg(a.attname ORDER BY array_position(con.conkey, a.attnum)) AS column_names
    FROM 
        tables t
    JOIN 
        pg_constraint con ON con.conrelid = (
            SELECT oid FROM pg_class 
            WHERE relname = t.table_name 
            AND relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = t.schema_name)
        )
    JOIN 
        pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = ANY(con.conkey)
    WHERE 
        con.contype IN ('p', 'u')  -- 'p' = primary key, 'u' = unique
    GROUP BY 
        t.schema_name, t.table_name, con.conname, con.contype
),

-- Get all foreign key constraints
foreign_keys AS (
    SELECT 
        t.schema_name,
        t.table_name,
        con.conname AS constraint_name,
        'f' AS constraint_type,
        'FOREIGN KEY' AS constraint_type_desc,
        array_agg(a.attname ORDER BY array_position(con.conkey, a.attnum)) AS column_names,
        nr.nspname AS referenced_schema,
        ref_table.relname AS referenced_table,
        array_agg(ref_col.attname ORDER BY array_position(con.confkey, ref_col.attnum)) AS referenced_columns
    FROM 
        tables t
    JOIN 
        pg_constraint con ON con.conrelid = (
            SELECT oid FROM pg_class 
            WHERE relname = t.table_name 
            AND relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = t.schema_name)
        )
    JOIN 
        pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = ANY(con.conkey)
    JOIN 
        pg_class ref_table ON ref_table.oid = con.confrelid
    JOIN 
        pg_namespace nr ON nr.oid = ref_table.relnamespace
    JOIN 
        pg_attribute ref_col ON ref_col.attrelid = con.confrelid AND ref_col.attnum = ANY(con.confkey)
    WHERE 
        con.contype = 'f'  -- 'f' = foreign key
    GROUP BY 
        t.schema_name, t.table_name, con.conname, nr.nspname, ref_table.relname
),

-- Get all check constraints
check_constraints AS (
    SELECT 
        t.schema_name,
        t.table_name,
        con.conname AS constraint_name,
        'c' AS constraint_type,
        'CHECK' AS constraint_type_desc,
        pg_get_constraintdef(con.oid) AS definition
    FROM 
        tables t
    JOIN 
        pg_constraint con ON con.conrelid = (
            SELECT oid FROM pg_class 
            WHERE relname = t.table_name 
            AND relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = t.schema_name)
        )
    WHERE 
        con.contype = 'c'  -- 'c' = check constraint
),

-- Get all indexes
indexes AS (
    SELECT 
        t.schema_name,
        t.table_name,
        i.relname AS index_name,
        am.amname AS index_type,
        ix.indisunique AS is_unique,
        ix.indisprimary AS is_primary,
        array_agg(a.attname ORDER BY array_position(ix.indkey::int[], a.attnum)) AS column_names
    FROM 
        tables t
    JOIN 
        pg_class tbl ON tbl.relname = t.table_name
        AND tbl.relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = t.schema_name)
    JOIN 
        pg_index ix ON ix.indrelid = tbl.oid
    JOIN 
        pg_class i ON i.oid = ix.indexrelid
    JOIN 
        pg_am am ON am.oid = i.relam
    JOIN 
        pg_attribute a ON a.attrelid = tbl.oid AND a.attnum = ANY(ix.indkey::int[])
    GROUP BY 
        t.schema_name, t.table_name, i.relname, am.amname, ix.indisunique, ix.indisprimary
)

-- Main query to return all data in JSON format
SELECT 
    jsonb_build_object(
        'schemas',
        (
            SELECT jsonb_agg(
                jsonb_build_object(
                    'name', s.schema_name,
                    'description', s.description,
                    'tables', (
                        SELECT jsonb_agg(
                            jsonb_build_object(
                                'name', t.table_name,
                                'description', t.description,
                                'row_count', t.row_count,
                                'columns', (
                                    SELECT jsonb_agg(
                                        jsonb_build_object(
                                            'name', c.column_name,
                                            'type', c.data_type,
                                            'nullable', c.is_nullable,
                                            'default', c.column_default,
                                            'description', c.description,
                                            'constraints', (
                                                SELECT jsonb_agg(
                                                    constraint_type_desc
                                                )
                                                FROM (
                                                    SELECT kc.constraint_type_desc
                                                    FROM key_constraints kc
                                                    WHERE kc.schema_name = t.schema_name
                                                      AND kc.table_name = t.table_name
                                                      AND c.column_name = ANY(kc.column_names)
                                                    UNION ALL
                                                    SELECT 'FOREIGN KEY'
                                                    FROM foreign_keys fk
                                                    WHERE fk.schema_name = t.schema_name
                                                      AND fk.table_name = t.table_name
                                                      AND c.column_name = ANY(fk.column_names)
                                                ) constraints
                                            )
                                        ) ORDER BY c.ordinal_position
                                    )
                                    FROM columns c
                                    WHERE c.schema_name = t.schema_name
                                      AND c.table_name = t.table_name
                                ),
                                'foreign_keys', (
                                    SELECT jsonb_agg(
                                        jsonb_build_object(
                                            'name', fk.constraint_name,
                                            'columns', fk.column_names,
                                            'referenced_schema', fk.referenced_schema,
                                            'referenced_table', fk.referenced_table,
                                            'referenced_columns', fk.referenced_columns
                                        )
                                    )
                                    FROM foreign_keys fk
                                    WHERE fk.schema_name = t.schema_name
                                      AND fk.table_name = t.table_name
                                ),
                                'indexes', (
                                    SELECT jsonb_agg(
                                        jsonb_build_object(
                                            'name', idx.index_name,
                                            'type', idx.index_type,
                                            'is_unique', idx.is_unique,
                                            'is_primary', idx.is_primary,
                                            'columns', idx.column_names
                                        )
                                    )
                                    FROM indexes idx
                                    WHERE idx.schema_name = t.schema_name
                                      AND idx.table_name = t.table_name
                                ),
                                'check_constraints', (
                                    SELECT jsonb_agg(
                                        jsonb_build_object(
                                            'name', cc.constraint_name,
                                            'definition', cc.definition
                                        )
                                    )
                                    FROM check_constraints cc
                                    WHERE cc.schema_name = t.schema_name
                                      AND cc.table_name = t.table_name
                                )
                            ) ORDER BY t.table_name
                        )
                        FROM tables t
                        WHERE t.schema_name = s.schema_name
                    )
                ) ORDER BY s.schema_name
            )
            FROM schemas s
        )
    ) AS db_structure;