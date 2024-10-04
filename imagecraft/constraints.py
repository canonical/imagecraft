# This file is part of imagecraft.
#
# Copyright 2023 Canonical Ltd.
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

import collections
from typing import Annotated, TypeVar

from pydantic import AfterValidator, Field

T = TypeVar("T")


def _validate_list_is_unique(value: list[T]) -> list[T]:
    value_set = set(value)
    if len(value_set) == len(value):
        return value
    dupes = [item for item, count in collections.Counter(value).items() if count > 1]
    raise ValueError(f"duplicate values in list: {dupes}")


UniqueList = Annotated[
    list[T],
    AfterValidator(_validate_list_is_unique),
    Field(json_schema_extra={"uniqueItems": True}),
]
