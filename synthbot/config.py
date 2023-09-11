import typing
import yaml


def get_config() -> dict[str, typing.Any]:
    with open("config.yaml", "r") as f:
        config = yaml.safe_load(f)
        return config


bot_config = get_config()
