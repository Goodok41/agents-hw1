"""Обёртка над agent.run_agent для logs-live/: журнал сохраняется и при остановке с AgentError.
agent.py не меняется; вызовы модели и инструментов записываются через обёртки. Текст исключений не пишется."""
import argparse, json, sys
from pathlib import Path
import agent

p = argparse.ArgumentParser()
p.add_argument("--config", required=True); p.add_argument("--output", required=True); p.add_argument("question")
a = p.parse_args()
cfg = agent.load_config(a.config)
calls, tools = [], []
live = agent.make_live_model(cfg, agent.LOCAL_KEY)
def model(history, defs):
    reply, usage = live(history, defs)
    calls.append({"reply": reply, "usage": usage})
    return reply, usage
real_tool = agent.run_allowed_tool
def tool(name, arguments, docs):
    result = real_tool(name, arguments, docs)
    tools.append({"name": name, "arguments": arguments, "result": result})
    return result
agent.run_allowed_tool = tool
try:
    result = agent.run_agent(a.question.strip(), cfg, model, "LIVE")
except agent.AgentError:
    result = {"mode": "LIVE", "question": a.question, "stop_reason": "agent_error",
              "error_kind": "empty_model_reply" if calls and not (calls[-1]["reply"].get("content") or "").strip() else "agent_error",
              "model_calls": len(calls) + 1, "tool_calls": len(tools), "answer": None,
              "partial_model_calls": calls, "partial_tool_calls": tools}
    print("\nstop_reason: agent_error (", result["error_kind"], ")")
else:
    print("\nstop_reason:", result["stop_reason"], "\nОтвет:", result["answer"])
Path(a.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print("Трасса сохранена:", a.output)
