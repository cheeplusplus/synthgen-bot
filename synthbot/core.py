import discord
import logging
from openai import APIError

from .chat_thread import ChatThread
from .config import bot_config
from .scryfall import get_mtg_embeds_from_message
from .openai_conversation import OpenaiConversation, summarize

logger = logging.getLogger(__name__)


class SynthbotCore:
    client: discord.Client
    thread_cache: dict[int, ChatThread]

    def __init__(self, client: discord.Client):
        self.client = client
        self.thread_cache = {}  # TODO: Save/load to disk (redis?)

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

        await self.handle_response_thread(message, response_thread, new_thread=True)

    async def on_thread_message(self, message: discord.Message):
        """Fetch the ChatThread for this message"""

        await self.handle_response_thread(message.channel)

    async def handle_response_thread(
        self,
        message: discord.Message,
        response_thread: discord.Thread,
        new_thread: bool = False,
    ):
        """Reply to the thread"""
        async with response_thread.typing():
            # Build the OpenAI conversation
            convo = None

            # Clean up the incoming content
            content = message.content.replace(self.client.user.mention, "").strip()

            # Keep track of the thread name
            thread_name = response_thread.name

            if new_thread:
                # Summarize the first post to use as a thread title
                summary = await summarize(content)
                logger.debug(
                    "Thread %s got summarized to: %s [%d]",
                    message.channel.id,
                    summary,
                    len(summary),
                )
                await response_thread.edit(name=summary[:100])
                thread_name = summary

            if response_thread.id in self.thread_cache:
                convo = self.thread_cache[response_thread.id]
                convo.update_thread_name(thread_name)
                convo.add_user_message(content)
            else:
                convo = OpenaiConversation(
                    "You are talking to a friendly user. Keep your replies under 1800 characters. Markdown is allowed.",
                    'You are continuing a conversation in a thread called "THREAD_NAME". Keep your replies under 1800 characters. Markdown is allowed.',
                )
                convo.update_thread_name(thread_name)
                if new_thread:
                    convo.add_user_message(content)
                else:
                    logger.debug(
                        "Thread %s is loading conversation history...",
                        message.channel.name,
                    )
                    await load_thread_conversation(convo, response_thread)
                self.thread_cache[response_thread.id] = convo

            # Fetch the OpenAI response
            try:
                resp = await convo.get_response()
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

            await response_thread.send(
                short_resp,
                allowed_mentions=discord.AllowedMentions.none(),
                embeds=embeds,
            )

            logger.debug("Thread %s was updated", message.channel.name)
