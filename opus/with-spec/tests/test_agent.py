"""Тесты harden-agent: A1–A5 и регрессия --replay.

Запуск: python3 tests/test_agent.py
Живая модель не используется, сеть заблокирована до импорта agent.
"""
import contextlib
import io
import json
import socket
import sys
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

# --- Блокировка сети (до импорта agent) ---------------------------------------
class NetworkBlocked(RuntimeError):
    pass

def _blocked(*args, **kwargs):
    raise NetworkBlocked("Сеть в тестах запрещена")

class _BlockedSocket(socket.socket):
    def connect(self, *args, **kwargs):
        _blocked()
    def connect_ex(self, *args, **kwargs):
        _blocked()

socket.socket = _BlockedSocket
socket.create_connection = _blocked
socket.getaddrinfo = _blocked
urllib.request.urlopen = _blocked
urllib.request.OpenerDirector.open = _blocked

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import agent  # noqa: E402

# --- Заглушка модели -----------------------------------------------------------
def tool_call(name, **args):
    return {"name": name, "args": args}

def calls(*items):
    return {"role": "assistant", "content": None, "tool_calls": [
        {"id": f"c{i}_{it['name']}", "type": "function",
         "function": {"name": it["name"], "arguments": json.dumps(it["args"], ensure_ascii=False)}}
        for i, it in enumerate(items)]}

def final(text):
    return {"role": "assistant", "content": text}

class StubModel:
    """Отдаёт заранее заданные ответы и запоминает, что видела модель."""
    def __init__(self, replies, repeat_last=False):
        self.replies, self.repeat_last = list(replies), repeat_last
        self.calls, self.histories = 0, []

    def __call__(self, history, tools):
        self.histories.append(json.loads(json.dumps(history, ensure_ascii=False)))
        if self.calls < len(self.replies):
            reply = self.replies[self.calls]
        elif self.repeat_last:
            reply = self.replies[-1]
        else:
            raise AssertionError("Заглушка модели вызвана сверх сценария")
        self.calls += 1
        return json.loads(json.dumps(reply)), {}

def cfg(**overrides):
    base = agent.load_config()
    base.update(overrides)
    return base

def run(model, config=None, **kwargs):
    return agent.run_agent("тестовый вопрос", config or cfg(), model, "TEST", emit=lambda *_: None, **kwargs)

def tool_events(result):
    return [e for e in result["trace"] if e["event"] == "tool"]

SEARCH = tool_call("search_docs", query="скан OCR")
OK_ANSWER = "Скан сначала проходит OCR [D01:1-2]."


class TestNetworkIsBlocked(unittest.TestCase):
    def test_socket_connection_blocked(self):
        with self.assertRaises(NetworkBlocked):
            socket.create_connection(("example.com", 443), timeout=1)

    def test_live_model_cannot_reach_network(self):
        with self.assertRaises((NetworkBlocked, agent.AgentError)):
            agent.make_live_model(cfg(), "fake-key")([{"role": "user", "content": "x"}], [])


class TestA1MissingDocument(unittest.TestCase):
    """A1 / R1, R3: неизвестный doc_id -> not_found, ID в missing_ids."""

    def test_tool_returns_structured_not_found(self):
        result = agent.run_allowed_tool("read_doc", '{"doc_id": "D99"}', agent.load_docs())
        self.assertEqual(result["error"]["code"], "not_found")
        self.assertEqual(result["error"]["doc_id"], "D99")

    def test_missing_id_in_final_result(self):
        model = StubModel([calls(SEARCH), calls(tool_call("read_doc", doc_id="D99")),
                           calls(tool_call("read_doc", doc_id="D02"), tool_call("read_doc", doc_id="D01")),
                           final(OK_ANSWER)])
        result = run(model)
        self.assertEqual(result["stop_reason"], "final_answer")
        self.assertEqual(result["missing_ids"], ["D99"])
        self.assertEqual(result["read_ids"], ["D01", "D02"])  # по возрастанию
        self.assertEqual(result["tool_errors"], 1)
        statuses = [(e["name"], e["status"]) for e in tool_events(result)]
        self.assertEqual(statuses, [("search_docs", "ok"), ("read_doc", "error"), ("read_doc", "ok"), ("read_doc", "ok")])
        # модель увидела структурированную ошибку
        tool_msgs = [m for m in model.histories[2] if m["role"] == "tool"]
        self.assertEqual(json.loads(tool_msgs[-1]["content"])["error"]["code"], "not_found")

    def test_citing_missing_id_is_not_accepted(self):
        model = StubModel([calls(SEARCH), calls(tool_call("read_doc", doc_id="D99"), tool_call("read_doc", doc_id="D01")),
                           final("Ответ [D01:1] и [D99:1].")], repeat_last=True)
        result = run(model)
        self.assertEqual(result["stop_reason"], "unverified_sources")
        self.assertIsNone(result["answer"])
        self.assertEqual(result["missing_ids"], ["D99"])


class TestA2ToolFailure(unittest.TestCase):
    """A2 / R2, R3: исключение в инструменте -> tool_failure, цикл продолжается."""

    def test_exception_becomes_tool_failure_and_loop_continues(self):
        state = {"failed": False}
        def flaky(name, arguments, docs):
            if name == "read_doc" and not state["failed"]:
                state["failed"] = True
                raise RuntimeError("диск недоступен")
            return agent.run_allowed_tool(name, arguments, docs)

        model = StubModel([calls(SEARCH), calls(tool_call("read_doc", doc_id="D01")),
                           calls(tool_call("read_doc", doc_id="D01")), final(OK_ANSWER)])
        result = run(model, tool_fn=flaky)
        self.assertEqual(result["stop_reason"], "final_answer")
        self.assertEqual(result["answer"], OK_ANSWER)
        failed = tool_events(result)[1]
        self.assertEqual(failed["status"], "error")
        self.assertEqual(failed["result"]["error"]["code"], "tool_failure")
        self.assertIn("RuntimeError", failed["result"]["error"]["message"])
        self.assertEqual(result["tool_errors"], 1)
        self.assertEqual(result["tool_calls"], 3)  # сбойный вызов засчитан
        self.assertEqual(result["read_ids"], ["D01"])
        tool_msgs = [m for m in model.histories[2] if m["role"] == "tool"]
        self.assertEqual(json.loads(tool_msgs[-1]["content"])["error"]["code"], "tool_failure")

    def test_always_failing_tool_stays_within_limits(self):
        def broken(name, arguments, docs):
            raise ValueError("сломано")
        model = StubModel([calls(SEARCH)], repeat_last=True)
        result = run(model, cfg(max_model_calls=4, max_tool_calls=16), tool_fn=broken)
        self.assertEqual(result["stop_reason"], "budget_exhausted")
        self.assertIsNone(result["answer"])
        self.assertEqual(result["tool_errors"], 4)
        self.assertEqual(model.calls, 4)


class TestA3SourceVerification(unittest.TestCase):
    """A3 / R4: ссылка на непрочитанный ID -> не более 2 замечаний, затем unverified_sources."""

    def test_unverified_answer_stops_after_two_remarks(self):
        bad = final("Ответ [D01:1-2], [D02:1].")
        model = StubModel([calls(SEARCH), calls(tool_call("read_doc", doc_id="D01")), bad, bad, bad, bad])
        result = run(model)
        self.assertEqual(result["stop_reason"], "unverified_sources")
        self.assertIsNone(result["answer"])
        self.assertEqual(model.calls, 5)  # 2 инструмента + 3 ответа, четвёртый не запрошен
        remarks = [e for e in result["trace"] if e["event"] == "validation" and e["error"] == "unread_sources"]
        self.assertEqual(len(remarks), 2)
        self.assertTrue(all(r["ids"] == ["D02"] for r in remarks))
        # замечание модели содержит конкретный ID
        remark_msgs = [m["content"] for m in model.histories[-1] if m["role"] == "user" and "Проверка программы" in m["content"]]
        self.assertEqual(len(remark_msgs), 2)
        self.assertTrue(all("D02" in m and "D01" not in m.split("read_doc:")[-1] for m in remark_msgs))

    def test_answer_without_search_is_not_accepted(self):
        model = StubModel([final(OK_ANSWER)], repeat_last=True)
        result = run(model)
        self.assertEqual(result["stop_reason"], "unverified_sources")
        self.assertIsNone(result["answer"])
        self.assertEqual(model.calls, 3)

    def test_answer_accepted_after_reading(self):
        model = StubModel([calls(SEARCH), final(OK_ANSWER),
                           calls(tool_call("read_doc", doc_id="D01")), final(OK_ANSWER)])
        result = run(model)
        self.assertEqual(result["stop_reason"], "final_answer")
        self.assertEqual(result["answer"], OK_ANSWER)
        remark = [e for e in result["trace"] if e["event"] == "validation"]
        self.assertEqual(len(remark), 1)
        self.assertEqual(remark[0]["ids"], ["D01"])


class TestA4ModelBudget(unittest.TestCase):
    """A4 / R5: исчерпание вызовов модели -> budget_exhausted, answer = null."""

    def test_model_budget_exhausted(self):
        model = StubModel([calls(SEARCH)], repeat_last=True)
        result = run(model, cfg(max_model_calls=3))
        self.assertEqual(result["stop_reason"], "budget_exhausted")
        self.assertIsNone(result["answer"])
        self.assertEqual(model.calls, 3)
        self.assertEqual(result["model_calls"], 3)
        for key in ("read_ids", "missing_ids", "tool_errors"):
            self.assertIn(key, result)

    def test_remarks_do_not_extend_model_budget(self):
        model = StubModel([calls(SEARCH), final(OK_ANSWER)], repeat_last=True)
        result = run(model, cfg(max_model_calls=2))
        self.assertEqual(result["stop_reason"], "budget_exhausted")
        self.assertIsNone(result["answer"])
        self.assertEqual(model.calls, 2)


class TestA5ToolBudget(unittest.TestCase):
    """A5 / R5: исчерпание вызовов инструментов -> tool_budget_exhausted, answer = null."""

    def test_tool_budget_exhausted(self):
        batch = calls(*[tool_call("search_docs", query=f"скан {i}") for i in range(5)])
        model = StubModel([batch], repeat_last=True)
        result = run(model, cfg(max_tool_calls=12))
        self.assertEqual(result["stop_reason"], "tool_budget_exhausted")
        self.assertIsNone(result["answer"])
        self.assertEqual(result["tool_calls"], 10)  # третий пакет не выполнен
        self.assertLessEqual(result["tool_calls"], 12)
        self.assertEqual(len(tool_events(result)), 10)
        for key in ("read_ids", "missing_ids", "tool_errors"):
            self.assertIn(key, result)


class TestToolInterfaceCompat(unittest.TestCase):
    """R6: интерфейс инструментов не изменился."""

    def test_tool_schema(self):
        params = {t["function"]["name"]: t["function"]["parameters"] for t in agent.TOOLS}
        self.assertEqual(set(params), {"search_docs", "read_doc"})
        self.assertEqual(params["search_docs"]["required"], ["query"])
        self.assertEqual(params["read_doc"]["required"], ["doc_id"])

    def test_successful_result_shapes(self):
        docs = agent.load_docs()
        found = agent.run_allowed_tool("search_docs", '{"query": "скан"}', docs)
        self.assertEqual(set(found), {"documents"})
        self.assertEqual(set(found["documents"][0]), {"id", "title", "snippet"})
        doc = agent.run_allowed_tool("read_doc", '{"doc_id": "D01"}', docs)
        self.assertEqual(set(doc), {"id", "title", "version", "lines"})
        self.assertEqual(agent.run_allowed_tool("read_doc", '{"id": "D01"}', docs)["error"]["code"], "bad_arguments")


class TestReplayRegression(unittest.TestCase):
    """R6: поведение --replay по умолчанию сохранено."""

    def test_replay_run_agent(self):
        result = agent.run_agent(agent.QUESTION, agent.load_config(), agent.make_replay_model(), "REPLAY", emit=lambda *_: None)
        self.assertEqual(result["stop_reason"], "final_answer")
        self.assertEqual(result["model_calls"], 4)
        self.assertEqual(result["tool_calls"], 4)
        self.assertEqual(result["answer"], agent.REPLAY_RESPONSES[3]["content"])
        self.assertEqual(result["read_ids"], ["D01", "D02"])
        self.assertEqual(result["missing_ids"], [])
        self.assertEqual(result["tool_errors"], 0)
        self.assertEqual([(e["name"], e["status"]) for e in tool_events(result)],
                         [("search_docs", "ok"), ("search_docs", "ok"), ("read_doc", "ok"), ("read_doc", "ok")])

    def test_replay_cli_output(self):
        out = io.StringIO()
        with mock.patch.object(sys, "argv", ["agent.py", "--replay"]), contextlib.redirect_stdout(out):
            code = agent.main()
        text = out.getvalue()
        self.assertEqual(code, 0)
        steps = [line for line in text.splitlines() if line.startswith(("[модель", "[инструмент", "[проверка"))]
        self.assertEqual(steps, [
            "[модель 1] запрос инструмента",
            '[инструмент 1] search_docs {"query":"обработка скана"}',
            '[инструмент 2] search_docs {"query":"внешний API проверка данных"}',
            "[модель 2] финальный ответ",
            "[проверка] Источники ещё не прочитаны. Нужен read_doc.",
            "[модель 3] запрос инструмента",
            '[инструмент 3] read_doc {"doc_id":"D01"}',
            '[инструмент 4] read_doc {"doc_id":"D02"}',
            "[модель 4] финальный ответ",
        ])
        self.assertIn("stop_reason: final_answer", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
