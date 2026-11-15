"""W1-W4: слабости агента, найденные в живом прогоне (report.md, «Дополнение», Таблица 4).
Модель заменена заглушкой, сеть не используется. Каждый тест описывает правильное поведение;
@expectedFailure стоит там, где агент так не умеет (агент сознательно не дорабатывался)."""
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import agent  # noqa: E402
from test_agent import CFG, Script, call, run, text, tools  # noqa: E402


class FakeResponse:
    """Ответ HTTP-сервера в формате OpenAI chat/completions."""
    def __init__(self, body):
        self.raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
    def read(self, limit):
        return self.raw[:limit]
    def __enter__(self):
        return self
    def __exit__(self, *exc):
        return False


def http_model(*choices):
    """Настоящий make_live_model, но вместо сети — заранее заданные ответы сервера (message, finish_reason)."""
    bodies = iter([{"choices": [{"message": msg, "finish_reason": reason}],
                    "usage": {"completion_tokens": CFG["max_output_tokens"] if reason == "length" else 50}}
                   for msg, reason in choices])
    opener = mock.Mock()
    opener.open.side_effect = lambda request, timeout: FakeResponse(next(bodies))
    patcher = mock.patch.object(agent, "build_opener", return_value=opener)
    patcher.start()
    return agent.make_live_model(CFG, agent.LOCAL_KEY), patcher


SEARCH = tools(call("search_docs", query="скан OCR внешний API"))
READ_D01 = tools(call("read_doc", doc_id="D01"))


class W1_TruncatedOrEmptyReply(unittest.TestCase):
    @unittest.expectedFailure
    def test_truncated_answer_is_not_final(self):
        """Слабость 1: finish_reason не проверяется, ответ, обрезанный по лимиту, принимается как final_answer."""
        model, patcher = http_model((SEARCH, "tool_calls"), (READ_D01, "tool_calls"),
                                    ({"role": "assistant", "content": "**Обработка скана:**\n- Скан"}, "length"))
        self.addCleanup(patcher.stop)
        r = run(model)
        self.assertNotEqual(r["stop_reason"], "final_answer")

    @unittest.expectedFailure
    def test_empty_reply_ends_with_clear_status(self):
        """Слабость 1: пустой content без tool_calls роняет run_agent исключением AgentError, журнала нет."""
        try:
            r = run(Script(SEARCH, READ_D01, {"role": "assistant", "content": ""}, repeat_last=True))
        except agent.AgentError as exc:
            self.fail(f"исключение вместо stop_reason: {exc}")
        self.assertNotEqual(r["stop_reason"], "final_answer")
        self.assertTrue(r["trace"])


class W2_CitationFormat(unittest.TestCase):
    @unittest.expectedFailure
    def test_bold_citation_of_unread_doc_is_rejected(self):
        """Слабость 2: ссылка в формате **D05:2-4** не распознаётся, непрочитанный D05 проходит проверку."""
        r = run(Script(SEARCH, READ_D01, text("Достаточно проверить имя файла **D05:2-4**."), repeat_last=True))
        self.assertNotEqual(r["stop_reason"], "final_answer")

    @unittest.expectedFailure
    def test_line_in_parentheses_citation_of_unread_doc_is_rejected(self):
        """Слабость 2: ссылка в формате «D03 (строка 3)» не распознаётся, непрочитанный D03 проходит проверку."""
        r = run(Script(SEARCH, READ_D01, text("Цена лицензии не указана. Источник: D03 (строка 3)."), repeat_last=True))
        self.assertNotEqual(r["stop_reason"], "final_answer")

    @unittest.expectedFailure
    def test_answer_without_citations_gets_a_note(self):
        """Слабость 2: ответ без единой ссылки после чтения документов принимается без замечания «укажи источники»."""
        m = Script(SEARCH, READ_D01, text("Проверьте числа, даты и имена."), text("Проверьте числа, даты и имена [D01:2]."))
        r = run(m)
        self.assertEqual(len(m.histories), 4)  # после ответа без ссылок модель получила замечание
        self.assertIn("[D01:2]", r["answer"])


class W3_ServiceReplyAfterNote(unittest.TestCase):
    @unittest.expectedFailure
    def test_service_reply_is_not_final(self):
        """Слабость 3: после замечания служебная фраза без сути и ссылок принимается как final_answer."""
        r = run(Script(SEARCH, READ_D01, text("Актуальна D01 [D01:2], правило в [D06:1]."),
                       text("Понял вас, буду следовать правилам."), repeat_last=True))
        self.assertFalse(r["stop_reason"] == "final_answer" and "Понял вас" in (r["answer"] or ""))


class W4_SearchById(unittest.TestCase):
    @unittest.expectedFailure
    def test_search_by_id_finds_document_or_hints_read_doc(self):
        """Слабость 4: search_docs не находит документ по ID («D08») и не подсказывает read_doc."""
        result = agent.run_allowed_tool("search_docs", json.dumps({"query": "D08"}), agent.load_docs())
        found = [d["id"] for d in result.get("documents", [])]
        self.assertTrue("D08" in found or "read_doc" in json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main(verbosity=2)
