"""Таблица токенов живого прогона: суммирует usage событий "model" из logs-live/*.json и печатает markdown."""
import json
from pathlib import Path

LOGS = Path(__file__).resolve().parents[1] / "logs-live"
MODELS = {"qwen": "qwen/qwen3.5-9b", "gemma": "google/gemma-4-12b"}

rows = ["| файл | модель | вопрос | вызовов модели | prompt | completion | из них reasoning | доля reasoning, % |",
        "|---|---|---|---|---|---|---|---|"]
for path in sorted(LOGS.glob("*.json")):
    log = json.loads(path.read_text(encoding="utf-8"))
    calls = [e for e in log.get("trace", []) if e.get("event") == "model"]
    prompt = completion = reasoning = 0
    for e in calls:
        usage = e.get("usage") or {}
        prompt += usage.get("prompt_tokens") or 0
        completion += usage.get("completion_tokens") or 0
        reasoning += (usage.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0
    share = f"{100 * reasoning / completion:.0f}" if completion else "—"
    model = MODELS.get(path.stem.split("_")[0], "?")
    question = log.get("question", "").replace("|", "/")
    rows.append(f"| {path.name} | {model} | {question} | {len(calls)} | {prompt} | {completion} | {reasoning} | {share} |")
print("\n".join(rows))
