import discord
import discordhealthcheck
from openai import APIError
import logging

from .config import bot_config
from .scryfall import get_mtg_embeds_from_message
from .openai_conversation import OpenaiConversation, summarize


logger = logging.getLogger(__name__)


class SynthbotClient(discord.Client):
    async def setup_hook(self):
        self.healthcheck_server = await discordhealthcheck.start(self)


intents = discord.Intents.default()
intents.message_content = True

client = SynthbotClient(intents=intents)


# Cache thread IDs to an OpenAI conversation
THREAD_CONVO_CACHE: dict[int, OpenaiConversation] = {}


@client.event
async def on_ready():
    logger.info("Logged in as %s", client.user)
    await client.change_presence(
        status=discord.Status.online,
        activity=discord.Activity(
            type=discord.ActivityType.listening, name="a stream of tokens"
        ),
    )


@client.event
async def on_message(message: discord.Message):
    if message.author == client.user or message.author.bot:
        # It's either from ourselves or another bot, ignore it
        return

    if not message.content:
        # Don't have permission to see it, or some other issue
        return

    new_thread = False
    response_thread = None
    if not message.guild:
        # DM
        logger.debug("Got direct message from %s: %s", message.author, message.content)

        if not bot_config.discord.admin_users or message.author.id not in bot_config.discord.admin_users:
            await message.channel.send("Hello! I am Synthgen GPT, your friendly robot friend.")
            return

        await message.channel.send("Hello! I am Synthgen GPT, your personal synth assistant.")
        return

    elif isinstance(message.channel, discord.TextChannel) and client.user.mentioned_in(
        message
    ):
        if (
            bot_config.discord.allowed_channels
            and message.channel.id not in bot_config.discord.allowed_channels
        ):
            # We're not allowed to use this channel
            return

        # User mentioned us, create a thread with our reply

        logger.debug(
            "Got tagged message in %s from %s: %s",
            message.channel.name,
            message.author,
            message.content,
        )

        new_thread = True
        response_thread = await message.create_thread(
            name="Synthbot reply",
            auto_archive_duration=1440,
            reason="ChatGPT conversation",
        )
    elif (
        isinstance(message.channel, discord.Thread)
        and message.channel.owner == client.user
        and message.type == discord.MessageType.default
    ):
        # User replied to a thread we created

        logger.debug(
            "Got reply in thread %s from %s: %s",
            message.channel.name,
            message.author,
            message.content,
        )

        response_thread = message.channel
    else:
        # Channel type not supported
        logger.warn(
            "Got an unsupported message [type: %s, channel: %s, author: %s]: %s",
            message.type,
            message.channel,
            message.author,
            message.content,
        )
        return

    async with response_thread.typing():
        # Build the OpenAI conversation
        convo = None

        # Clean up the incoming content
        content = message.content.replace(client.user.mention, "").strip()

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

        if response_thread.id in THREAD_CONVO_CACHE:
            convo = THREAD_CONVO_CACHE[response_thread.id]
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
                    "Thread %s is loading conversation history...", message.channel.name
                )
                await load_thread_conversation(convo, response_thread)
            THREAD_CONVO_CACHE[response_thread.id] = convo

        # Fetch the OpenAI response
        try:
            resp = await convo.get_response()
            logger.debug(
                "Thread %s got OpenAI response: %s", message.channel.name, resp
            )
        except APIError as e:
            logger.exception("Got an error while trying to get a conversation response")

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


async def load_thread_conversation(convo: OpenaiConversation, thread: discord.Thread):
    # This really needs to be some dynamic thing where we walk backwards to the max token limit
    async for message in thread.history(limit=100, oldest_first=True):
        if message.type not in [
            discord.MessageType.thread_starter_message,
            discord.MessageType.default,
            discord.MessageType.reply,
        ]:
            # Ignore other message types (thread renames, etc)
            logger.debug(
                "Ignored thread event [name: %s, type: %s, author: %s]: %s",
                thread.name,
                message.type,
                message.author,
                message.system_content,
            )
            pass
        elif (
            message.type == discord.MessageType.thread_starter_message
            and message.reference
            and isinstance(message.reference.resolved, discord.Message)
        ):
            # Initial thread message - this looks like a bot message but it refers to the original
            # discordpy just doesn't handle this correctly apparently
            logger.debug(
                "Thread loaded initial user message [name: %s, type: %s, author: %s]: %s",
                thread.name,
                message.type,
                message.author,
                message.system_content,
            )
            cleaned_msg = message.reference.resolved.content.replace(
                client.user.mention, ""
            ).strip()
            convo.add_user_message(cleaned_msg)
        elif not message.content:
            # Ignore empty messages after this point
            logger.debug(
                "Ignored thread load [name: %s, type: %s, author: %s]: %s",
                thread.name,
                message.type,
                message.author,
                message.content,
            )
            pass
        elif message.author == client.user:
            # Reply from us (bot)
            logger.debug(
                "Thread loaded bot message [name: %s, type: %s, author: %s]: %s",
                thread.name,
                message.type,
                message.author,
                message.content,
            )
            convo.add_assistant_message(message.clean_content)
        elif message.author.bot:
            # Reply from other bot
            logger.debug(
                "Thread ignored bot message [name: %s, type: %s, author: %s]: %s",
                thread.name,
                message.type,
                message.author,
                message.content,
            )
            # Ignore other bot's messages
            pass
        else:
            # Reply from user
            logger.debug(
                "Thread loaded user message [name: %s, type: %s, author: %s]: %s",
                thread.name,
                message.type,
                message.author,
                message.content,
            )
            convo.add_user_message(message.clean_content)
