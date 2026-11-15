# agents-hw1 · ДЗ №1 · вариант C

Агент по документам DemoDesk (Python 3.11+, без зависимостей), две попытки одного изменения.
- `direct/` · без спецификации; `with-spec/` · с `openspec/changes/harden-agent/` (OpenSpec 1.14.1)
- `change-brief.md` · общее изменение; `prompts.txt` · промпты; `report.md` · отчёт; `logs/` · реальные логи
- Модель: Claude Sonnet 5.5, 15.11.2026. Живая модель не запускалась; ключей в репозитории нет.

Запуск (в папке direct или with-spec):
    python tests/test_agent.py
    python agent.py --replay --output replay.json
Спека: `cd with-spec && openspec validate harden-agent --strict --no-interactive`
