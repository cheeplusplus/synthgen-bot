from attrs import define, field
import cattrs
import yaml
from typing import Optional


@define
class BotConfig:
    debug: bool = field(default=False)


@define
class DiscordConfig:
    token: str
    doing: str
    default_thread_title: Optional[str] = field(default="Synthbot reply")
    allowed_channels: Optional[list[int]] = field(default=None)
    admin_users: Optional[list[int]] = field(default=None)


@define
class OpenAIConfig:
    api_key: str
    model: Optional[str] = field(default="gpt-3.5-turbo")
    thread_token_limit: Optional[int] = field(default=None)
    reply_token_limit: Optional[int] = field(default=512)


@define
class ScryfallConfig:
    enabled: bool = field(default=True)


@define
class SynthbotConfig:
    discord: DiscordConfig
    openai: OpenAIConfig
    bot: BotConfig = field(default=BotConfig())
    scryfall: ScryfallConfig = field(default=ScryfallConfig())


def get_config() -> SynthbotConfig:
    with open("config.yaml", "r") as f:
        config = yaml.safe_load(f)
        return cattrs.structure(config, SynthbotConfig)


bot_config = get_config()
