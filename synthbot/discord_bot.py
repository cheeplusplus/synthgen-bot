import discord
import discordhealthcheck
import logging

from .config import bot_config
from .core import SynthbotCore


logger = logging.getLogger(__name__)


class SynthbotClient(discord.Client):
    async def setup_hook(self):
        self.healthcheck_server = await discordhealthcheck.start(self)


intents = discord.Intents.default()
intents.message_content = True

client = SynthbotClient(intents=intents)

botcore = SynthbotCore(client)


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

    if not message.guild:
        # Direct message
        logger.debug("Got direct message from %s: %s", message.author, message.content)
        await botcore.on_dm_message(message)
        return

    elif isinstance(message.channel, discord.TextChannel) and client.user.mentioned_in(
        message
    ):
        # Bot sent a message to a text channel and mentioned us
        if (
            bot_config.discord.allowed_channels
            and message.channel.id not in bot_config.discord.allowed_channels
        ):
            # We're not allowed to use this channel
            return

        logger.debug(
            "Got tagged message in %s from %s: %s",
            message.channel.name,
            message.author,
            message.content,
        )

        await botcore.on_channel_message(message)
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

        await botcore.on_thread_message(message)
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
