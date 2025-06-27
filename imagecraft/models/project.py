# This file is part of imagecraft.
#
# Copyright 2023-2025 Canonical Ltd.
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

"""Imagecraft project definition.

This module defines a imagecraft.yaml file, exportable to a JSON schema.
"""

import typing
from typing import Annotated, Any, Literal, Self

from craft_application.errors import CraftValidationError
from craft_application.models import CraftBaseModel
from craft_application.models import Platform as BasePlatform
from craft_application.models import Project as BaseProject
from craft_providers import bases
from pydantic import (
    AfterValidator,
    ConfigDict,
    Field,
    model_validator,
)
from typing_extensions import override

from imagecraft.models.volume import (
    StructureItem,
    Volume,
    VolumeName,
)


class Platform(BasePlatform):
    """Imagecraft project platform definition."""

    @model_validator(mode="after")  # pyright: ignore[reportUntypedFunctionDecorator]
    def _validate_platform_set(self) -> Self:
        """Validate the build_on build_for combination."""
        build_on: list[str] | str = self.build_on if self.build_on else []

        # We can only build on 1 arch at the moment
        if len(build_on) > 1:
            raise CraftValidationError(
                str(
                    f"Trying to build an image on {build_on} "
                    "but multiple architectures are not "
                    "currently supported. Please specify only 1 value.",
                ),
            )

        return self


BaseT = Literal["bare"]
BuildBaseT = typing.Annotated[
    Literal["ubuntu@20.04", "ubuntu@22.04", "ubuntu@24.04", "devel"] | None,
    Field(
        validate_default=True,
        description="The build environment to use when building the image.",
        examples=["ubuntu@22.04", "ubuntu@24.04"],
    ),
]


VolumeDictT = Annotated[dict[VolumeName, Volume], Field(min_length=1, max_length=1)]


def _validate_filesystem(filesystem: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Validate a filesystem item.

    :param filesystem: a list representing a filesystem.
    :returns: That same list, if valid.
    :raises: ValueError if the filesystem is not valid.
    """
    # This check is not always used, import it here to avoid unnecessary import
    from craft_parts.filesystem_mounts import (  # noqa: PLC0415
        validate_filesystem_mount,  # type: ignore[import-untyped]
    )

    validate_filesystem_mount(filesystem)
    return filesystem


FilesystemsDictT = Annotated[
    dict[
        str,
        Annotated[
            list[dict[str, Any]],
            Field(min_length=1),
            AfterValidator(_validate_filesystem),
        ],
    ],
    Field(min_length=1, max_length=1),
]


class Project(BaseProject):
    """Definition of imagecraft.yaml configuration."""

    base: BaseT = Field(  # type: ignore[reportIncompatibleVariableOverride]
        description="The base layer the image is built on.",
        examples=["bare"],
    )
    """The base layer the image is built on.

    The value ``bare`` denotes that the project will start with an empty directory and,
    if overlays are used, an empty base layer.
    """

    build_base: BuildBaseT  # type: ignore[reportIncompatibleVariableOverride]
    """The build base determines the image's build environment. This system and version
    will be used when assembling the image's contents, but will not be included in the
    final image.

    **Values**

    .. list-table::
        :header-rows: 1

        * - Value
          - Description
        * - ``ubuntu@20.04``
          - The Ubuntu 20.04 build environment.
        * - ``ubuntu@22.04``
          - The Ubuntu 22.04 build environment.
        * - ``ubuntu@24.04``
          - The Ubuntu 24.04 build environment.

    """

    volumes: VolumeDictT = Field(
        description="The structure and properties of the image.",
        examples=[
            "{pc: {schema: gpt, structure: [{name: efi, type: C12A7328-F81F-11D2-BA4B-00A0C93EC93B, filesystem: vfat, role: system-boot, filesystem-label: UEFI, size: 256M}, {name: rootfs, type: 0FC63DAF-8483-4772-8E79-3D69D8477DE4, filesystem: ext4, filesystem-label: writable, role: system-data, size: 5G}]}}"
        ],
    )
    """The structure and properties of the image.

    This key expects a single entry defining the image's schema and partitions.
    """

    filesystems: FilesystemsDictT = Field(
        description="A mapping of where partitions are mounted in the filesystem.",
        examples=[
            "{default: [{mount: /, device: (default)}, {mount: /boot/efi, device: (volume/pc/efi)}]}",
        ],
    )
    """The mapping of the image's partitions to mount points.

    This mapping can only contain a single filesystem, named ``default``. The first
    entry of ``default`` must map a partition to the ``/`` mount point.
    """

    model_config = ConfigDict(
        validate_assignment=True,
        extra="forbid",
        frozen=False,
        populate_by_name=True,
    )

    @override
    @classmethod
    def _providers_base(cls, base: str) -> bases.BaseAlias | None:
        """Get a BaseAlias from imagecraft's base.

        :param base: The base name.

        :returns: Always None because imagecraft only supports bare bases.
        """
        return None

    def get_partitions(self) -> list[str]:
        """Get a list of partitions based on the project's volumes.

        :returns: A list of partitions formatted as ['default', 'volume/<name>', ...]
        """
        return _get_partitions(self.volumes, self.filesystems)


class VolumeFilesystemMountsProject(CraftBaseModel, extra="ignore"):
    """Project definition containing only volumes and filesystems data."""

    volumes: VolumeDictT
    filesystems: FilesystemsDictT

    def get_partitions(self) -> list[str]:
        """Get a list of partitions based on the project's volumes.

        :returns: A list of partitions formatted as ['default', 'volume/<name>', ...]
        """
        return _get_partitions(self.volumes, self.filesystems)


def get_partition_name(volume_name: str, structure: StructureItem) -> str:
    """Get the name of the partition associated to the StructureItem."""
    return f"volume/{volume_name}/{structure.name}"


def _get_partitions(
    volumes_data: dict[str, Any],
    filesystems: dict[str, Any],
) -> list[str]:
    """Get a list of partitions based on the project's volumes.

    :returns: A list of partitions formatted as ['foo', 'volume/<name>', ...]
    """
    default_alias = _get_alias_to_default(filesystems)
    partitions: list[str] = [default_alias]

    for volume_name, volume in volumes_data.items():
        for structure in volume.structure:
            name = get_partition_name(volume_name, structure)
            if name != default_alias:
                partitions.append(name)
    return partitions


def _get_alias_to_default(filesystems: dict[str, Any]) -> str:
    """Get the alias to the default partition defined in the Filesystems."""
    default_alias = "default"
    default_filesystem_mount: list[dict[str, Any]] | None = filesystems.get("default")
    if default_filesystem_mount is None:
        return default_alias

    alias = default_filesystem_mount[0].get("device", default_alias)

    return str(alias).strip("()")
