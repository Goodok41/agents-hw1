"""A1-A5 из ДЗ1 (вариант C). Модель и сбои инструментов заменены контролируемыми заглушками.
Живая модель НЕ используется: тесты проверяют программу (цикл, проверки, журнал), а не качество модели."""
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import agent  # noqa: E402

CFG = agent.load_config()
_n = 0

def call(name, **args):
    global _n
    _n += 1
    raw = args.pop("_raw", None)
    return {"id": f"call_t{_n}", "type": "function",
            "function": {"name": name, "arguments": raw if raw is not None else json.dumps(args, ensure_ascii=False)}}

def tools(*calls):
    return {"role": "assistant", "content": None, "tool_calls": list(calls)}

def text(s):
    return {"role": "assistant", "content": s}

class Script:
    """Заглушка модели: отдаёт заранее заданные ответы и запоминает историю."""
    def __init__(self, *replies, repeat_last=False):
        self.replies, self.repeat_last, self.histories = list(replies), repeat_last, []
    def __call__(self, history, tool_defs):
        self.histories.append(list(history))
        if len(self.histories) > len(self.replies):
            if self.repeat_last:
                return self.replies[-1], {}
            raise AssertionError("заглушка исчерпана")
        return self.replies[len(self.histories) - 1], {}

def run(model, cfg=None):
    return agent.run_agent("тест", cfg or CFG, model, "STUB", emit=lambda *_: None)

class A1_SearchAndRead(unittest.TestCase):
    def test_answer_confirmed_by_read_docs(self):
        r = run(Script(tools(call("search_docs", query="скан OCR внешний API")),
                       tools(call("read_doc", doc_id="D01"), call("read_doc", doc_id="D02")),
                       text("После OCR проверьте данные [D01:1-2]. Перед API уберите персональные данные [D02:1-2].")))
        self.assertEqual(r["stop_reason"], "final_answer")
        self.assertEqual(r["read_ids"], ["D01", "D02"])
        self.assertEqual((r["missing_ids"], r["tool_errors"]), ([], 0))
        self.assertTrue(all(e["status"] == "ok" for e in r["trace"] if e["event"] == "tool"))

    def test_snippet_only_answer_is_sent_back_then_accepted(self):
        m = Script(tools(call("search_docs", query="скан OCR")),
                   text("Проверьте числа после OCR [D01:1-2]."),
                   tools(call("read_doc", doc_id="D01")),
                   text("Проверьте числа после OCR [D01:1-2]."))
        r = run(m)
        self.assertEqual(r["stop_reason"], "final_answer")
        self.assertIn("D01", m.histories[2][-1]["content"])

class A2_NoAnswerInCorpus(unittest.TestCase):
    def test_price_absent_in_d03(self):
        r = run(Script(tools(call("search_docs", query="цена лицензия DemoDesk")),
                       tools(call("read_doc", doc_id="D03")),
                       text("В корпусе нет сведений о цене лицензии DemoDesk [D03:1-4].")))
        self.assertEqual(r["stop_reason"], "final_answer")
        self.assertEqual(r["read_ids"], ["D03"])
        self.assertIn("нет сведений", r["answer"])
        doc = next(d for d in agent.load_docs() if d["id"] == "D03")
        self.assertNotRegex(doc["text"], r"\d+\s*(руб|₽|\$|USD)")  # в самом корпусе цены нет

class A3_UnknownIdAndBadArguments(unittest.TestCase):
    def test_structured_errors_without_crash(self):
        r = run(Script(tools(call("search_docs", query="прокси")),
                       tools(call("read_doc", doc_id="D99"), call("read_doc", _raw="не json"),
                             call("read_doc", wrong="D01"), call("shell", cmd="ls"), call("read_doc", doc_id="D07")),
                       text("Документа D99 в корпусе нет, сведений о прокси нет [D07:1-3].")))
        results = [e["result"] for e in r["trace"] if e["event"] == "tool"][1:]
        self.assertEqual([x.get("error", {}).get("code") for x in results], ["not_found", "bad_arguments", "bad_arguments", "unknown_tool", None])
        self.assertEqual(r["missing_ids"], ["D99"])
        self.assertEqual((r["stop_reason"], r["tool_errors"], r["read_ids"]), ("final_answer", 4, ["D07"]))
        self.assertTrue(all("lines" not in x for x in results[:4]))  # содержимое D99 не выдумано

    def test_citing_missing_doc_is_never_accepted(self):
        lie = text("Прокси настраивается так [D99:1-2].")
        r = run(Script(tools(call("search_docs", query="прокси")), tools(call("read_doc", doc_id="D99")), lie, lie, lie))
        self.assertEqual((r["stop_reason"], r["answer"], r["missing_ids"]), ("unverified_sources", None, ["D99"]))

class A4_ToolFailure(unittest.TestCase):
    def test_failure_is_logged_and_agent_recovers(self):
        real, state = agent.run_allowed_tool, {"n": 0}
        def flaky(name, arguments, docs):
            if name == "read_doc":
                state["n"] += 1
                if state["n"] == 1:
                    raise RuntimeError("секретный-ключ-не-должен-попасть-в-журнал")
            return real(name, arguments, docs)
        with mock.patch.object(agent, "run_allowed_tool", flaky):
            r = run(Script(tools(call("search_docs", query="скан")), tools(call("read_doc", doc_id="D01")),
                           tools(call("read_doc", doc_id="D01")), text("После OCR проверьте данные [D01:1-2].")))
        self.assertEqual((r["stop_reason"], r["tool_errors"], r["read_ids"]), ("final_answer", 1, ["D01"]))
        failed = [e for e in r["trace"] if e["event"] == "tool" and e["status"] == "error"]
        self.assertEqual(failed[0]["result"]["error"]["code"], "tool_failure")
        self.assertNotIn("секретный", json.dumps(r, ensure_ascii=False))

    def test_persistent_failure_ends_with_clear_status(self):
        def broken(name, arguments, docs):
            raise OSError("диск недоступен")
        with mock.patch.object(agent, "run_allowed_tool", broken):
            r = run(Script(tools(call("read_doc", doc_id="D01")), repeat_last=True))
        self.assertIn(r["stop_reason"], {"budget_exhausted", "tool_budget_exhausted"})
        self.assertIsNone(r["answer"])
        self.assertGreaterEqual(r["tool_errors"], 1)

class A5_LimitStopsLoop(unittest.TestCase):
    def test_model_call_limit(self):
        r = run(Script(tools(call("search_docs", query="скан")), repeat_last=True), {**CFG, "max_model_calls": 2})
        self.assertEqual((r["stop_reason"], r["model_calls"], r["answer"]), ("budget_exhausted", 2, None))

    def test_tool_call_limit(self):
        r = run(Script(tools(call("search_docs", query="скан"), call("search_docs", query="api")), repeat_last=True),
                {**CFG, "max_tool_calls": 1})
        self.assertEqual((r["stop_reason"], r["tool_calls"], r["answer"]), ("tool_budget_exhausted", 0, None))

class Regression_Replay(unittest.TestCase):
    def test_replay_still_works(self):
        r = agent.run_agent(agent.QUESTION, CFG, agent.make_replay_model(), "REPLAY", emit=lambda *_: None)
        self.assertEqual((r["stop_reason"], r["read_ids"], r["model_calls"]), ("final_answer", ["D01", "D02"], 4))

if __name__ == "__main__":
    unittest.main(verbosity=2)
