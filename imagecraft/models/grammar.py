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

import pydantic
from craft_application.models.base import alias_generator
from craft_grammar.models import Grammar  # type: ignore[import-untyped]
from pydantic import ConfigDict, Field


class _GrammarAwareModel(pydantic.BaseModel):
    model_config = ConfigDict(
        validate_assignment=True,
        extra="allow",
        alias_generator=alias_generator,
        populate_by_name=True,
    )


class _GrammarAwareStructureItem(_GrammarAwareModel):
    name: Grammar[str] | None = None
    id: Grammar[str] | None = None
    role: Grammar[str] | None = None
    structure_type: Grammar[str] | None = None
    size: Grammar[str] | None = None
    filesystem: Grammar[str] | None = None
    filesystem_label: Grammar[str] | None = None


class _GrammarAwareVolume(_GrammarAwareModel):
    volume_schema: Grammar[str] | None = Field(None, alias="schema")
    structure: Grammar[list[_GrammarAwareStructureItem]] | None = None


def get_grammar_aware_volume_keywords() -> list[str]:
    """Return all supported grammar keywords for a volume."""
    keywords: list[str] = [
        item.alias or name for name, item in _GrammarAwareVolume.model_fields.items()
    ]
    return keywords
