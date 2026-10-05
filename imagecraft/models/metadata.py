# Copyright 2026 Canonical Ltd.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Image metadata models."""

from craft_application.models import CraftBaseModel


class VolumeMetadata(CraftBaseModel):
    """Volume metadata entry."""

    format: str


class ImageMetadata(CraftBaseModel):
    """Image metadata payload."""

    name: str
    base: str
    build_base: str | None = None
    platform: str
    architecture: str
    volumes: dict[str, VolumeMetadata]
    title: str | None = None
    version: str | None = None
    summary: str | None = None
    description: str | None = None
    contact: list[str] | None = None
    issues: list[str] | None = None
    source_code: str | None = None
