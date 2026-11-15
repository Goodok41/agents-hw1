"""Таблица токенов живого прогона: суммирует usage вызовов модели и печатает markdown.

Обрабатывает logs-live/*.json (лимит ответа 700) и logs-live/nolimit/*.json (лимит 8000),
для каждого каталога печатается отдельная таблица. Журналы с agent_error (run_logged.py)
учитываются по partial_model_calls. Время берётся из logs-live/nolimit/times.json, если есть.
"""
import json
from pathlib import Path

LOGS = Path(__file__).resolve().parents[1] / "logs-live"
MODELS = {"qwen": "qwen/qwen3.5-9b", "gemma": "google/gemma-4-12b"}
SETS = [("Лимит ответа 700", LOGS, 700), ("Без лимита ответа (8000)", LOGS / "nolimit", 8000)]


def model_usages(log):
    calls = [e for e in log.get("trace", []) if e.get("event") == "model"] or log.get("partial_model_calls", [])
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
    for title, directory, limit in SETS:
        if directory.is_dir():
            print(f"### {title}\n\n{table(directory, limit)}\n")
