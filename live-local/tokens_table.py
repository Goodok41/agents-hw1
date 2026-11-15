"""Таблица токенов живого прогона: суммирует usage вызовов модели и печатает markdown.

Обрабатывает logs-live/*.json (лимит ответа 8000, контекст 16384). Журналы Qwen сняты run_all_agents.py
(реализация direct), журналы Gemma — run_logged.py; журналы с agent_error учитываются по partial_model_calls. Время берётся из logs-live/times.json, если есть.
"""
import json
from pathlib import Path

LOGS = Path(__file__).resolve().parents[1] / "logs-live"
MODELS = {"qwen": "qwen/qwen3.5-9b", "gemma": "google/gemma-4-12b"}
LIMIT = 8000


def model_usages(log):
    """Два формата журнала: run_logged.py (результат run_agent в корне) и run_all_agents.py (в поле result)."""
    trace = log.get("trace") or (log.get("result") or {}).get("trace") or []
    calls = [e for e in trace if e.get("event") == "model"] or log.get("partial_model_calls") or log.get("model_calls") or []
    if isinstance(calls, int):
        calls = []
    return [e.get("usage") or {} for e in calls]


def table(directory, limit):
    times_path = directory / "times.json"
    times = json.loads(times_path.read_text(encoding="utf-8")) if times_path.exists() else {}
    rows = ["| файл | модель | вопрос | вызовов модели | prompt | completion | из них reasoning | доля reasoning, % | обрезка | время, с |",
            "|---|---|---|---|---|---|---|---|---|---|"]
    for path in sorted(p for p in directory.glob("*.json") if p.name != "times.json"):
        log = json.loads(path.read_text(encoding="utf-8"))
        usages = model_usages(log)
        prompt = sum(u.get("prompt_tokens") or 0 for u in usages)
        completion = sum(u.get("completion_tokens") or 0 for u in usages)
        reasoning = sum((u.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0 for u in usages)
        share = f"{100 * reasoning / completion:.0f}" if completion else "—"
        # finish_reason в журнал не пишется: обрезкой считаем вызов, исчерпавший лимит (completion >= limit - 1).
        cut = [str(i) for i, u in enumerate(usages, 1) if (u.get("completion_tokens") or 0) >= limit - 1]
        cut = "да, вызов " + ", ".join(cut) if cut else "нет"
        model = MODELS.get(path.stem.split("_")[0], "?")
        question = log.get("question", "").replace("|", "/")
        took = times.get(path.stem, "не замерялось")
        rows.append(f"| {path.name} | {model} | {question} | {len(usages)} | {prompt} | {completion} | {reasoning} | {share} | {cut} | {took} |")
    return "\n".join(rows)


if __name__ == "__main__":
    print(table(LOGS, LIMIT))
