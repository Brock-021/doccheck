#!/usr/bin/env bash
# DocCheck · 测试运行脚本
# Usage: bash scripts/run_tests.sh [options]
#   Options:
#     --all        Run full test suite (including slow tests)
#     --fast       Run only fast tests (skip slow, default)
#     --coverage   Generate coverage report
#     --html       Generate HTML coverage report

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

echo "=============================="
echo " DocCheck 测试套件"
echo "=============================="

# Install dependencies if needed
if ! python3 -c "import pytest" 2>/dev/null; then
    echo "[setup] Installing test dependencies..."
    pip install -q pytest pytest-asyncio httpx pytest-cov
fi

if [ ! -d "venv" ]; then
    echo "[setup] Creating virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
    pip install -q -r requirements.txt 2>/dev/null || true
    pip install -q pytest pytest-asyncio httpx pytest-cov
fi

ARGS=""

# Parse arguments
for arg in "$@"; do
    case "$arg" in
        --all)
            ARGS="$ARGS"
            ;;
        --fast)
            ARGS="$ARGS -m 'not slow'"
            ;;
        --coverage)
            ARGS="$ARGS --cov=doccheck --cov-report=term-missing"
            ;;
        --html)
            ARGS="$ARGS --cov=doccheck --cov-report=html"
            ;;
    esac
done

# Default: skip slow tests
if [[ ! "$*" =~ --all ]] && [[ ! "$*" =~ --fast ]]; then
    ARGS="-m 'not slow' $ARGS"
fi

echo ""
echo "[run] pytest tests/ -v $ARGS"
echo "=============================="
eval python3 -m pytest tests/ -v $ARGS

echo ""
echo "=============================="
echo " 测试完成"
echo "=============================="
