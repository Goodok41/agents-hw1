#!/bin/sh
# Прогон единого набора A1-A5 по всем реализациям. Запуск из корня репозитория: sh acceptance/run.sh
# Журналы: logs/acceptance_<имя>.log. Код возврата 0, даже если в каком-то наборе есть падения.
cd "$(dirname "$0")/.." || exit 1
mkdir -p logs
for impl in direct with-spec opus/direct opus/with-spec; do
    name=$(echo "$impl" | tr '/' '-')
    PYTHONDONTWRITEBYTECODE=1 python3 acceptance/test_a1_a5.py "$impl" -v > "logs/acceptance_$name.log" 2>&1
    echo "$impl: $(tail -1 "logs/acceptance_$name.log")"
done
