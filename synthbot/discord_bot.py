import discord
import discordhealthcheck
import logging

from .config import bot_config
from .core import SynthbotCore


logger = logging.getLogger(__name__)

intents = discord.Intents.default()
intents.message_content = True


class SynthbotClient(discord.Client):
    botcore: SynthbotCore

    def __init__(self):
        super().__init__(intents=intents)
        self.botcore = SynthbotCore(self)

    async def setup_hook(self):
        self.healthcheck_server = await discordhealthcheck.start(self)


client = SynthbotClient()


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
        await client.botcore.on_dm_message(message)
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

        await client.botcore.on_channel_message(message)
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

        await client.botcore.on_thread_message(message)
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
