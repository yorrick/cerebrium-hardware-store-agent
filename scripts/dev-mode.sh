#!/bin/bash
# Toggle dispatch rule between dev and prod agent names
# Usage: ./scripts/dev-mode.sh [on|off]

set -e

DISPATCH_RULE_ID="SDR_PQ7m39MPaf5Z"
DEV_AGENT_NAME="hardware-store-dev"
PROD_AGENT_NAME="hardware-store"

create_dispatch_rule() {
    local agent_name=$1
    local temp_file=$(mktemp)

    cat > "$temp_file" << EOF
{
  "dispatch_rule": {
    "rule": {
      "dispatchRuleIndividual": {
        "roomPrefix": "call-"
      }
    },
    "name": "Hardware Store Calls",
    "roomConfig": {
      "agents": [{
        "agentName": "$agent_name"
      }]
    }
  }
}
EOF

    echo "$temp_file"
}

case "${1:-status}" in
    on|dev)
        echo "Switching to DEV mode (agent: $DEV_AGENT_NAME)..."
        lk sip dispatch delete "$DISPATCH_RULE_ID" 2>/dev/null || true
        temp_file=$(create_dispatch_rule "$DEV_AGENT_NAME")
        lk sip dispatch create "$temp_file"
        rm "$temp_file"
        echo ""
        echo "Dev mode enabled. Now run your agent with:"
        echo "  AGENT_NAME=hardware-store-dev DEV_MODE_SHUTDOWN=true uv run python src/agent.py dev"
        echo ""
        echo "Your local agent will receive all calls and shut down after the call ends."
        ;;
    off|prod)
        echo "Switching to PROD mode (agent: $PROD_AGENT_NAME)..."
        # Find current dispatch rule ID (it changes after recreation)
        current_id=$(lk sip dispatch list 2>/dev/null | grep "Hardware Store" | awk '{print $2}' | head -1)
        if [ -n "$current_id" ]; then
            lk sip dispatch delete "$current_id" 2>/dev/null || true
        fi
        temp_file=$(create_dispatch_rule "$PROD_AGENT_NAME")
        lk sip dispatch create "$temp_file"
        rm "$temp_file"
        echo ""
        echo "Prod mode enabled. Cloud agent will receive calls."
        ;;
    status)
        echo "Current dispatch rules:"
        lk sip dispatch list
        ;;
    *)
        echo "Usage: $0 [on|off|status]"
        echo "  on/dev   - Route calls to local dev agent (hardware-store-dev)"
        echo "  off/prod - Route calls to cloud agent (hardware-store)"
        echo "  status   - Show current dispatch rules"
        exit 1
        ;;
esac
