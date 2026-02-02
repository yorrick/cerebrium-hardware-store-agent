# CLAUDE.md

This is a LiveKit Agents project deployed on Cerebrium. LiveKit Agents is a Python SDK for building voice AI agents. This project uses LiveKit Cloud for SIP/WebRTC infrastructure and Cerebrium for hosting the agent workers.

See @README.md for more about the architecture and deployment.

## Project structure

This Python project uses the `uv` package manager. You should always use `uv` to install dependencies, run the agent, and run tests.

All app-level code is in the `src/` directory. The main agent is in `agent.py` which serves as the entrypoint (see the Dockerfile for deployment details).

Be sure to maintain code formatting. You can use the ruff formatter/linter as needed: `uv run ruff format` and `uv run ruff check`.

## LiveKit Documentation

LiveKit Agents is a fast-evolving project, and the documentation is updated frequently. You should always refer to the latest documentation when working with this project. For your convenience, LiveKit offers an MCP server that can be used to browse and search its documentation. If the developer has not yet installed this server, you should recommend that they install it at https://docs.livekit.io/mcp.

### LiveKit Docs MCP Server installation

If you are Claude Code, run this command to install the server:

```
claude mcp add --transport http livekit-docs https://docs.livekit.io/mcp
```

## Development Feedback Loop

**IMPORTANT: For every code change, you MUST run this verification sequence before considering the change complete:**

```bash
# 1. Lint and format check
uv run ruff check src/
uv run ruff format --check src/

# 2. Type checking
uv run pyright src/

# 3. Run unit tests
uv run pytest

# 4. Test agent locally (requires .env.local with LiveKit credentials)
uv run python src/agent.py console
```

If any step fails, fix the issues before proceeding. Do not skip these checks.

## Testing

When possible, add tests for agent behavior. Read the [documentation](https://docs.livekit.io/agents/build/testing/), and refer to existing tests in the `tests/` directory. Run tests with `uv run pytest`.

Important: When modifying core agent behavior such as instructions, tool descriptions, and tasks/workflows/handoffs, never just guess what will work. Always use test-driven development (TDD) and begin by writing tests for the desired behavior.

## Running the Agent Locally

There are different modes for running the agent:

### Console Mode
```bash
uv run python src/agent.py console
```
Runs everything locally using your microphone. Useful for quick testing of agent responses, but **does not support SIP features** like call transfers since there's no LiveKit Cloud connection.

### Dev Mode (Recommended for Development)

```bash
mkdir -p logs && AGENT_NAME=hardware-store-dev uv run python src/agent.py dev 2>&1 | tee logs/agent-dev.log
```

This command:
- Sets `AGENT_NAME=hardware-store-dev` to register as the dev agent (avoiding conflicts with the production agent)
- Saves logs to `logs/agent-dev.log` for debugging
- Connects to LiveKit Cloud for real phone call testing with SIP features

### Production Mode
```bash
uv run python src/agent.py start
```
For production deployment. Deploy to Cerebrium with `cerebrium deploy`.

## Cerebrium Deployment

This project is configured for deployment on Cerebrium. Key files:

- `cerebrium.toml` - Cerebrium configuration (hardware, scaling, port)
- `Dockerfile` - Container build instructions

### Add Secrets via CLI

```bash
uv run cerebrium secrets add \
  "LIVEKIT_URL=wss://your-project.livekit.cloud" \
  "LIVEKIT_API_KEY=your-api-key" \
  "LIVEKIT_API_SECRET=your-api-secret"
```

Optional secrets for warm transfers:
- `SUPERVISOR_PHONE_NUMBER`
- `LIVEKIT_SIP_OUTBOUND_TRUNK`

Verify secrets are set:

```bash
uv run cerebrium secrets list
```

### Deploy

```bash
uv run cerebrium deploy -y
```

### Verify Deployment

1. Check app status:
   ```bash
   uv run cerebrium apps list
   ```
   Look for `STATUS: ready`

2. Check logs to confirm agent registered:
   ```bash
   uv run cerebrium logs hardware-store-agent --since "5m" --no-follow
   ```
   Look for: `"registered worker", "agent_name": "hardware-store"`

### Log Fetching Reliability

**IMPORTANT**: Cerebrium log fetching is unreliable. The same query may return logs on one attempt and nothing on the next.

**Workaround**: Run the log command up to 4 times before concluding logs are unavailable:

```bash
# Run this up to 4 times if no output
uv run cerebrium logs hardware-store-agent --since "15m" --no-follow
```

If after 4 attempts you still get no logs, then conclude the logs are not available for that time window.

### Make a Test Call

Call directly to LiveKit SIP endpoint:

```bash
twilio api:core:calls:create \
  --to "sip:+14387994512@1hroiplacjw.sip.livekit.cloud" \
  --from "+14388149935" \
  --url "https://handler.twilio.com/twiml/EHb11cbc2e61587849ca15aa519559569f"
```

Then check logs (run up to 4 times):

```bash
uv run cerebrium logs hardware-store-agent --since "5m" --no-follow | grep -E "received job request|Checking inventory"
```

Look for:
- `"received job request"` - call was received
- `"Checking inventory"` or other agent actions - agent is processing

### Tail Logs in Real-Time

```bash
uv run cerebrium logs hardware-store-agent
```

Press `Ctrl+C` to stop.

## SIP Telephony Setup

When configuring SIP trunks (e.g., Twilio) to route calls to LiveKit:

**Important:** The SIP URI for your project is NOT the same as your project subdomain. You must use the SIP URI shown in the [LiveKit Cloud dashboard](https://cloud.livekit.io) under **Telephony** → **SIP trunks**.

- Project URL: `wss://your-project-abc123.livekit.cloud`
- SIP URI: `sip:xyz789.sip.livekit.cloud` (different identifier!)

Always copy the SIP URI directly from the dashboard when configuring your SIP trunk provider's origination URL.

## Known Issues

- **Turn detector model**: The MultilingualModel turn detector requires model files that don't persist in Cerebrium's cache. Use `turn_detection=None` instead.
- **Log inconsistency**: Cerebrium's log API is unreliable - retry queries up to 4 times.
