"""Try the Song Analyst with a local Ollama model, using the same instructions and tools that
LibreChat uses. Needs the stack running (./start.sh) and Ollama running.

    python3 try_agent.py "Which genres grow fastest among 2025 releases?" [--model song-analyst]
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

import yaml

from query import call_tool, list_tools

OLLAMA = "http://127.0.0.1:11434/api/chat"
SPEC = yaml.safe_load((Path(__file__).parent / "librechat-config" / "librechat.yaml").read_text())["modelSpecs"]["list"][0]
INSTRUCTIONS = SPEC["preset"]["instructions"]
_tools = None


def tools():
    """The song tools, in the format Ollama expects (read from the running tool server)."""
    global _tools
    if _tools is None:
        _tools = [{"type": "function", "function": {
            "name": t["name"], "description": t["description"], "parameters": t["inputSchema"]}} for t in list_tools()]
    return _tools


def chat(model, messages):
    body = {"model": model, "messages": messages, "tools": tools(), "stream": False,
            "options": {"num_ctx": 8192, "temperature": 0.1}, "keep_alive": "30s"}
    req = urllib.request.Request(OLLAMA, json.dumps(body).encode(), {"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=600).read())["message"]


def chat_openai(model, messages):
    """Same request shape LibreChat sends: Ollama's OpenAI-compatible endpoint (no num_ctx here; the model's own setting applies)."""
    body = {"model": model, "messages": messages, "tools": tools(), "stream": False, "temperature": 0.1}
    req = urllib.request.Request("http://127.0.0.1:11434/v1/chat/completions", json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=600).read())["choices"][0]["message"]


def ask_openai(question, model, max_steps=6, quiet=False):
    """Like ask(), but over the OpenAI-style endpoint, which is what LibreChat uses."""
    calls = []
    messages = [{"role": "system", "content": INSTRUCTIONS}, {"role": "user", "content": question}]
    for _ in range(max_steps):
        msg = chat_openai(model, messages)
        messages.append({k: v for k, v in msg.items() if k in ("role", "content", "tool_calls")})
        if not msg.get("tool_calls"):
            return msg.get("content") or "", calls
        for call in msg["tool_calls"]:
            name = call["function"]["name"]
            args = json.loads(call["function"]["arguments"] or "{}")
            calls.append(f"{name}({json.dumps(args, ensure_ascii=False)})")
            if not quiet:
                print(f"  [tool] {calls[-1][:300]}")
            try:
                ok, body = call_tool(name, args)
            except Exception as e:
                ok, body = False, str(e)
            text = json.dumps(body, ensure_ascii=False)[:3000] if ok else "ERROR: " + str(body)[:500]
            messages.append({"role": "tool", "tool_call_id": call.get("id", ""), "content": text})
    return "(stopped: too many tool calls)", calls


def ask(question, model, max_steps=6, quiet=False):
    """Returns (answer, calls). Each call is written like: song_stats({"genre": "Pop"})."""
    calls = []
    messages = [{"role": "system", "content": INSTRUCTIONS}, {"role": "user", "content": question}]
    for _ in range(max_steps):
        msg = chat(model, messages)
        messages.append(msg)
        if not msg.get("tool_calls"):
            return msg.get("content", ""), calls
        for call in msg["tool_calls"]:
            name, args = call["function"]["name"], call["function"]["arguments"]
            calls.append(f"{name}({json.dumps(args, ensure_ascii=False)})")
            if not quiet:
                print(f"  [tool] {calls[-1][:300]}")
            try:
                ok, body = call_tool(name, args)
            except Exception as e:  # a bad argument from the model: report it back like LibreChat would
                ok, body = False, str(e)
            text = json.dumps(body, ensure_ascii=False)[:3000] if ok else "ERROR: " + str(body)[:500]
            if not quiet:
                print(f"  [result] {text[:200]}")
            messages.append({"role": "tool", "content": text})
    return "(stopped: too many tool calls)", calls


if __name__ == "__main__":
    args = sys.argv[1:]
    model = "song-analyst"
    api_flag = "--openai" in args
    args = [a for a in args if a != "--openai"]
    if "--model" in args:
        i = args.index("--model"); model = args[i + 1]; del args[i:i + 2]
    try:
        for q in args:
            print(f"\nQ: {q}")
            start = time.time()
            print("\n" + (ask_openai if "--openai" in sys.argv else ask)(q, model)[0] + f"\n\n({time.time() - start:.0f}s)")
    finally:  # free the model's memory straight away
        urllib.request.urlopen(urllib.request.Request(
            "http://127.0.0.1:11434/api/generate", json.dumps({"model": model, "keep_alive": 0}).encode(),
            {"Content-Type": "application/json"}))
