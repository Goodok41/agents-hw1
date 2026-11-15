# agents-hw1 · ДЗ №1 · вариант C

Агент по документам DemoDesk (Python 3.11+, без зависимостей). Одно изменение (R1–R6 в `change-brief.md`) сделано двумя способами, каждый в отдельной новой сессии Claude Sonnet 5.5. Отчёт — `report.md`, промпты — `prompts.txt`. Ключей API в репозитории нет.

## Структура
- `direct/` · реализация без спецификации (Sonnet 5.5), свои тесты `tests/`, итог сессии `RESULTS_SONNET.md`
- `with-spec/` · реализация через OpenSpec (`openspec/changes/harden-agent/`, OpenSpec 2.0.0), свои тесты, `RESULTS_SONNET.md`
- `acceptance/` · единый приёмочный набор A1–A5 (`test_a1_a5.py`) для любой реализации и `run.sh`
- `live-local/` · копия `direct/` с правкой для LM Studio (`local.patch`), тесты B1–B5 и W1–W4, скрипты живого прогона, `RESULTS.md`
- `logs/` · журналы тестов, валидатора и приёмочного набора
- `logs-live/` · журналы живого прогона (Qwen, Gemma); `logs-live/agents/` · все реализации на Qwen
- `opus/`, `logs-opus/` · те же два способа на Claude Opus 5.5 для сравнения
- `change-brief.md` · бриф (R1–R6 + таблица A1–A5); `base.sha256` · хеши стартового кода

## Запуск
Из корня репозитория:

    python3 direct/tests/test_agent.py                    # свои тесты direct
    python3 with-spec/tests/test_agent.py                 # свои тесты with-spec
    sh acceptance/run.sh                                  # A1–A5 для direct, with-spec, opus/* -> logs/acceptance_*.log
    python3 acceptance/test_a1_a5.py live-local -v        # A1–A5 для любой папки с agent.py
    python3 -m unittest discover -s live-local/tests      # B1–B5, W1–W4 (OK, expected failures=11)
    python3 direct/agent.py --replay                      # регрессия --replay

Спека: `cd with-spec && openspec validate harden-agent --strict --no-interactive`

Живой прогон (нужен LM Studio на `http://localhost:1234/v1`, контекст 16384):

    cd live-local && sh run_set.sh qwen                   # или gemma; журналы -> logs-live/
    python3 live-local/run_all_agents.py                  # все реализации на Qwen -> logs-live/agents/
    python3 live-local/tokens_table.py                    # таблица токенов
