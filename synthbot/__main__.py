import logging
import logging.handlers
import sys

from .config import bot_config
from .discord_bot import client


def setup_logger():
    logger = logging.getLogger()
    formatter = logging.Formatter(
        "[{asctime}] [{levelname:<8}] {name}: {message}", "%Y-%m-%d %H:%M:%S", style="{"
    )
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    if "--debug" in sys.argv or bot_config.bot.debug:
        # Is there a better way to do this???
        logging.getLogger("synthbot.discord_bot").setLevel(logging.DEBUG)
        logging.getLogger("synthbot.openai_conversation").setLevel(logging.DEBUG)
        logging.getLogger("synthbot.scryfall").setLevel(logging.DEBUG)


setup_logger()

client.run(bot_config.discord.token, log_handler=None)
