"""Тесты по таблице A1–A5 из change-brief.md плюс регрессия --replay.

Без сети: модель — контролируемая заглушка, живой API не вызывается.
Запуск: python3 tests/test_agent.py
"""
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import agent  # noqa: E402

CFG = {"api_base": "https://ai.api.cloud.yandex.net/v1", "model": "gpt://test/aliceai-llm-flash",
       "max_model_calls": 6, "max_tool_calls": 12, "max_output_tokens": 350, "timeout_seconds": 30}


def call(name, args, idx=[0]):
    idx[0] += 1
    arguments = args if isinstance(args, str) else json.dumps(args, ensure_ascii=False)
    return {"id": f"c{idx[0]}", "type": "function", "function": {"name": name, "arguments": arguments}}


def tools(*calls):
    return {"role": "assistant", "content": None, "tool_calls": list(calls)}


def final(text):
    return {"role": "assistant", "content": text}


class ScriptedModel:
    """Заглушка модели: отдаёт заранее заданные ответы и запоминает историю каждого вызова."""

    def __init__(self, replies, repeat_last=False):
        self.replies, self.repeat_last, self.calls = list(replies), repeat_last, []

    def __call__(self, history, tool_defs):
        self.calls.append(json.loads(json.dumps(history, ensure_ascii=False)))
        i = len(self.calls) - 1
        if i >= len(self.replies):
            if not self.repeat_last:
                raise AssertionError("Модель вызвана больше раз, чем предусмотрено сценарием")
            i = len(self.replies) - 1
        return json.loads(json.dumps(self.replies[i], ensure_ascii=False)), {}


def run(model, cfg=None, question="вопрос"):
    lines = []
    result = agent.run_agent(question, dict(cfg or CFG), model, mode="TEST", emit=lines.append)
    return result, lines


def tool_events(result):
    return [e for e in result["trace"] if e["event"] == "tool"]


class TestA1to5(unittest.TestCase):
    # A1. «Что проверить после OCR и перед внешним API?» — поиск + чтение, ответ подтверждён D01/D02.
    def test_a1_search_read_answer_confirmed_by_d01_d02(self):
        model = ScriptedModel([
            tools(call("search_docs", {"query": "OCR проверка"}), call("search_docs", {"query": "внешний API"})),
            tools(call("read_doc", {"doc_id": "D01"}), call("read_doc", {"doc_id": "D02"})),
            final("После OCR проверьте числа, даты и имена [D01:2]. Перед внешним API уберите "
                  "персональные сведения и проверьте разрешение [D02:1-2]."),
        ])
        result, _ = run(model, question="Что проверить после OCR и перед внешним API?")
        self.assertEqual(result["stop_reason"], "final_answer")
        self.assertIsNotNone(result["answer"])
        self.assertEqual(result["read_ids"], ["D01", "D02"])
        self.assertEqual(result["missing_ids"], [])
        self.assertEqual(result["tool_errors"], 0)
        names = [e["name"] for e in tool_events(result)]
        self.assertIn("search_docs", names)
        self.assertIn("read_doc", names)
        self.assertTrue(all(e["status"] == "ok" for e in tool_events(result)))
        # Реальное содержимое D01 действительно попало модели.
        last_history = json.dumps(model.calls[-1], ensure_ascii=False)
        self.assertIn("После OCR проверьте числа, даты и имена", last_history)

    def test_a1_answer_citing_unread_doc_is_rejected_then_accepted_after_read(self):
        model = ScriptedModel([
            tools(call("search_docs", {"query": "OCR внешний API"})),
            final("Проверьте числа [D01:2] и уберите персональные данные [D02:1]."),
            tools(call("read_doc", {"doc_id": "D01"}), call("read_doc", {"doc_id": "D02"})),
            final("Проверьте числа [D01:2] и уберите персональные данные [D02:1]."),
        ])
        result, _ = run(model)
        self.assertEqual(result["stop_reason"], "final_answer")
        self.assertEqual(result["read_ids"], ["D01", "D02"])
        validations = [e for e in result["trace"] if e["event"] == "validation"]
        self.assertEqual(len(validations), 1)
        self.assertEqual(validations[0]["ids"], ["D01", "D02"])
        remark = model.calls[2][-1]["content"]
        self.assertIn("D01", remark)
        self.assertIn("D02", remark)

    # A2. «Сколько стоит лицензия DemoDesk?» — цены нет, агент не выдумывает тариф.
    def test_a2_license_price_absent_answer_reports_no_data(self):
        model = ScriptedModel([
            tools(call("search_docs", {"query": "цена лицензии тариф"})),
            tools(call("read_doc", {"doc_id": "D03"})),
            final("В учебном корпусе нет сведений о цене лицензии DemoDesk: тариф и цена не указаны [D03:3]."),
        ])
        result, _ = run(model, question="Сколько стоит лицензия DemoDesk?")
        search = tool_events(result)[0]["result"]
        self.assertIn("D03", [d["id"] for d in search["documents"]])
        d03 = tool_events(result)[1]["result"]
        self.assertTrue(any("цена лицензии в корпусе не указаны" in l["text"] for l in d03["lines"]))
        self.assertEqual(result["stop_reason"], "final_answer")
        self.assertEqual(result["read_ids"], ["D03"])
        self.assertRegex(result["answer"], r"нет сведений|не указан")
        self.assertIsNone(re.search(r"\d+\s*(₽|руб|\$|usd|eur)", result["answer"], re.I))

    def test_a2_invented_tariff_with_unread_source_is_not_returned(self):
        invented = final("Лицензия DemoDesk стоит 990 руб. в месяц [D07:1].")
        model = ScriptedModel([
            tools(call("search_docs", {"query": "цена лицензии"})),
            tools(call("read_doc", {"doc_id": "D03"})),
            invented, invented, invented,
        ])
        result, _ = run(model, question="Сколько стоит лицензия DemoDesk?")
        self.assertEqual(result["stop_reason"], "unverified_sources")
        self.assertIsNone(result["answer"])
        self.assertEqual(len(model.calls), 5)  # 2 замечания, третий ответ — остановка
        remarks = [h[-1]["content"] for h in model.calls[3:5]]
        self.assertTrue(all("D07" in r for r in remarks))

    # A3. Неизвестный ID D99 и неверные аргументы — структурированная ошибка без падения.
    def test_a3_unknown_d99_and_bad_arguments_structured_errors(self):
        model = ScriptedModel([
            tools(call("search_docs", {"query": "скан"})),
            tools(call("read_doc", {"doc_id": "D99"}),
                  call("read_doc", "это не JSON"),
                  call("read_doc", {"id": "D01"}),
                  call("search_docs", {"query": ""}),
                  call("delete_doc", {"doc_id": "D01"})),
            tools(call("read_doc", {"doc_id": "D01"})),
            final("Документ D99 не найден в корпусе. После OCR проверьте числа [D01:2]."),
        ])
        result, _ = run(model)
        events = tool_events(result)
        codes = [e["result"].get("error", {}).get("code") for e in events[1:6]]
        self.assertEqual(codes, ["not_found", "bad_arguments", "bad_arguments", "bad_arguments", "unknown_tool"])
        self.assertTrue(all(e["status"] == "error" for e in events[1:6]))
        self.assertEqual(events[1]["result"]["error"]["doc_id"], "D99")
        self.assertNotIn("lines", events[1]["result"])  # нет выдуманного содержимого D99
        self.assertEqual(result["missing_ids"], ["D99"])
        self.assertEqual(result["tool_errors"], 5)
        self.assertEqual(result["read_ids"], ["D01"])
        self.assertEqual(result["stop_reason"], "final_answer")
        # Ошибки дошли до модели как результаты инструментов.
        tool_msgs = [m for m in model.calls[2] if m["role"] == "tool"]
        self.assertIn("not_found", tool_msgs[1]["content"])

    def test_a3_citation_of_missing_d99_is_rejected(self):
        cite = final("По документу D99: лицензия бесплатна [D99:1].")
        model = ScriptedModel([
            tools(call("search_docs", {"query": "лицензия"})),
            tools(call("read_doc", {"doc_id": "D99"})),
            cite, cite, cite,
        ])
        result, _ = run(model)
        self.assertEqual(result["stop_reason"], "unverified_sources")
        self.assertIsNone(result["answer"])
        self.assertEqual(result["missing_ids"], ["D99"])
        self.assertNotIn("D99", result["read_ids"])

    # A4. Искусственный сбой read_doc — ошибка зафиксирована, ограниченное восстановление.
    def test_a4_read_doc_failure_recorded_and_agent_recovers(self):
        real = agent.run_allowed_tool
        state = {"failed": False}

        def flaky(name, arguments, docs):
            if name == "read_doc" and not state["failed"]:
                state["failed"] = True
                raise RuntimeError("диск недоступен")
            return real(name, arguments, docs)

        model = ScriptedModel([
            tools(call("search_docs", {"query": "скан"})),
            tools(call("read_doc", {"doc_id": "D01"})),
            tools(call("read_doc", {"doc_id": "D01"})),
            final("После OCR проверьте числа, даты и имена [D01:2]."),
        ])
        with mock.patch.object(agent, "run_allowed_tool", side_effect=flaky):
            result, _ = run(model)
        failed = tool_events(result)[1]
        self.assertEqual(failed["status"], "error")
        self.assertEqual(failed["result"]["error"]["code"], "tool_failure")
        self.assertEqual(result["tool_errors"], 1)
        self.assertEqual(result["stop_reason"], "final_answer")
        self.assertEqual(result["read_ids"], ["D01"])

    def test_a4_persistent_read_doc_failure_stops_with_clear_status(self):
        real = agent.run_allowed_tool

        def broken(name, arguments, docs):
            if name == "read_doc":
                raise OSError("сбой чтения")
            return real(name, arguments, docs)

        model = ScriptedModel([tools(call("search_docs", {"query": "скан"})),
                               tools(call("read_doc", {"doc_id": "D01"}))], repeat_last=True)
        cfg = dict(CFG, max_model_calls=8, max_tool_calls=4)
        with mock.patch.object(agent, "run_allowed_tool", side_effect=broken):
            result, _ = run(model, cfg)
        self.assertEqual(result["stop_reason"], "tool_budget_exhausted")
        self.assertIsNone(result["answer"])
        self.assertEqual(result["tool_calls"], 4)
        self.assertEqual(result["tool_errors"], 3)
        self.assertEqual(result["read_ids"], [])
        self.assertTrue(all(e["result"]["error"]["code"] == "tool_failure"
                            for e in tool_events(result) if e["name"] == "read_doc"))

    # A5. Принудительно уменьшенный лимит вызовов — остановка, нет финального ответа.
    def test_a5_model_call_limit_stops_loop(self):
        model = ScriptedModel([tools(call("search_docs", {"query": "скан"}))], repeat_last=True)
        result, _ = run(model, dict(CFG, max_model_calls=2))
        self.assertEqual(result["stop_reason"], "budget_exhausted")
        self.assertIsNone(result["answer"])
        self.assertEqual(result["model_calls"], 2)
        self.assertEqual(len(model.calls), 2)

    def test_a5_tool_call_limit_stops_loop(self):
        model = ScriptedModel([tools(call("search_docs", {"query": "скан"}),
                                     call("search_docs", {"query": "API"}))], repeat_last=True)
        result, _ = run(model, dict(CFG, max_model_calls=8, max_tool_calls=3))
        self.assertEqual(result["stop_reason"], "tool_budget_exhausted")
        self.assertIsNone(result["answer"])
        self.assertLessEqual(result["tool_calls"], 3)
        self.assertEqual(len(model.calls), 2)

    def test_a5_unverified_answer_loop_is_bounded(self):
        model = ScriptedModel([final("Ответ без чтения [D01:1].")], repeat_last=True)
        result, _ = run(model, dict(CFG, max_model_calls=8))
        self.assertEqual(result["stop_reason"], "unverified_sources")
        self.assertIsNone(result["answer"])
        self.assertEqual(len(model.calls), 3)  # 1 ответ + 2 замечания, без бесконечного повтора


class TestReplayRegression(unittest.TestCase):
    def test_replay_run_agent_same_result(self):
        result, lines = run(agent.make_replay_model(), agent.load_config(), question=agent.QUESTION)
        self.assertEqual(result["stop_reason"], "final_answer")
        self.assertEqual(result["model_calls"], 4)
        self.assertEqual(result["tool_calls"], 4)
        self.assertEqual(result["answer"], agent.REPLAY_RESPONSES[3]["content"])
        self.assertEqual(result["read_ids"], ["D01", "D02"])
        self.assertEqual(result["missing_ids"], [])
        self.assertEqual(result["tool_errors"], 0)
        self.assertEqual(sum(e["event"] == "validation" for e in result["trace"]), 1)

    def test_replay_cli(self):
        proc = subprocess.run([sys.executable, str(ROOT / "agent.py"), "--replay"],
                              capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("stop_reason: final_answer", proc.stdout)
        self.assertIn("read_ids: ['D01', 'D02']", proc.stdout)
        self.assertIn("(D01:1-3)", proc.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
