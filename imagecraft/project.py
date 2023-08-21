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

from typing import TYPE_CHECKING, Any, Dict, List, Optional
from pydantic import BaseModel, ValidationError, validator, conlist

# A workaround for mypy false positives
# see https://github.com/samuelcolvin/pydantic/issues/975#issuecomment-551147305
# fmt: off
if TYPE_CHECKING:
    UniqueStrList = List[str]
else:
    UniqueStrList = conlist(str, unique_items=True, min_items=1)


class ProjectModel(BaseModel):
    """Base model for the imagecraft project class."""

    class Config:
        validate_assignment = True
        extra = "forbid"
        allow_mutation = True
        allow_population_by_field_name = True
        alias_generator = lambda s: s.replace("_", "-")


class Gadget(ProjectModel):
    source: str
    gadget_target: Optional[str]


class Platform(ProjectModel):
    build_on: UniqueStrList
    build_for: UniqueStrList
    extensions: UniqueStrList = []
    gadget: Optional[Gadget]
    fragments: UniqueStrList = []


class Project(ProjectModel):
    name: str
    version: str
    base: str
    build_base: Optional[str]  # this == base if not set

    platforms: Dict[str, Platform]

    parts: Dict[str, Any]  # parts are handled by craft-parts

    @classmethod
    def unmarshal(cls, data):
        if not isinstance(data, dict):
            raise TypeError("Project data is not a dictionary")

        try:
            project = Project(**data)
        except ValidationError as err:
            # TODO: proper error handling
            raise err

        return project

    @validator("platforms", pre=True, always=True)
    @classmethod
    def _apply_dynamic_default(cls, platforms):
        # TODO: handle build-on and build-for defaults
        return platforms
    
    def select_platforms(self, requested_platforms, build_on):
        platforms = []
        if not requested_platforms:
            requested_platforms = self.platforms.keys()
        print(requested_platforms)
        print(platforms)
        for label, platform in self.platforms.items():
            print(label)
            if label in requested_platforms or not label:
                print(platform.build_on)
                print(build_on)
                if set(build_on) <= set(platform.build_on):
                    platforms.append((label, platform))

        return platforms
