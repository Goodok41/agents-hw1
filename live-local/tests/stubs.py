"""Заглушки модели для тестов live-local (B1-B5, W1-W4). Живая модель не используется.
A1-A5 для live-local прогоняются единым набором: python3 acceptance/test_a1_a5.py live-local -v"""
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
