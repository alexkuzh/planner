-- planner_db_audit.sql
-- Generated: 2026-01-10T18:59:04.222376Z
-- Purpose: dump schema details needed for "DB hardening" work (constraints, indexes, key columns).
--
-- How to run (macOS system terminal):
--   1) Copy this file into the Postgres container:
--        docker cp planner_db_audit.sql planner_postgres:/tmp/planner_db_audit.sql
--   2) Execute:
--        docker exec -i planner_postgres psql -U planner -d planner_test -v ON_ERROR_STOP=1 -f /tmp/planner_db_audit.sql
--
-- Notes:
-- - This script turns pager off so output is continuous.
-- - It will error if some optional tables are missing; in that case, delete the missing-table sections
--   or create empty tables, or tell me which ones don't exist and I'll adjust.

\pset pager off
\set ON_ERROR_STOP on

\echo '=== DB AUDIT START ==='
\echo 'Database: ' :DBNAME
\echo 'User: ' :USER
\echo 'Timestamp (server):'
SELECT now();

\echo ''
\echo '=== Extensions (pgcrypto, etc.) ==='
SELECT extname, extversion
FROM pg_extension
ORDER BY extname;

\echo ''
\echo '=== Tables present? (public schema) ==='
SELECT c.relname AS table_name
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname='public'
  AND c.relkind='r'
  AND c.relname IN ('tasks','task_transitions','task_events','qc_inspections')
ORDER BY c.relname;

\echo ''
\echo '=== Columns (information_schema) for target tables ==='
SELECT table_name,
       ordinal_position,
       column_name,
       data_type,
       udt_name,
       is_nullable,
       column_default
FROM information_schema.columns
WHERE table_schema='public'
  AND table_name IN ('tasks','task_transitions','task_events','qc_inspections')
ORDER BY table_name, ordinal_position;

\echo ''
\echo '=== Constraints (PK/FK/UNIQUE/CHECK) with convalidated ==='
SELECT rel.relname AS table_name,
       c.conname,
       c.contype,
       c.convalidated,
       pg_get_constraintdef(c.oid) AS def
FROM pg_constraint c
JOIN pg_class rel ON rel.oid = c.conrelid
JOIN pg_namespace n ON n.oid = rel.relnamespace
WHERE n.nspname='public'
  AND rel.relname IN ('tasks','task_transitions','task_events','qc_inspections')
ORDER BY rel.relname, c.contype, c.conname;

\echo ''
\echo '=== Indexes (including partial) definitions ==='
SELECT schemaname, tablename, indexname, indexdef
FROM pg_indexes
WHERE schemaname='public'
  AND tablename IN ('tasks','task_transitions','task_events','qc_inspections')
ORDER BY tablename, indexname;

\echo ''
\echo '=== Tasks: unique / PK / composite key candidates (all unique/primary indexes) ==='
SELECT rel.relname AS table_name,
       i.relname AS index_name,
       ix.indisunique AS is_unique,
       ix.indisprimary AS is_primary,
       pg_get_indexdef(ix.indexrelid) AS index_def
FROM pg_class rel
JOIN pg_namespace n ON n.oid = rel.relnamespace
JOIN pg_index ix ON ix.indrelid = rel.oid
JOIN pg_class i ON i.oid = ix.indexrelid
WHERE n.nspname='public'
  AND rel.relname = 'tasks'
  AND (ix.indisunique OR ix.indisprimary)
ORDER BY ix.indisprimary DESC, ix.indisunique DESC, index_name;

\echo ''
\echo '=== Foreign keys only (quick view) ==='
SELECT rel.relname AS table_name,
       c.conname,
       c.convalidated,
       pg_get_constraintdef(c.oid) AS fk_def
FROM pg_constraint c
JOIN pg_class rel ON rel.oid = c.conrelid
JOIN pg_namespace n ON n.oid = rel.relnamespace
WHERE n.nspname='public'
  AND rel.relname IN ('tasks','task_transitions','task_events','qc_inspections')
  AND c.contype = 'f'
ORDER BY rel.relname, c.conname;

\echo ''
\echo '=== Row counts (sanity) ==='
SELECT 'tasks'::text AS table_name, count(*)::bigint AS rows FROM tasks
UNION ALL
SELECT 'task_transitions'::text, count(*)::bigint FROM task_transitions
UNION ALL
SELECT 'task_events'::text, count(*)::bigint FROM task_events
UNION ALL
SELECT 'qc_inspections'::text, count(*)::bigint FROM qc_inspections;

\echo ''
\echo '=== (Optional) Recent transitions sample ==='
SELECT org_id, task_id, action, from_status, to_status, created_at, client_event_id
FROM task_transitions
ORDER BY created_at DESC
LIMIT 20;

\echo ''
\echo '=== DB AUDIT END ==='
