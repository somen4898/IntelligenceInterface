import pathlib

import yaml


def execute(command: str | None = None) -> dict:
    """Return structured YAML documentation for ii-structure commands.

    With no argument, returns the full help content. Pass a command name
    to get documentation for that specific command only.
    """
    help_path = pathlib.Path(__file__).parent.parent / "help_content.yaml"
    content = yaml.safe_load(help_path.read_text())

    if command is None:
        return content

    commands = content.get("commands", {})
    if command in commands:
        return {"command": command, **commands[command]}

    return None  # signal not found
