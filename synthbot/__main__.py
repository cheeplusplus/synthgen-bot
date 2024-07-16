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
        for key in logging.Logger.manager.loggerDict:
            if key.startswith("synthbot"):
                logging.getLogger(key).setLevel(logging.DEBUG)


setup_logger()

client.run(bot_config.discord.token, log_handler=None)
