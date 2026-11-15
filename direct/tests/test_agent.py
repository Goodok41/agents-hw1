"""Тесты агента DemoDesk (A1-A5 из change-brief.md + регрессия --replay). Без сети, модель - заглушка."""
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import agent  # noqa: E402

_n = 0

def call(name, **args):
    global _n
    _n += 1
    return {"id": f"c{_n}", "type": "function", "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)}}

def raw_call(name, arguments):
    global _n
    _n += 1
    return {"id": f"c{_n}", "type": "function", "function": {"name": name, "arguments": arguments}}

def tools_reply(*calls):
    return {"role": "assistant", "content": None, "tool_calls": list(calls)}

def text_reply(text):
    return {"role": "assistant", "content": text}

class Stub:
    """Выдаёт заранее заданные ответы; после конца списка повторяет последний (или падает, если repeat=False)."""
    def __init__(self, replies, repeat=False):
        self.replies, self.repeat, self.calls = list(replies), repeat, 0
    def __call__(self, history, tools):
        self.calls += 1
        if self.calls <= len(self.replies):
            return self.replies[self.calls - 1], {}
        if self.repeat:
            return self.replies[-1], {}
        raise AssertionError("Модель вызвана больше, чем предусмотрено сценарием")

def run(replies, question="q", repeat=False, **cfg_over):
    cfg = {**agent.load_config(), **cfg_over}
    stub = Stub(replies, repeat)
    result = agent.run_agent(question, cfg, stub, "TEST", emit=lambda *_: None)
    return result, stub

def tool_events(result, name=None):
    return [e for e in result["trace"] if e["event"] == "tool" and (name is None or e["name"] == name)]

class TestA(unittest.TestCase):
    def test_a1_ocr_then_external_api(self):
        result, _ = run([
            tools_reply(call("search_docs", query="проверить после OCR и перед внешним API")),
            tools_reply(call("read_doc", doc_id="D01"), call("read_doc", doc_id="D02")),
            text_reply("После OCR проверьте числа, даты и имена (D01:2). Перед внешним API уберите персональные данные (D02:1)."),
        ], "Что проверить после OCR и перед внешним API?")
        self.assertEqual(result["stop_reason"], "final_answer")
        self.assertEqual(result["read_ids"], ["D01", "D02"])
        self.assertEqual(result["missing_ids"], [])
        self.assertEqual(result["tool_errors"], 0)
        self.assertIn("D01:2", result["answer"])
        self.assertIn("D02:1", result["answer"])
        found = {d["id"] for d in tool_events(result, "search_docs")[0]["result"]["documents"]}
        self.assertTrue({"D01", "D02"} <= found)
        self.assertTrue(all(e["status"] == "ok" for e in tool_events(result)))

    def test_a2_no_price_in_corpus(self):
        result, _ = run([
            tools_reply(call("search_docs", query="цена лицензия DemoDesk")),
            tools_reply(call("read_doc", doc_id="D03")),
            text_reply("В корпусе нет сведений о цене лицензии DemoDesk: тариф не указан (D03:3)."),
        ], "Сколько стоит лицензия DemoDesk?")
        self.assertEqual(result["stop_reason"], "final_answer")
        self.assertEqual(result["read_ids"], ["D03"])
        self.assertIn("нет сведений", result["answer"])
        self.assertNotRegex(result["answer"], r"\d+\s*(руб|₽|\$|USD|евро)")
        d03 = tool_events(result, "read_doc")[0]["result"]
        self.assertFalse(any("руб" in l["text"] for l in d03["lines"]))

    def test_a3_unknown_id_and_bad_arguments(self):
        result, _ = run([
            tools_reply(call("search_docs", query="прокси")),
            tools_reply(call("read_doc", doc_id="D07"), call("read_doc", doc_id="D99"),
                        raw_call("read_doc", "не json"),
                        call("read_doc", doc_id="D01", extra=1),
                        call("search_docs", query=""),
                        raw_call("run_shell", "{}")),
            text_reply("Документ D99 в корпусе отсутствует, сведений о настройке прокси нет."),
        ])
        self.assertEqual(result["stop_reason"], "final_answer")
        self.assertEqual(result["missing_ids"], ["D99"])
        self.assertEqual(result["read_ids"], ["D07"])
        self.assertEqual(result["tool_errors"], 5)
        events = tool_events(result)[2:]
        self.assertEqual([e["status"] for e in events], ["error"] * 5)
        self.assertEqual([e["result"]["error"]["code"] for e in events],
                         ["not_found", "bad_arguments", "bad_arguments", "bad_arguments", "unknown_tool"])
        self.assertEqual(events[0]["result"]["error"]["doc_id"], "D99")
        for e in events:
            self.assertNotIn("lines", e["result"])
            self.assertNotIn("title", e["result"])

    def test_a3_citing_unknown_id_is_not_issued(self):
        fake = text_reply("Прокси настраивается так (D99:1).")
        result, stub = run([tools_reply(call("search_docs", query="прокси")),
                            tools_reply(call("read_doc", doc_id="D99")), fake], repeat=True)
        self.assertEqual(result["stop_reason"], "unverified_sources")
        self.assertIsNone(result["answer"])
        self.assertEqual(result["missing_ids"], ["D99"])

    def test_a4_read_doc_failure_then_recovery(self):
        real = agent.run_allowed_tool
        state = {"failed": False}
        def flaky(name, arguments, docs):
            if name == "read_doc" and not state["failed"]:
                state["failed"] = True
                raise RuntimeError("искусственный сбой")
            return real(name, arguments, docs)
        with mock.patch.object(agent, "run_allowed_tool", flaky):
            result, _ = run([
                tools_reply(call("search_docs", query="скан OCR")),
                tools_reply(call("read_doc", doc_id="D01")),
                tools_reply(call("read_doc", doc_id="D01")),
                text_reply("После OCR проверьте числа, даты и имена (D01:2)."),
            ])
        self.assertEqual(result["stop_reason"], "final_answer")
        self.assertEqual(result["tool_errors"], 1)
        self.assertEqual(result["read_ids"], ["D01"])
        failed = tool_events(result, "read_doc")[0]
        self.assertEqual(failed["status"], "error")
        self.assertEqual(failed["result"]["error"]["code"], "tool_failure")

    def test_a4_persistent_failure_ends_with_clear_status(self):
        real = agent.run_allowed_tool
        def broken(name, arguments, docs):
            if name == "read_doc":
                raise RuntimeError("искусственный сбой")
            return real(name, arguments, docs)
        with mock.patch.object(agent, "run_allowed_tool", broken):
            result, _ = run([
                tools_reply(call("search_docs", query="скан OCR")),
                tools_reply(call("read_doc", doc_id="D01")),
                text_reply("После OCR проверьте числа (D01:2)."),
            ], repeat=True)
        self.assertEqual(result["stop_reason"], "unverified_sources")
        self.assertIsNone(result["answer"])
        self.assertEqual(result["read_ids"], [])
        self.assertEqual(result["tool_errors"], 1)

    def test_a5_model_call_limit(self):
        result, stub = run([tools_reply(call("search_docs", query="скан"))], repeat=True, max_model_calls=2)
        self.assertEqual(result["stop_reason"], "budget_exhausted")
        self.assertIsNone(result["answer"])
        self.assertEqual(stub.calls, 2)
        self.assertEqual(result["model_calls"], 2)

    def test_a5_tool_call_limit(self):
        result, stub = run([tools_reply(call("search_docs", query="скан"), call("search_docs", query="api"))],
                           repeat=True, max_tool_calls=3)
        self.assertEqual(result["stop_reason"], "tool_budget_exhausted")
        self.assertIsNone(result["answer"])
        self.assertLessEqual(result["tool_calls"], 3)
        self.assertEqual(stub.calls, 2)

class TestR4(unittest.TestCase):
    def test_at_most_two_remarks_with_concrete_ids(self):
        seen = []
        replies = [tools_reply(call("search_docs", query="скан")), text_reply("Ответ (D01:1).")]
        stub = Stub(replies, repeat=True)
        def model(history, tools):
            seen.append(list(history))
            return stub(history, tools)
        cfg = agent.load_config()
        result = agent.run_agent("q", cfg, model, "TEST", emit=lambda *_: None)
        self.assertEqual(result["stop_reason"], "unverified_sources")
        self.assertIsNone(result["answer"])
        remarks = [m for m in seen[-1] if m["role"] == "user" and m["content"].startswith("Проверка программы")]
        self.assertEqual(len(remarks), 2)
        self.assertTrue(all("D01" in m["content"] for m in remarks))

class TestRegression(unittest.TestCase):
    def test_replay_cli_unchanged(self):
        proc = subprocess.run([sys.executable, str(ROOT / "agent.py"), "--replay"], capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("stop_reason: final_answer", proc.stdout)
        self.assertIn("(D01:1-3)", proc.stdout)
        self.assertIn("(D02:1-2)", proc.stdout)

    def test_replay_run_agent(self):
        result = agent.run_agent(agent.QUESTION, agent.load_config(), agent.make_replay_model(), "REPLAY", emit=lambda *_: None)
        self.assertEqual(result["stop_reason"], "final_answer")
        self.assertEqual(result["model_calls"], 4)
        self.assertEqual(result["tool_calls"], 4)
        self.assertEqual(result["read_ids"], ["D01", "D02"])
        self.assertEqual(result["missing_ids"], [])
        self.assertEqual(result["tool_errors"], 0)
        self.assertEqual([e["error"] for e in result["trace"] if e["event"] == "validation"], ["unread_sources"])

    def test_tool_interface_unchanged(self):
        self.assertEqual([t["function"]["name"] for t in agent.TOOLS], ["search_docs", "read_doc"])

if __name__ == "__main__":
    unittest.main(verbosity=2)
