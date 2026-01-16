#!/usr/bin/env bash
set -e

cd /Users/alex/PycharmProjects/planner

tar --exclude='.git' \
    --exclude='.venv' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='.pytest_cache' \
    --exclude='.ruff_cache' \
    --exclude='.idea' \
    --exclude='.DS_Store' \
    --exclude='postgres_data' \
    --exclude='.env' \
    --exclude='planner_backup_*.tar.gz' \
    -czf planner_backup_$(date +%Y%m%d_%H%M).tar.gz .
