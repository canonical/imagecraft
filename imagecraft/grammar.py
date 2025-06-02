# This file is part of imagecraft.
#
# Copyright 2025 Canonical Ltd.
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 3, as published
# by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranties of MERCHANTABILITY,
# SATISFACTORY QUALITY, or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Grammar processor."""

from typing import Any, cast

import craft_cli
from craft_application.errors import CraftValidationError
from craft_grammar import GrammarProcessor  # type: ignore[import-untyped]
from craft_grammar.errors import GrammarSyntaxError  # type: ignore[import-untyped]

from imagecraft.models import get_grammar_aware_volume_keywords

# Values that should return as a single object / list / dict.
_NON_SCALAR_VALUES = [
    "structure",
]

# Values that should return a dict, not in a list.
_DICT_ONLY_VALUES: list[str] = []


def _self_check(value: Any) -> bool:  # noqa: ANN401
    return bool(
        value == value  # pylint: disable=comparison-with-itself  # noqa: PLR0124
    )


def process_volumes(
    *, volumes_yaml_data: dict[str, Any], arch: str, target_arch: str
) -> dict[str, Any]:
    """Process grammar for volumes.

    :param yaml_data: unprocessed volumes section of imagecraft.yaml.
    :returns: processed volumes section of imagecraft.yaml.
    """
    # TODO: make checker optional in craft-grammar.  # noqa: FIX002
    processor = GrammarProcessor(
        arch=arch, target_arch=target_arch, checker=_self_check
    )

    for volume_name, volume_data in volumes_yaml_data.items():
        volumes_yaml_data[volume_name] = process_volume(
            volume_yaml_data=volume_data, processor=processor
        )

    return volumes_yaml_data


def process_volume(
    *, volume_yaml_data: dict[str, Any], processor: GrammarProcessor
) -> dict[str, Any]:
    """Process grammar for a given volume."""
    for key, volume_data in volume_yaml_data.items():
        unprocessed_grammar = volume_data

        # ignore non-grammar keywords
        if key not in get_grammar_aware_volume_keywords():
            craft_cli.emit.debug(
                f"Not processing grammar for non-grammar enabled keyword {key}"
            )
            continue

        craft_cli.emit.debug(f"Processing grammar for {key}: {unprocessed_grammar}")
        # grammar aware models can be strings or list of dicts and strings
        if isinstance(unprocessed_grammar, list):
            # all items in the list must be a dict or a string
            if any(not isinstance(d, dict | str) for d in unprocessed_grammar):  # type: ignore[reportUnknownVariableType]
                continue

            # all keys in the dictionary must be a string
            for item in unprocessed_grammar:  # type: ignore[reportUnknownVariableType]
                if isinstance(item, dict) and any(
                    not isinstance(key, str)
                    for key in item  # type: ignore[reportUnknownVariableType]
                ):
                    continue

            unprocessed_grammar = cast(list[dict[str, Any] | str], unprocessed_grammar)
        # grammar aware models can be a string
        elif isinstance(unprocessed_grammar, str):
            unprocessed_grammar = [unprocessed_grammar]
        # skip all other data types
        else:
            continue

        try:
            processed_grammar = processor.process(grammar=unprocessed_grammar)
        except GrammarSyntaxError as e:
            raise CraftValidationError(
                f"Invalid grammar syntax while processing '{key}' in '{volume_yaml_data}': {e}"
            ) from e

        # special cases:
        # - scalar values should return as a single object, not in a list.
        # - dict values should return as a dict, not in a list.
        if key not in _NON_SCALAR_VALUES or key in _DICT_ONLY_VALUES:
            processed_grammar = processed_grammar[0] if processed_grammar else None  # type: ignore[assignment]

        volume_yaml_data[key] = processed_grammar

    return volume_yaml_data


def process_filesystems(
    *, filesystems_yaml_data: dict[str, Any], arch: str, target_arch: str
) -> dict[str, Any]:
    """Process grammar for filesystems.

    :param filesystems_yaml_data: unprocessed filesystems section of imagecraft.yaml.
    :returns: processed filesystems section of imagecraft.yaml.
    """
    processor = GrammarProcessor(
        arch=arch, target_arch=target_arch, checker=_self_check
    )

    for filesystem_name, filesystem_data in filesystems_yaml_data.items():
        filesystems_yaml_data[filesystem_name] = process_filesystem(
            filesystem_yaml_data=filesystem_data, processor=processor
        )

    return filesystems_yaml_data


def process_filesystem(
    *, filesystem_yaml_data: list[dict[str, Any]], processor: GrammarProcessor
) -> list[dict[str, Any]]:
    """Process grammar for a filesystem.

    :param filesystem_yaml_data: unprocessed filesystem entry.
    :returns: processed filesystem entry.
    """
    craft_cli.emit.debug(f"Processing grammar for filesystem {filesystem_yaml_data}")

    unprocessed_grammar = filesystem_yaml_data
    # all items in the list must be dicts
    if any(not isinstance(d, dict) for d in unprocessed_grammar):  # type: ignore[reportUnknownVariableType]
        return filesystem_yaml_data

    # all keys in the dictionary must be a string
    for item in unprocessed_grammar:  # type: ignore[reportUnknownVariableType]
        if isinstance(item, dict) and any(  # type: ignore[reportUnnecessesaryIsInstance]
            not isinstance(key, str)  # type: ignore[reportUnnecessesaryIsInstance]
            for key in item  # type: ignore[reportUnknownVariableType]
        ):
            return filesystem_yaml_data

    try:
        processed_grammar = processor.process(grammar=unprocessed_grammar)
    except GrammarSyntaxError as e:
        raise CraftValidationError(
            f"Invalid grammar syntax while processing filesystems in '{unprocessed_grammar}': {e}"
        ) from e

    return cast(list[dict[str, Any]], processed_grammar)
