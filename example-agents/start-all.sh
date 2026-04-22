#!/bin/bash
# Start all NEXUS external marketplace agents
# Each agent registers itself with the NEXUS backend on startup.
# Make sure the backend is running at http://localhost:8000 first.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Starting NEXUS external marketplace agents..."
echo "Backend expected at: ${NEXUS_URL:-http://localhost:8000}"
echo ""

# Install deps for each agent if needed
for agent in defi-agent dexscreener-agent security-agent; do
  if [ -f "$SCRIPT_DIR/$agent/requirements.txt" ]; then
    echo "Installing deps for $agent..."
    pip install -q -r "$SCRIPT_DIR/$agent/requirements.txt"
  fi
done

echo ""
echo "Launching agents..."

# Start each agent on its own port in background
(cd "$SCRIPT_DIR/defi-agent" && AGENT_PORT=5001 uvicorn app:app --host 0.0.0.0 --port 5001) &
DEFI_PID=$!

(cd "$SCRIPT_DIR/dexscreener-agent" && AGENT_PORT=5002 uvicorn app:app --host 0.0.0.0 --port 5002) &
DEX_PID=$!

(cd "$SCRIPT_DIR/security-agent" && AGENT_PORT=5003 uvicorn app:app --host 0.0.0.0 --port 5003) &
SEC_PID=$!

echo ""
echo "Agents running:"
echo "  DeFi Agent       (PID $DEFI_PID) -> http://localhost:5001"
echo "  DEXScreener      (PID $DEX_PID)  -> http://localhost:5002"
echo "  Security Agent   (PID $SEC_PID)  -> http://localhost:5003"
echo ""
echo "Press Ctrl+C to stop all agents"

# Wait for all background jobs
trap "kill $DEFI_PID $DEX_PID $SEC_PID 2>/dev/null; exit 0" INT TERM
wait
