from attrs import define, field
import cattrs
import yaml


@define
class DiscordConfig:
    token: str
    doing: str
    allowed_channels: list[int] = field(default=None)


@define
class OpenAIConfig:
    api_key: str
    model: str


@define
class ScryfallConfig:
    enabled: bool = field(default=True)


@define
class SynthbotConfig:
    discord: DiscordConfig
    openai: OpenAIConfig
    scryfall: ScryfallConfig = field(default=ScryfallConfig())


def get_config() -> SynthbotConfig:
    with open("config.yaml", "r") as f:
        config = yaml.safe_load(f)
        return cattrs.structure(config, SynthbotConfig)


bot_config = get_config()
