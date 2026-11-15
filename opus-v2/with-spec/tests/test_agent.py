"""Тесты harden-agent: проверки A1–A5 из change-brief.md и регрессия --replay.

unittest, без сети: модель — контролируемая заглушка, инструменты локальные
(для A4 — заглушка инструмента с искусственным сбоем).
"""
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import agent  # noqa: E402

CFG = {"max_model_calls": 6, "max_tool_calls": 12, "max_output_tokens": 350, "timeout_seconds": 30}

# Ответ --replay, зафиксированный до изменения (исходный agent.py, 225 строк).
REPLAY_ANSWER_BEFORE = (
    " Для обработки скана: сначала выполните распознавание текста с помощью OCR, затем проверьте числа, "
    "даты и имена по исходному изображению. Если текст распознан плохо, переснимите документ или исправьте "
    "ошибочные фрагменты вручную (D01:1-3). Перед отправкой текста во внешний API уберите персональные и "
    "конфиденциальные сведения и убедитесь, что у вас есть разрешение на передачу данных выбранному внешнему "
    "сервису (D02:1-2)."
)


def call(name, args, idx=0):
    arguments = args if isinstance(args, str) else json.dumps(args, ensure_ascii=False)
    return {"id": f"c{idx}_{name}", "type": "function", "function": {"name": name, "arguments": arguments}}


def tools(*calls):
    return {"role": "assistant", "content": None, "tool_calls": list(calls)}


def final(text):
    return {"role": "assistant", "content": text}


class ScriptedModel:
    """Заглушка модели: отдаёт заранее заданные реплики, запоминает полученную историю."""

    def __init__(self, replies, repeat_last=False):
        self.replies, self.repeat_last, self.calls, self.histories = list(replies), repeat_last, 0, []

    def __call__(self, history, tool_schemas):
        self.histories.append([dict(m) for m in history])
        self.calls += 1
        if self.replies:
            reply = self.replies.pop(0) if (len(self.replies) > 1 or not self.repeat_last) else self.replies[0]
            return json.loads(json.dumps(reply)), {}
        raise AssertionError("Заглушка модели вызвана сверх сценария")


def run(model, question="тест", cfg=None, tool_fn=agent.run_allowed_tool):
    return agent.run_agent(question, cfg or CFG, model, mode="TEST", emit=lambda *_: None, tool_fn=tool_fn)


def tool_events(result, name=None):
    return [e for e in result["trace"] if e["event"] == "tool" and (name is None or e["name"] == name)]


def remarks(model):
    """Тексты замечаний программы, переданные модели."""
    return [m["content"] for m in model.histories[-1] if m["role"] == "user" and m["content"].startswith("Проверка программы")]


class TestAcceptance(unittest.TestCase):
    # A1. «Что проверить после OCR и перед внешним API?» — поиск + чтение; ответ подтверждён D01/D02.
    def test_a1_ocr_and_external_api_answer_confirmed_by_d01_d02(self):
        q = "Что проверить после OCR и перед внешним API?"
        model = ScriptedModel([
            tools(call("search_docs", {"query": "проверка после OCR и перед внешним API"})),
            tools(call("read_doc", {"doc_id": "D01"}, 1), call("read_doc", {"doc_id": "D02"}, 2)),
            final("После OCR проверьте числа, даты и имена по исходному изображению [D01:2]. "
                  "Перед внешним API уберите персональные сведения и проверьте разрешение [D02:1-2]."),
        ])
        result = run(model, q)
        self.assertEqual(result["stop_reason"], "final_answer")
        search = tool_events(result, "search_docs")
        self.assertEqual(len(search), 1)
        self.assertEqual(search[0]["status"], "ok")
        found = {d["id"] for d in search[0]["result"]["documents"]}
        self.assertTrue({"D01", "D02"} <= found, found)
        reads = tool_events(result, "read_doc")
        self.assertEqual([e["status"] for e in reads], ["ok", "ok"])
        self.assertEqual(result["read_ids"], ["D01", "D02"])
        cited = set(re.findall(r"\bD\d{2}\b", result["answer"]))
        self.assertEqual(cited, {"D01", "D02"})
        self.assertTrue(cited <= set(result["read_ids"]))
        self.assertEqual(result["missing_ids"], [])
        self.assertEqual(result["tool_errors"], 0)

    def test_a1_answer_citing_unread_d02_is_not_accepted(self):
        model = ScriptedModel([
            tools(call("search_docs", {"query": "OCR внешний API"})),
            tools(call("read_doc", {"doc_id": "D01"}, 1)),
            final("Проверьте числа [D01:2] и уберите персональные сведения [D02:1]."),
            tools(call("read_doc", {"doc_id": "D02"}, 2)),
            final("Проверьте числа [D01:2] и уберите персональные сведения [D02:1]."),
        ])
        result = run(model, "Что проверить после OCR и перед внешним API?")
        self.assertEqual(result["stop_reason"], "final_answer")
        self.assertEqual(result["read_ids"], ["D01", "D02"])
        texts = remarks(model)
        self.assertEqual(len(texts), 1)
        self.assertIn("D02", texts[0])
        self.assertNotIn("D01", texts[0].split("Не прочитаны через read_doc:")[1].split(".")[0])

    # A2. «Сколько стоит лицензия DemoDesk?» — в D03 цены нет; агент не выдумывает тариф.
    def test_a2_demodesk_license_price_absent_reported(self):
        q = "Сколько стоит лицензия DemoDesk?"
        model = ScriptedModel([
            tools(call("search_docs", {"query": "лицензия DemoDesk цена"})),
            tools(call("read_doc", {"doc_id": "D03"}, 1)),
            final("В учебном корпусе нет сведений о цене лицензии DemoDesk: тариф и цена не указаны [D03:3]."),
        ])
        result = run(model, q)
        self.assertEqual(result["stop_reason"], "final_answer")
        found = [d["id"] for d in tool_events(result, "search_docs")[0]["result"]["documents"]]
        self.assertIn("D03", found)
        d03_lines = [l["text"] for l in tool_events(result, "read_doc")[0]["result"]["lines"]]
        self.assertIn("Тариф и цена лицензии в корпусе не указаны.", d03_lines)
        self.assertEqual(result["read_ids"], ["D03"])
        self.assertIn("нет сведений", result["answer"])
        self.assertIsNone(re.search(r"\d+\s*(руб|₽|\$|usd|eur|€)", result["answer"], re.I))

    def test_a2_invented_price_with_unread_source_not_returned(self):
        invented = "Лицензия DemoDesk стоит 990 руб. в месяц [D07:1]."
        model = ScriptedModel([
            tools(call("search_docs", {"query": "лицензия DemoDesk цена"})),
            tools(call("read_doc", {"doc_id": "D03"}, 1)),
            final(invented), final(invented), final(invented),
        ])
        result = run(model, "Сколько стоит лицензия DemoDesk?")
        self.assertEqual(result["stop_reason"], "unverified_sources")
        self.assertIsNone(result["answer"])
        self.assertNotIn("990", json.dumps({k: v for k, v in result.items() if k != "trace"}, ensure_ascii=False))
        self.assertEqual(len(remarks(model)), 2)
        self.assertTrue(all("D07" in t for t in remarks(model)))

    # A3. Неизвестный ID D99 и неверные аргументы — структурированная ошибка без падения.
    def test_a3_unknown_d99_and_bad_arguments_structured_errors(self):
        model = ScriptedModel([
            tools(call("search_docs", {"query": "OCR"})),
            tools(call("read_doc", {"doc_id": "D99"}, 1),
                  call("read_doc", "not json", 2),
                  call("read_doc", {"id": "D01"}, 3),
                  call("read_doc", {"doc_id": ""}, 4),
                  call("delete_doc", {"doc_id": "D01"}, 5)),
            tools(call("read_doc", {"doc_id": "D01"}, 6)),
            final("После OCR проверьте числа, даты и имена [D01:2]."),
        ])
        result = run(model)  # не должно бросать исключение
        self.assertEqual(result["stop_reason"], "final_answer")
        reads = tool_events(result)
        codes = [e["result"]["error"]["code"] for e in reads if e["status"] == "error"]
        self.assertEqual(codes, ["not_found", "bad_arguments", "bad_arguments", "bad_arguments", "unknown_tool"])
        d99 = reads[1]
        self.assertEqual(d99["result"]["error"]["doc_id"], "D99")
        self.assertEqual(set(d99["result"]), {"error"})  # нет lines/title — нет выдуманного содержимого
        self.assertEqual(result["missing_ids"], ["D99"])
        self.assertEqual(result["read_ids"], ["D01"])
        self.assertEqual(result["tool_errors"], 5)

    def test_a3_non_string_arguments_do_not_crash(self):
        bad = {"id": "c1", "type": "function", "function": {"name": "read_doc", "arguments": {"doc_id": "D01"}}}
        model = ScriptedModel([tools(call("search_docs", {"query": "OCR"})), tools(bad),
                               tools(call("read_doc", {"doc_id": "D01"}, 2)),
                               final("После OCR проверьте числа [D01:2].")])
        result = run(model)
        self.assertEqual(result["stop_reason"], "final_answer")
        self.assertEqual(result["tool_errors"], 1)
        ev = tool_events(result, "read_doc")[0]
        self.assertEqual(ev["status"], "error")
        self.assertEqual(ev["result"]["error"]["code"], "bad_arguments")

    def test_a3_answer_with_content_of_d99_rejected(self):
        model = ScriptedModel([
            tools(call("search_docs", {"query": "OCR"})),
            tools(call("read_doc", {"doc_id": "D99"}, 1)),
            final("Согласно D99, сканы проверять не нужно [D99:1]."),
            final("Согласно D99, сканы проверять не нужно [D99:1]."),
            final("Согласно D99, сканы проверять не нужно [D99:1]."),
        ])
        result = run(model)
        self.assertEqual(result["stop_reason"], "unverified_sources")
        self.assertIsNone(result["answer"])
        self.assertEqual(result["missing_ids"], ["D99"])

    # A4. Искусственный сбой read_doc — ошибка зафиксирована, ограниченное восстановление или понятный статус.
    def test_a4_read_doc_failure_recovered(self):
        failures = {"left": 1}

        def flaky_tool(name, arguments, docs):
            if name == "read_doc" and failures["left"]:
                failures["left"] -= 1
                raise RuntimeError("диск недоступен")
            return agent.run_allowed_tool(name, arguments, docs)

        model = ScriptedModel([
            tools(call("search_docs", {"query": "OCR"})),
            tools(call("read_doc", {"doc_id": "D01"}, 1)),
            tools(call("read_doc", {"doc_id": "D01"}, 2)),
            final("После OCR проверьте числа, даты и имена [D01:2]."),
        ])
        result = run(model, tool_fn=flaky_tool)
        reads = tool_events(result, "read_doc")
        self.assertEqual(reads[0]["status"], "error")
        self.assertEqual(reads[0]["result"]["error"]["code"], "tool_failure")
        self.assertIn("диск недоступен", reads[0]["result"]["error"]["message"])
        self.assertEqual(reads[1]["status"], "ok")
        self.assertEqual(result["tool_errors"], 1)
        self.assertEqual(result["stop_reason"], "final_answer")
        self.assertEqual(result["read_ids"], ["D01"])
        tool_msgs = [m for m in model.histories[2] if m["role"] == "tool"]
        self.assertIn("tool_failure", tool_msgs[-1]["content"])  # модель увидела ошибку

    def test_a4_read_doc_always_fails_clear_stop(self):
        def broken_tool(name, arguments, docs):
            if name == "read_doc":
                raise OSError("сбой чтения")
            return agent.run_allowed_tool(name, arguments, docs)

        answer = "После OCR проверьте числа [D01:2]."
        model = ScriptedModel([
            tools(call("search_docs", {"query": "OCR"})),
            tools(call("read_doc", {"doc_id": "D01"}, 1)),
            final(answer), final(answer), final(answer),
        ])
        result = run(model, tool_fn=broken_tool)
        self.assertEqual(result["stop_reason"], "unverified_sources")
        self.assertIsNone(result["answer"])
        self.assertEqual(result["read_ids"], [])
        self.assertEqual(result["tool_errors"], 1)
        self.assertEqual(model.calls, 5)

    # A5. Принудительно уменьшенный лимит — остановка на лимите, без бесконечного повтора.
    def test_a5_reduced_model_call_limit_stops(self):
        model = ScriptedModel([tools(call("search_docs", {"query": "OCR"}))], repeat_last=True)
        result = run(model, cfg=dict(CFG, max_model_calls=2))
        self.assertEqual(result["stop_reason"], "budget_exhausted")
        self.assertIsNone(result["answer"])
        self.assertEqual(model.calls, 2)
        self.assertEqual(result["model_calls"], 2)

    def test_a5_reduced_tool_call_limit_stops(self):
        model = ScriptedModel([tools(call("read_doc", {"doc_id": "D01"}))], repeat_last=True)
        result = run(model, cfg=dict(CFG, max_tool_calls=3))
        self.assertEqual(result["stop_reason"], "tool_budget_exhausted")
        self.assertIsNone(result["answer"])
        self.assertEqual(result["tool_calls"], 3)
        self.assertEqual(len(tool_events(result)), 3)

    def test_a5_reduced_limit_with_unverified_answers_no_answer(self):
        model = ScriptedModel([final("Ответ без чтения [D01:1].")], repeat_last=True)
        result = run(model, cfg=dict(CFG, max_model_calls=2))
        self.assertEqual(result["stop_reason"], "budget_exhausted")
        self.assertIsNone(result["answer"])
        self.assertEqual(model.calls, 2)


class TestReplayRegression(unittest.TestCase):
    def test_replay_regression(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "replay.json"
            proc = subprocess.run([sys.executable, str(ROOT / "agent.py"), "--replay", "--output", str(out)],
                                  capture_output=True, text=True, timeout=60, cwd=ROOT)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("stop_reason: final_answer", proc.stdout)
            result = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(result["stop_reason"], "final_answer")
        self.assertEqual(result["answer"], REPLAY_ANSWER_BEFORE)
        self.assertEqual((result["model_calls"], result["tool_calls"]), (4, 4))
        self.assertEqual(result["read_ids"], ["D01", "D02"])
        self.assertEqual((result["missing_ids"], result["tool_errors"]), ([], 0))
        self.assertTrue(all(e["status"] == "ok" for e in result["trace"] if e["event"] == "tool"))

    def test_replay_tool_interface_unchanged(self):
        names = [t["function"]["name"] for t in agent.TOOLS]
        self.assertEqual(names, ["search_docs", "read_doc"])
        self.assertEqual(agent.TOOLS[1]["function"]["parameters"]["required"], ["doc_id"])
        self.assertEqual(agent.TOOLS[0]["function"]["parameters"]["required"], ["query"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
