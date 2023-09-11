from .config import bot_config
from .discord_bot import client

client.run(bot_config.discord.token)
