"""Тесты agent.py: заглушка модели, без сети. Запуск: python3 tests/test_agent.py"""
import io
import json
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import agent  # noqa: E402

CFG = {"max_model_calls": 6, "max_tool_calls": 12, "max_output_tokens": 350, "timeout_seconds": 30}


def call(name, args, idx):
    return {"id": f"c{idx}", "type": "function", "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)}}


def tools(*pairs):
    return {"role": "assistant", "content": None,
            "tool_calls": [call(n, a, i) for i, (n, a) in enumerate(pairs)]}


def final(text):
    return {"role": "assistant", "content": text}


class StubModel:
    """Отдаёт заранее заданные ответы; при исчерпании повторяет последний."""
    def __init__(self, replies):
        self.replies, self.calls, self.histories = list(replies), 0, []

    def __call__(self, history, tool_defs):
        self.histories.append([dict(m) for m in history])
        reply = self.replies[min(self.calls, len(self.replies) - 1)]
        self.calls += 1
        return json.loads(json.dumps(reply)), {}


def run(replies, cfg=CFG):
    model = StubModel(replies)
    result = agent.run_agent("вопрос", cfg, model, mode="TEST", emit=lambda *_: None)
    return result, model


def no_network(*a, **k):
    raise AssertionError("сеть в тестах запрещена")


@mock.patch.object(agent, "build_opener", no_network)
class TestAgent(unittest.TestCase):
    # A1 / R1: неизвестный doc_id
    def test_a1_unknown_doc_id_is_not_found_and_in_missing_ids(self):
        result, _ = run([
            tools(("search_docs", {"query": "прокси"})),
            tools(("read_doc", {"doc_id": "D99"}), ("read_doc", {"doc_id": "D07"})),
            final("Документа D99 в корпусе нет, настройка прокси не описана [D07:1-3]."),
        ])
        tool_events = [e for e in result["trace"] if e["event"] == "tool"]
        d99 = tool_events[1]
        self.assertEqual(d99["status"], "error")
        self.assertEqual(d99["result"]["error"]["code"], "not_found")
        self.assertEqual(d99["result"]["error"]["doc_id"], "D99")
        self.assertEqual(result["missing_ids"], ["D99"])
        self.assertEqual(result["read_ids"], ["D07"])
        self.assertEqual(result["stop_reason"], "final_answer")

    def test_a1_direct_tool_call(self):
        res = agent.run_allowed_tool("read_doc", '{"doc_id": "D42"}', agent.load_docs())
        self.assertEqual(res["error"]["code"], "not_found")

    # A2 / R2: исключение внутри инструмента
    def test_a2_tool_exception_becomes_tool_failure_and_loop_continues(self):
        real = agent.run_allowed_tool

        def flaky(name, arguments, docs):
            if name == "read_doc" and "D01" in arguments:
                raise RuntimeError("диск недоступен")
            return real(name, arguments, docs)

        with mock.patch.object(agent, "run_allowed_tool", flaky):
            result, model = run([
                tools(("search_docs", {"query": "скан"})),
                tools(("read_doc", {"doc_id": "D01"})),
                tools(("read_doc", {"doc_id": "D06"})),
                final("Для сканов актуальна инструкция от 2026-10-20 [D06:2]."),
            ])
        failed = [e for e in result["trace"] if e["event"] == "tool" and e["status"] == "error"]
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0]["result"]["error"]["code"], "tool_failure")
        self.assertNotIn("диск", json.dumps(failed[0]["result"], ensure_ascii=False))  # детали исключения не утекают
        self.assertEqual(result["stop_reason"], "final_answer")
        self.assertEqual(model.calls, 4)
        self.assertEqual(result["tool_errors"], 1)
        self.assertEqual(result["read_ids"], ["D06"])
        self.assertEqual(result["missing_ids"], [])  # сбой — не отсутствие документа

    def test_a2_tool_failure_respects_limits(self):
        with mock.patch.object(agent, "run_allowed_tool", side_effect=ValueError("boom")):
            result, _ = run([tools(("search_docs", {"query": "скан"}))], cfg={**CFG, "max_model_calls": 3})
        self.assertEqual(result["stop_reason"], "budget_exhausted")
        self.assertIsNone(result["answer"])
        self.assertEqual(result["tool_errors"], 3)

    # A3 / R4: проверка источников
    def test_a3_remark_names_unread_ids_then_success(self):
        result, model = run([
            tools(("search_docs", {"query": "скан"})),
            tools(("read_doc", {"doc_id": "D01"})),
            final("Проверьте числа [D01:2] и уберите персональные данные [D02:1]."),
            tools(("read_doc", {"doc_id": "D02"})),
            final("Проверьте числа [D01:2] и уберите персональные данные [D02:1]."),
        ])
        self.assertEqual(result["stop_reason"], "final_answer")
        remark = model.histories[3][-1]
        self.assertEqual(remark["role"], "user")
        self.assertIn("D02", remark["content"])
        self.assertNotIn("D01", remark["content"])
        self.assertEqual(result["read_ids"], ["D01", "D02"])

    def test_a3_at_most_two_remarks_then_unverified_sources(self):
        bad = final("Ответ по источнику [D03:1] и [D05:2].")
        result, model = run([
            tools(("search_docs", {"query": "скан"})),
            tools(("read_doc", {"doc_id": "D01"})),
            bad, bad, bad, bad,
        ])
        self.assertEqual(result["stop_reason"], "unverified_sources")
        self.assertIsNone(result["answer"])
        self.assertEqual(model.calls, 5)  # 2 инструмента + 3 ответа: два замечания, третий — стоп
        remarks = [m for m in model.histories[-1] if m["role"] == "user" and m["content"].startswith("Проверка программы")]
        self.assertEqual(len(remarks), 2)
        self.assertTrue(all("D03" in m["content"] and "D05" in m["content"] for m in remarks))

    def test_a3_citation_of_missing_doc_is_rejected(self):
        bad = final("Настройка прокси описана в [D99:1].")
        result, _ = run([
            tools(("search_docs", {"query": "прокси"})),
            tools(("read_doc", {"doc_id": "D99"}), ("read_doc", {"doc_id": "D07"})),
            bad, bad, bad,
        ])
        self.assertEqual(result["stop_reason"], "unverified_sources")
        self.assertIsNone(result["answer"])
        self.assertEqual(result["missing_ids"], ["D99"])

    def test_a3_citation_formats(self):
        self.assertEqual(agent.cited_ids_in("x [D01:1-3; D02:1-2] y (D03, D04) z (D05)"),
                         {"D01", "D02", "D03", "D04", "D05"})
        self.assertEqual(agent.cited_ids_in("Документа D99 нет (документ D98 отсутствует)."), set())

    # A4 / R5: лимиты
    def test_a4_model_budget_exhausted(self):
        result, model = run([tools(("search_docs", {"query": "скан"}))], cfg={**CFG, "max_model_calls": 2, "max_tool_calls": 16})
        self.assertEqual(result["stop_reason"], "budget_exhausted")
        self.assertIsNone(result["answer"])
        self.assertEqual(model.calls, 2)

    def test_a4_tool_budget_exhausted(self):
        result, _ = run([
            tools(("search_docs", {"query": "скан"}), ("search_docs", {"query": "API"})),
            tools(("read_doc", {"doc_id": "D01"}), ("read_doc", {"doc_id": "D02"})),
        ], cfg={**CFG, "max_tool_calls": 3})
        self.assertEqual(result["stop_reason"], "tool_budget_exhausted")
        self.assertIsNone(result["answer"])
        self.assertEqual(result["tool_calls"], 2)

    def test_a4_limits_not_relaxed_by_remarks(self):
        bad = final("Ответ [D02:1].")
        result, _ = run([tools(("search_docs", {"query": "скан"})), bad, bad],
                        cfg={**CFG, "max_model_calls": 3})
        self.assertEqual(result["stop_reason"], "budget_exhausted")
        self.assertIsNone(result["answer"])

    # A5 / R3: журнал и итоговые поля
    def test_a5_trace_status_and_summary_fields(self):
        result, _ = run([
            tools(("search_docs", {"query": "скан"}), ("unknown_tool", {}), ("read_doc", {"doc_id": ""})),
            tools(("read_doc", {"doc_id": "D06"}), ("read_doc", {"doc_id": "D01"}), ("read_doc", {"doc_id": "D77"})),
            final("Проверьте числа [D01:2]; актуальна редакция [D06:2]."),
        ])
        tool_events = [e for e in result["trace"] if e["event"] == "tool"]
        self.assertTrue(all(e["status"] in ("ok", "error") for e in tool_events))
        self.assertEqual([e["status"] for e in tool_events], ["ok", "error", "error", "ok", "ok", "error"])
        self.assertEqual(result["read_ids"], ["D01", "D06"])  # по возрастанию
        self.assertEqual(result["missing_ids"], ["D77"])
        self.assertEqual(result["tool_errors"], 3)
        self.assertEqual(result["stop_reason"], "final_answer")

    def test_a5_summary_fields_present_on_every_stop_reason(self):
        results = [
            run([tools(("search_docs", {"query": "скан"}))], cfg={**CFG, "max_model_calls": 1})[0],
            run([tools(*[("search_docs", {"query": "скан"})] * 13)])[0],
            run([tools(("search_docs", {"query": "скан"})), final("[D09:1]")])[0],
        ]
        self.assertEqual([r["stop_reason"] for r in results], ["budget_exhausted", "tool_budget_exhausted", "unverified_sources"])
        for r in results:
            self.assertEqual({"read_ids", "missing_ids", "tool_errors"} - set(r), set())

    # R6: интерфейс инструментов и регрессия --replay
    def test_r6_tool_interface_unchanged(self):
        self.assertEqual([t["function"]["name"] for t in agent.TOOLS], ["search_docs", "read_doc"])
        self.assertEqual(agent.TOOLS[0]["function"]["parameters"]["required"], ["query"])
        self.assertEqual(agent.TOOLS[1]["function"]["parameters"]["required"], ["doc_id"])
        ok = agent.run_allowed_tool("read_doc", '{"doc_id": "D01"}', agent.load_docs())
        self.assertEqual(set(ok), {"id", "title", "version", "lines"})

    def test_replay_regression_run_agent(self):
        result = agent.run_agent(agent.QUESTION, agent.load_config(), agent.make_replay_model(), "REPLAY", emit=lambda *_: None)
        self.assertEqual(result["stop_reason"], "final_answer")
        self.assertEqual(result["model_calls"], 4)
        self.assertEqual(result["tool_calls"], 4)
        self.assertEqual(result["read_ids"], ["D01", "D02"])
        self.assertEqual(result["missing_ids"], [])
        self.assertEqual(result["tool_errors"], 0)
        self.assertIn("(D01:1-3)", result["answer"])
        self.assertEqual([e["error"] for e in result["trace"] if e["event"] == "validation"], ["unread_sources"])

    def test_replay_regression_cli(self):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(sys, "argv", ["agent.py", "--replay"]), redirect_stdout(out), redirect_stderr(err):
            code = agent.main()
        self.assertEqual(code, 0, err.getvalue())
        self.assertIn("stop_reason: final_answer", out.getvalue())
        self.assertIn("(D02:1-2)", out.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
