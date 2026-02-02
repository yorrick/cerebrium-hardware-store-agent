# Hardware Store Voice Agent (Cerebrium)

A voice AI agent for a hardware store, built with [LiveKit Agents](https://github.com/livekit/agents) and deployed on [Cerebrium](https://cerebrium.ai/).

## Features

### Warm Transfers to Human Agents

When a customer requests to speak with a human or the agent cannot resolve their issue, the agent performs a warm transfer via SIP trunk. The caller is placed on a brief hold while the system connects to a supervisor, passing along conversation context and the reason for escalation. The AI agent then gracefully exits, handing the call to the human.

### Store Information Tools

The agent has access to real-time store data through callable tools:
- **Inventory lookup** - Check product availability, pricing, and aisle location at specific stores
- **Store hours** - Get operating hours for each location
- **Department info** - List available departments (Sales, Tool Rental, Pro Desk, etc.)

### Multilingual Support

The agent automatically responds in the caller's language. Using ElevenLabs Scribe v2 for speech-to-text (99+ languages), Google Gemini for understanding and response generation, and Cartesia for text-to-speech, language detection and response happens automatically with no manual selection needed.

### Voice AI Pipeline

- [LiveKit Turn Detector](https://docs.livekit.io/agents/build/turns/turn-detector/) for contextually-aware end-of-turn detection with multilingual support
- [Background voice cancellation](https://docs.livekit.io/home/cloud/noise-cancellation/) optimized for telephony
- Preemptive response generation for lower latency
- Twilio SIP integration for inbound phone calls

## Architecture

This agent uses a hybrid architecture:
- **Cerebrium** hosts the agent workers (compute)
- **LiveKit Cloud** handles SIP/WebRTC infrastructure (telephony routing, room management)

```
┌─────────────────────────────────────────────────────────────┐
│                    Twilio (Phone Numbers)                    │
└─────────────────────────┬───────────────────────────────────┘
                          │ SIP
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                  LiveKit Cloud (WebRTC/SIP)                  │
│  - Room management                                           │
│  - SIP trunk routing                                         │
│  - Audio/video transport                                     │
└─────────────────────────┬───────────────────────────────────┘
                          │ WebSocket
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                   Cerebrium (Agent Workers)                  │
│  ┌─────────────────────────────────────────────────────┐    │
│  │               Hardware Store Agent                   │    │
│  │  - STT (ElevenLabs Scribe)                          │    │
│  │  - LLM (Google Gemini)                              │    │
│  │  - TTS (Cartesia)                                   │    │
│  │  - Tools (inventory, hours, transfer)               │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

## Dev Setup

Clone the repository and install dependencies to a virtual environment:

```console
git clone <your-repo-url>
cd cerebrium-hardware-store-agent
uv sync
```

### Environment Setup

1. Sign up for [LiveKit Cloud](https://cloud.livekit.io/)
2. Copy `.env.example` to `.env.local` and fill in:
   - `LIVEKIT_URL`
   - `LIVEKIT_API_KEY`
   - `LIVEKIT_API_SECRET`

You can load the LiveKit environment automatically using the [LiveKit CLI](https://docs.livekit.io/home/cli/cli-setup):

```bash
lk cloud auth
lk app env -w -d .env.local
```

### Warm Transfer Setup (Optional)

To enable call transfers to humans, add to `.env.local`:
- `SUPERVISOR_PHONE_NUMBER` - Phone number to transfer calls to
- `LIVEKIT_SIP_OUTBOUND_TRUNK` - SIP trunk ID for outbound calls

## Run the Agent Locally

Before your first run, download required models:

```console
uv run python src/agent.py download-files
```

### Console Mode (Quick Testing)

Speak to your agent directly in the terminal:

```console
uv run python src/agent.py console
```

**Note:** Console mode does not support SIP features like call transfers.

### Dev Mode (With LiveKit Cloud)

For full functionality with telephony:

```console
mkdir -p logs && AGENT_NAME=hardware-store-dev uv run python src/agent.py dev 2>&1 | tee logs/agent-dev.log
```

## Deploy to Cerebrium

### Prerequisites

1. [Cerebrium account](https://cerebrium.ai)
2. Cerebrium CLI installed: `pip install cerebrium`
3. Logged in: `cerebrium login`

### Configure Secrets

Add your environment variables in the Cerebrium dashboard under **Secrets**:
- `LIVEKIT_API_KEY`
- `LIVEKIT_API_SECRET`
- `LIVEKIT_URL`
- `SUPERVISOR_PHONE_NUMBER` (optional)
- `LIVEKIT_SIP_OUTBOUND_TRUNK` (optional)

### Deploy

```bash
cerebrium deploy
```

This will:
1. Build the Docker image
2. Install dependencies
3. Download ML models
4. Deploy with autoscaling (1-5 replicas)

## Twilio Telephony Setup

To enable phone calls to your agent via Twilio, follow these steps:

### Prerequisites

- A [Twilio account](https://www.twilio.com/) with a purchased phone number
- [Twilio CLI](https://www.twilio.com/docs/twilio-cli/getting-started/install) installed and configured
- [LiveKit CLI](https://docs.livekit.io/home/cli/cli-setup) installed and authenticated

### Step 1: Create a Twilio SIP Trunk

```bash
twilio api trunking v1 trunks create \
  --friendly-name "My LiveKit Trunk" \
  --domain-name "my-trunk.pstn.twilio.com"
```

Save the Trunk SID (e.g., `TK...`) from the output.

### Step 2: Configure the Origination URL

Get your LiveKit SIP URI from the [LiveKit Cloud dashboard](https://cloud.livekit.io) under **Telephony** → **SIP trunks**. It looks like `sip:abc123.sip.livekit.cloud`.

> **Important**: Use the SIP URI shown in the dashboard, not your project subdomain.

```bash
twilio api trunking v1 trunks origination-urls create \
  --trunk-sid <your-trunk-sid> \
  --friendly-name "LiveKit SIP URI" \
  --sip-url "sip:<your-sip-uri>.sip.livekit.cloud" \
  --weight 1 --priority 1 --enabled
```

### Step 3: Associate Your Phone Number

```bash
# List your phone numbers to get the SID
twilio phone-numbers list

# Associate the phone number with the trunk
twilio api trunking v1 trunks phone-numbers create \
  --trunk-sid <your-trunk-sid> \
  --phone-number-sid <your-phone-number-sid>
```

### Step 4: Create a LiveKit Inbound Trunk

```bash
lk sip inbound create --name "Twilio Inbound" --numbers "+1234567890"
```

Replace `+1234567890` with your Twilio phone number.

### Step 5: Create a Dispatch Rule

```bash
lk sip dispatch create --name "Inbound Calls" --individual "call-" --randomize
```

### Verify Setup

Call your Twilio phone number. The call should connect to your agent running on Cerebrium.

To troubleshoot:
- Check agent logs in Cerebrium dashboard
- Check LiveKit Cloud **Telephony** → **Calls** for call logs

## Tests

Run the test suite:

```console
uv run pytest
```

## License

This project is licensed under the MIT License.
