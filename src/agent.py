import logging
import os
from typing import Any

from dotenv import load_dotenv
from livekit import rtc
from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    JobProcess,
    RunContext,
    WorkerOptions,
    WorkerType,
    cli,
    function_tool,
    room_io,
)
from livekit.agents.llm import ToolError
from livekit.plugins import cartesia, deepgram, google, noise_cancellation, silero

logger = logging.getLogger("agent")

load_dotenv(".env.local")

# Store location data - single source of truth for all locations
STORE_LOCATIONS = {
    "oakville": {
        "id": "8c5dc6ab-a958-4b1d-be32-5b38bdb21b80",
        "name": "Oakville",
        "hours": {
            "Monday - Saturday": "8:00 AM to 9:00 PM",
            "Sunday": "10:00 AM to 6:00 PM",
        },
        "departments": ["Sales", "Customer Service", "Tool Rental", "Contractor Desk"],
    },
    "burnaby": {
        "id": "d8e8f8f8-3d3d-4c4c-8c8c-8c8c8c8c8c8c",
        "name": "Burnaby",
        "hours": {
            "Monday - Friday": "7:30 AM to 9:00 PM",
            "Saturday": "8:00 AM to 8:00 PM",
            "Sunday": "10:00 AM to 5:00 PM",
        },
        "departments": ["Sales", "Customer Service", "Pro Desk"],
    },
    "halifax": {
        "id": "123e4567-e89b-12d3-a456-426614174000",
        "name": "Halifax",
        "hours": {
            "Monday - Saturday": "8:00 AM to 10:00 PM",
            "Sunday": "9:00 AM to 7:00 PM",
        },
        "departments": ["Sales", "Customer Service", "Tool Rental", "Garden Center"],
    },
}

LOCATION_NAMES = "Oakville, Burnaby, or Halifax"

HARDWARE_STORE_INSTRUCTIONS = """You are a friendly and efficient virtual receptionist for Builder's Hub Hardware. Your primary role is to answer incoming calls, determine the caller's needs, and provide assistance using the tools and information available to you.

Since this phone number serves multiple store locations, your absolute first step is to always clarify which location the caller is interested in before proceeding. Your main tasks are to check product inventory and provide store information when necessary.

## Rules & Constraints

- **Respond in the caller's language.** If the caller speaks to you in a language other than English, respond in that same language. You are a multilingual assistant and should match the caller's preferred language throughout the conversation.
- **Always identify the location first.** Before any other action, you must determine the caller's desired store location. Ask: "Which of our locations can I help you with today: Oakville, Burnaby, or Halifax?"
- **Use the inventory_check tool correctly.** If a caller asks about product availability for a specific item, you MUST use this tool. You must first get the item name and the caller's chosen store location.
- **Be precise with tool results.** When the tool returns inventory status, relay that information clearly. If an item is out of stock at the selected location, offer to check other locations.
- **Do not guess or hallucinate.** If you do not have the information or a tool to find it, state that you are unable to help with that specific request.
- **Maintain a conversational flow.** Keep your responses concise. Wait for the caller to finish speaking before you respond.
- **Format for Natural Speech.** When relaying information like prices or quantities from the inventory tool, format it to be spoken naturally. For example, a price of "$6.50" should be stated as "six dollars and fifty cents," and a quantity of "1200" should be read as "twelve hundred."

## Store Locations

Here are our store locations and their details:

### Oakville
- Hours: Monday - Saturday: 8:00 AM to 9:00 PM, Sunday: 10:00 AM to 6:00 PM
- Departments: Sales, Customer Service, Tool Rental, Contractor Desk

### Burnaby
- Hours: Monday - Friday: 7:30 AM to 9:00 PM, Saturday: 8:00 AM to 8:00 PM, Sunday: 10:00 AM to 5:00 PM
- Departments: Sales, Customer Service, Pro Desk

### Halifax
- Hours: Monday - Saturday: 8:00 AM to 10:00 PM, Sunday: 9:00 AM to 7:00 PM
- Departments: Sales, Customer Service, Tool Rental, Garden Center

## Personality & Tone

Your persona should be professional, patient, and consistently helpful. Use a clear and welcoming tone. You are the first point of contact for the customer, so it's important to be friendly and make them feel valued. Phrases like "I can certainly help with that," "Of course," and "Let me check on that for you" should be used to create a positive experience.
"""


def get_store_by_name(location_name: str) -> dict[str, Any] | None:
    """Look up a store by name (case-insensitive)."""
    return STORE_LOCATIONS.get(location_name.lower())


class HardwareStoreAgent(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions=HARDWARE_STORE_INSTRUCTIONS,
        )

    async def on_enter(self) -> None:
        """Called when the agent first enters the session. Greet the caller."""
        await self.session.say(
            "Welcome to Builder's Hub Hardware, how can I help you today?",
            allow_interruptions=True,
        )

    @function_tool()
    async def transfer_to_human(
        self,
        context: RunContext,
        reason: str = "Customer requested human assistance",
    ) -> None:
        """Transfer the caller to a human agent. Use this when the customer explicitly
        requests to speak with a human, or when you are unable to resolve their issue.

        Args:
            reason: Brief explanation of why the transfer is needed
        """
        from livekit.agents.beta.workflows import WarmTransferTask

        logger.info(f"Initiating warm transfer: {reason}")

        # Get transfer configuration from environment
        supervisor_phone = os.getenv("SUPERVISOR_PHONE_NUMBER")
        sip_trunk_id = os.getenv("LIVEKIT_SIP_OUTBOUND_TRUNK") or os.getenv(
            "SIP_OUTBOUND_TRUNK_ID"
        )

        if not supervisor_phone:
            logger.error(
                "Cannot initiate warm transfer: SUPERVISOR_PHONE_NUMBER not configured"
            )
            raise ToolError(
                "I'm sorry, I'm unable to connect you with a team member right now. "
                "Please call back or visit us in store."
            )

        if not sip_trunk_id:
            logger.error(
                "Cannot initiate warm transfer: LIVEKIT_SIP_OUTBOUND_TRUNK or "
                "SIP_OUTBOUND_TRUNK_ID not configured"
            )
            raise ToolError(
                "I'm sorry, I'm unable to connect you with a team member right now. "
                "Please call back or visit us in store."
            )

        await self.session.say(
            "Please hold while I connect you to a team member.",
            allow_interruptions=False,
        )

        try:
            result = await WarmTransferTask(
                target_phone_number=supervisor_phone,
                sip_trunk_id=sip_trunk_id,
                chat_ctx=self.chat_ctx,
                extra_instructions=(
                    f"Transfer reason: {reason}\n\n"
                    "Please assist this customer with extra care and patience. "
                    "The customer may need human support."
                ),
            )
            logger.info(
                "Warm transfer completed successfully",
                extra={"supervisor_identity": result.human_agent_identity},
            )

            await self.session.say(
                "You are now connected with one of our team members. "
                "I'll leave you with them. Have a great day!",
                allow_interruptions=False,
            )
            self.session.shutdown()

        except ToolError as e:
            logger.error(f"Warm transfer failed with tool error: {e}")
            raise e
        except Exception as e:
            logger.exception("Warm transfer failed")
            raise ToolError(
                "I apologize, but I'm having trouble connecting you right now. "
                "Please call back in a few minutes or visit us in store."
            ) from e

    @function_tool()
    async def inventory_check(
        self,
        context: RunContext,
        item_name: str,
        store_location: str,
    ) -> dict[str, Any]:
        """Check if an item is in stock at a specific store location.

        Args:
            item_name: The name of the product the user is asking about (e.g., "pressure-treated 2x4s", "DeWalt 20V MAX cordless drill")
            store_location: The store location name (Oakville, Burnaby, or Halifax)
        """
        logger.info(f"Checking inventory for '{item_name}' at {store_location}")

        store = get_store_by_name(store_location)
        if not store:
            return {
                "success": False,
                "error": f"Unknown store location: {store_location}. Valid locations are: {LOCATION_NAMES}",
            }

        # TODO: Replace with actual inventory API call
        # For now, return mock data
        # In production, this would call an external inventory service
        return {
            "success": True,
            "item_name": item_name,
            "store_name": store["name"],
            "store_id": store["id"],
            "in_stock": True,
            "quantity": 150,
            "price": "$4.97",
            "aisle": "Building Materials, Aisle 12",
        }

    @function_tool()
    async def get_store_hours(
        self,
        context: RunContext,
        store_location: str,
    ) -> dict[str, Any]:
        """Get the operating hours for a specific store location.

        Args:
            store_location: The store location name (Oakville, Burnaby, or Halifax)
        """
        logger.info(f"Getting hours for {store_location}")

        store = get_store_by_name(store_location)
        if not store:
            return {
                "success": False,
                "error": f"Unknown store location: {store_location}. Valid locations are: {LOCATION_NAMES}",
            }

        return {
            "success": True,
            "store_name": store["name"],
            "hours": store["hours"],
        }

    @function_tool()
    async def get_store_departments(
        self,
        context: RunContext,
        store_location: str,
    ) -> dict[str, Any]:
        """Get the available departments at a specific store location.

        Args:
            store_location: The store location name (Oakville, Burnaby, or Halifax)
        """
        logger.info(f"Getting departments for {store_location}")

        store = get_store_by_name(store_location)
        if not store:
            return {
                "success": False,
                "error": f"Unknown store location: {store_location}. Valid locations are: {LOCATION_NAMES}",
            }

        return {
            "success": True,
            "store_name": store["name"],
            "departments": store["departments"],
        }


def prewarm(proc: JobProcess):
    """Prewarm function - loads models when worker starts."""
    # Load VAD model
    proc.userdata["vad"] = silero.VAD.load()
    logger.info("[Prewarm] VAD model loaded")


# Use hardware-store-dev for local testing, hardware-store for production
AGENT_NAME = os.getenv("AGENT_NAME", "hardware-store")


async def entrypoint(ctx: JobContext):
    """Main entrypoint for the agent worker."""
    # Logging setup
    ctx.log_context_fields = {
        "room": ctx.room.name,
    }

    # Set up a voice AI pipeline for the hardware store agent
    session = AgentSession(
        # Speech-to-text (STT) using Deepgram Nova-3 for reliable English transcription
        stt=deepgram.STT(model="nova-3", language="en"),
        # Large Language Model (LLM) for processing user input and generating responses
        llm=google.LLM(model="gemini-2.5-flash"),
        # Text-to-speech (TTS) using Cartesia plugin directly
        tts=cartesia.TTS(model="sonic-3", voice="9626c31c-bec5-4cca-baa8-f8ba9e84c8bc"),
        # Using VAD-only turn detection since MultilingualModel files don't persist
        # in Cerebrium's runtime filesystem (Cerebrium overwrites the Docker image at runtime)
        turn_detection="vad",
        vad=ctx.proc.userdata["vad"],
        # Allow preemptive generation for faster responses
        preemptive_generation=True,
    )

    # Create the hardware store agent
    agent = HardwareStoreAgent()

    # Start the session with the hardware store agent
    await session.start(
        agent=agent,
        room=ctx.room,
        room_options=room_io.RoomOptions(
            audio_input=room_io.AudioInputOptions(
                # Use telephony-optimized noise cancellation for SIP calls
                noise_cancellation=lambda params: noise_cancellation.BVCTelephony()
                if params.participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP
                else noise_cancellation.BVC(),
            ),
        ),
    )

    # Join the room and connect to the caller
    await ctx.connect()


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
            agent_name=AGENT_NAME,
            worker_type=WorkerType.ROOM,
            # Port for Cerebrium deployment
            port=int(os.getenv("PORT", "8600")),
        )
    )
