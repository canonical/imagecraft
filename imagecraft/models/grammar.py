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

"""Grammar-aware models."""

from typing import Any

import pydantic
from craft_application.models.base import alias_generator
from craft_grammar.models import Grammar  # type: ignore[import-untyped]
from pydantic import ConfigDict


class _GrammarAwareModel(pydantic.BaseModel):
    model_config = ConfigDict(
        validate_assignment=True,
        extra="allow",
        alias_generator=alias_generator,
        populate_by_name=True,
    )


class _GrammarAwareVolume(_GrammarAwareModel):
    structure: Grammar[list[dict[str, Any]]] | None = None


def get_grammar_aware_volume_keywords() -> list[str]:
    """Return all supported grammar keywords for a volume."""
    keywords: list[str] = [
        item.alias or name for name, item in _GrammarAwareVolume.model_fields.items()
    ]
    return keywords
