import discord
import logging
from openai import APIError

from .chat_thread import ChatThreadManager
from .config import bot_config
from .scryfall import get_mtg_embeds_from_message

logger = logging.getLogger(__name__)


class SynthbotCore:
    client: discord.Client
    thread_mgr: ChatThreadManager

    def __init__(self, client: discord.Client):
        self.client = client
        self.thread_mgr = ChatThreadManager()

    async def on_dm_message(self, message: discord.Message):
        """Do a DM response"""
        if (
            not bot_config.discord.admin_users
            or message.author.id not in bot_config.discord.admin_users
        ):
            await message.channel.send(
                "Hello! I am Synthgen GPT, your friendly robot friend."
            )
            return

        await message.channel.send(
            "Hello! I am Synthgen GPT, your personal synth assistant."
        )

    async def on_channel_message(self, message: discord.Message):
        """User mentioned us, create a thread with our reply"""

        response_thread = await message.create_thread(
            name="Synthbot reply",
            auto_archive_duration=1440,
            reason="ChatGPT conversation",
        )

        await self.handle_response_thread(message, response_thread)

    async def on_thread_message(self, message: discord.Message):
        """Fetch the ChatThread for this message"""

        await self.handle_response_thread(message, message.channel)

    async def handle_response_thread(
        self,
        message: discord.Message,
        response_thread: discord.Thread,
    ):
        """Reply to the thread"""
        async with response_thread.typing():
            # Build the OpenAI conversation
            convo = await self.thread_mgr.get_thread(self.client.user, response_thread)
            convo.add(message)

            if response_thread.name == bot_config.discord.default_thread_title:
                # Summarize the thread prompt into something shorter for the thread title.
                try:
                    summary_resp = await convo.summarize()
                    await response_thread.edit(name=summary_resp)
                except APIError as e:
                    logger.exception(
                        "Got an error while trying to summarize the conversation"
                    )

            # Fetch the OpenAI response
            try:
                resp = await convo.continue_thread()
                logger.debug(
                    "Thread %s got OpenAI response: %s", message.channel.name, resp
                )
            except APIError as e:
                logger.exception(
                    "Got an error while trying to get a conversation response"
                )

                try:
                    await response_thread.send(
                        f"---\nError while getting a conversation response:\n```{repr(e)}```"
                    )
                except Exception:
                    logger.exception(
                        "Got an error trying to talk to Discord when complaining about a conversation response!"
                    )

                return

            # Look up Magic cards
            embeds = None
            if bot_config.scryfall.enabled:
                embeds = await get_mtg_embeds_from_message(resp)

            # Trim response to fit in Discord's 2000 character limit. The convo still contains the whole message.
            # short_resp = textwrap.shorten(resp, width=2000, placeholder="...") # this removes whitespace
            short_resp = (resp[:1996] + "...") if len(resp) > 1999 else resp

            msg = await response_thread.send(
                short_resp,
                allowed_mentions=discord.AllowedMentions.none(),
                embeds=embeds,
            )
            convo.add(msg, full_text=resp)

            logger.debug("Thread %s was updated", message.channel.name)
