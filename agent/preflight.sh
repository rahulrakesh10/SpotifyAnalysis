#!/bin/bash
# Run this before trying the chat. It checks everything is in place, starts the project,
# and asks the agent one question so you know it works before you open the browser.
cd "$(dirname "$0")"
fail=0
ok()  { echo "  ok    $1"; }
bad() { echo "  FAIL  $1"; fail=1; }

echo "Checking your setup..."
command -v docker >/dev/null && ok "Docker is installed" || bad "Docker is not installed"
command -v ollama >/dev/null && ok "Ollama is installed" || bad "Ollama is not installed (https://ollama.com)"
curl -s -m 3 http://127.0.0.1:11434/api/tags >/dev/null && ok "Ollama is running" || bad "Ollama is not running: open the Ollama app, then run this again"
free=$(sysctl -n vm.swapusage | sed -n 's/.*free = \([0-9.]*\)M.*/\1/p')
if [ "${free%.*}" -lt 1500 ] 2>/dev/null; then
  echo "  WARN  Your Mac is low on memory (only ${free%.*} MB of swap free). Quit Firefox and other big apps first, or the chat will be slow."
else
  ok "Enough free memory"
fi
[ "$fail" = 1 ] && { echo; echo "Fix the FAIL lines above, then run ./preflight.sh again."; exit 1; }

echo; echo "Starting the project (the first start takes a minute)..."
./start.sh >/dev/null 2>&1
for i in $(seq 1 40); do python3 checks.py >/dev/null 2>&1 && break; sleep 3; done
python3 checks.py | tail -1 | sed 's/^/  /'
curl -s -o /dev/null -w "  LibreChat web page: HTTP %{http_code}\n" http://127.0.0.1:3080/

echo; echo "Asking the agent a test question (a few seconds)..."
answer=$(python3 try_agent.py --openai "What factors predict faster growth beyond release age?" 2>&1)
echo "$answer" | sed -n '3,8p' | cut -c1-160 | sed 's/^/  /'
if echo "$answer" | grep -qi "latin" && echo "$answer" | grep -qi "country"; then
  ok "The agent gave the expected answer (Latin Music and Country)"
else
  echo "  WARN  The answer looks different from expected. The agent is a small model, so try the question again in the chat."
fi

echo
echo "Ready. Open http://localhost:3080, create an account, and pick 'Song Analyst'."
echo "When you are done, run ./stop.sh to free your memory."
