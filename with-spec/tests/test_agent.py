"""Тесты агента DemoDesk: без сети, модель заменена заглушкой."""
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import agent  # noqa: E402

_n = [0]


def tc(name, args):
    _n[0] += 1
    return {"id": f"c{_n[0]}", "type": "function",
            "function": {"name": name, "arguments": args if isinstance(args, str) else json.dumps(args, ensure_ascii=False)}}


def calls(*items):
    return {"role": "assistant", "content": None, "tool_calls": list(items)}


def say(text):
    return {"role": "assistant", "content": text}


def stub(replies, repeat_last=False):
    """Заглушка модели: отдаёт заранее заданные ответы, запоминает историю."""
    state = {"i": 0, "histories": []}

    def model(history, tools):
        state["histories"].append([dict(m) for m in history])
        i = state["i"]
        if i >= len(replies):
            if not repeat_last:
                raise AssertionError("модель вызвана больше, чем задано сценарием")
            i = len(replies) - 1
        state["i"] += 1
        return replies[i], {}
    model.state = state
    return model


def cfg(**over):
    c = agent.load_config()
    c.update(over)
    return c


def run(question, model, **over):
    return agent.run_agent(question, cfg(**over), model, "TEST", emit=lambda *_: None)


class AgentTests(unittest.TestCase):
    def test_a1_ocr_and_external_api_confirmed_by_d01_d02(self):
        model = stub([
            calls(tc("search_docs", {"query": "OCR проверка"}), tc("search_docs", {"query": "внешний API"})),
            calls(tc("read_doc", {"doc_id": "D01"}), tc("read_doc", {"doc_id": "D02"})),
            say("После OCR проверьте числа, даты и имена (D01:2). Перед внешним API уберите персональные данные (D02:1)."),
        ])
        r = run("Что проверить после OCR и перед внешним API?", model)
        self.assertEqual(r["stop_reason"], "final_answer")
        self.assertEqual(r["read_ids"], ["D01", "D02"])
        self.assertEqual(r["missing_ids"], [])
        self.assertEqual(r["tool_errors"], 0)
        tools = [e for e in r["trace"] if e["event"] == "tool"]
        self.assertEqual([e["name"] for e in tools], ["search_docs", "search_docs", "read_doc", "read_doc"])
        self.assertTrue(all(e["status"] == "ok" for e in tools))
        self.assertIn("D01", r["answer"])
        self.assertIn("D02", r["answer"])

    def test_a2_license_price_absent_not_invented(self):
        model = stub([
            calls(tc("search_docs", {"query": "лицензия DemoDesk цена"})),
            calls(tc("read_doc", {"doc_id": "D03"})),
            say("В корпусе нет сведений о цене лицензии DemoDesk: тариф не указан (D03:3)."),
        ])
        r = run("Сколько стоит лицензия DemoDesk?", model)
        self.assertEqual(r["stop_reason"], "final_answer")
        self.assertEqual(r["read_ids"], ["D03"])
        self.assertIn("нет сведений", r["answer"])
        self.assertNotRegex(r["answer"], r"\d+\s*(руб|₽|\$|USD|eur)")
        self.assertEqual(sorted(set(__import__("re").findall(r"D\d{2}", r["answer"]))), ["D03"])

    def test_a3_unknown_id_and_bad_arguments_structured_errors(self):
        model = stub([
            calls(tc("read_doc", {"doc_id": "D99"}), tc("read_doc", "не json"),
                  tc("search_docs", {"query": "x", "extra": 1}), tc("shell", {"cmd": "ls"})),
            say("Документа D99 в корпусе нет, сведений о нём нет."),
        ])
        r = run("Что в D99?", model)
        tools = [e for e in r["trace"] if e["event"] == "tool"]
        codes = [e["result"]["error"]["code"] for e in tools]
        self.assertEqual(codes, ["not_found", "bad_arguments", "bad_arguments", "unknown_tool"])
        self.assertTrue(all(e["status"] == "error" for e in tools))
        self.assertNotIn("lines", tools[0]["result"])
        self.assertNotIn("title", tools[0]["result"])
        self.assertEqual(r["missing_ids"], ["D99"])
        self.assertEqual(r["read_ids"], [])
        self.assertEqual(r["tool_errors"], 4)
        self.assertEqual(r["stop_reason"], "final_answer")  # процесс не упал

    def test_a4_read_doc_failure_is_recorded_and_agent_recovers(self):
        real = agent.run_allowed_tool
        failed = []

        def flaky(name, arguments, docs):
            if name == "read_doc" and not failed:
                failed.append(1)
                raise RuntimeError("искусственный сбой")
            return real(name, arguments, docs)

        model = stub([
            calls(tc("search_docs", {"query": "OCR скан"})),
            calls(tc("read_doc", {"doc_id": "D01"})),
            calls(tc("read_doc", {"doc_id": "D01"})),
            say("После OCR проверьте числа, даты и имена (D01:2)."),
        ])
        with mock.patch.object(agent, "run_allowed_tool", flaky):
            r = run("Что проверить после OCR?", model)
        errs = [e for e in r["trace"] if e["event"] == "tool" and e["status"] == "error"]
        self.assertEqual(len(errs), 1)
        self.assertEqual(errs[0]["result"]["error"]["code"], "tool_failure")
        self.assertEqual(r["tool_errors"], 1)
        self.assertEqual(r["stop_reason"], "final_answer")
        self.assertEqual(r["read_ids"], ["D01"])

    def test_a4_persistent_failure_ends_with_clear_status(self):
        def broken(name, arguments, docs):
            raise RuntimeError("сбой")

        model = stub([calls(tc("read_doc", {"doc_id": "D01"}))], repeat_last=True)
        with mock.patch.object(agent, "run_allowed_tool", broken):
            r = run("Что в D01?", model)
        self.assertIn(r["stop_reason"], {"budget_exhausted", "tool_budget_exhausted"})
        self.assertIsNone(r["answer"])
        self.assertGreaterEqual(r["tool_errors"], 1)

    def test_a5_reduced_limits_stop_loop_without_answer(self):
        model = stub([calls(tc("search_docs", {"query": "скан"}))], repeat_last=True)
        r = run("Вопрос", model, max_model_calls=2, max_tool_calls=1)
        self.assertEqual(r["stop_reason"], "tool_budget_exhausted")
        self.assertIsNone(r["answer"])
        self.assertLessEqual(r["model_calls"], 2)
        self.assertLessEqual(r["tool_calls"], 1)

        model = stub([calls(tc("search_docs", {"query": "скан"}))], repeat_last=True)
        r = run("Вопрос", model, max_model_calls=2, max_tool_calls=12)
        self.assertEqual(r["stop_reason"], "budget_exhausted")
        self.assertIsNone(r["answer"])
        self.assertEqual(model.state["i"], 2)

    def test_r4_notice_names_ids_then_unverified_sources_after_two(self):
        bad = say("Ответ (D05:1).")
        model = stub([calls(tc("search_docs", {"query": "скан"})), bad, bad, bad])
        r = run("Вопрос", model)
        self.assertEqual(r["stop_reason"], "unverified_sources")
        self.assertIsNone(r["answer"])
        notices = [e for e in r["trace"] if e["event"] == "validation" and e["error"] == "unread_sources"]
        self.assertEqual(len(notices), 2)
        last = model.state["histories"][-1][-1]
        self.assertIn("D05", last["content"])

    def test_regression_replay_cli_works_as_before(self):
        p = subprocess.run([sys.executable, str(ROOT / "agent.py"), "--replay"], capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("stop_reason: final_answer", p.stdout)
        self.assertIn("D01:1-3", p.stdout)
        self.assertIn("D02:1-2", p.stdout)

    def test_regression_replay_run_agent_and_tool_interface(self):
        r = agent.run_agent(agent.QUESTION, agent.load_config(), agent.make_replay_model(), "REPLAY", emit=lambda *_: None)
        self.assertEqual(r["stop_reason"], "final_answer")
        self.assertEqual(r["read_ids"], ["D01", "D02"])
        self.assertEqual([t["function"]["name"] for t in agent.TOOLS], ["search_docs", "read_doc"])


if __name__ == "__main__":
    unittest.main()
