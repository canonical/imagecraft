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

from copy import deepcopy
from typing import Any, Dict

from craft_application import Application, AppMetadata, util
from overrides import override

from imagecraft.project import Project


APP_METADATA = AppMetadata(
    name="imagecraft",
    summary="A tool to create Ubuntu bootable images",
    ProjectClass=Project,
)


class Imagecraft(Application):
    """Imagecraft application definition"""

    @override
    def _configure_services(
        self,
        platform: str | None,
        build_for: str | None
    ) -> None:
        super()._configure_services(platform, build_for)
        if build_for is None:
            build_for = util.get_host_architecture()

        self.services.set_kwargs(
            "package",
            platform=platform,
            build_for=build_for,
        )
        self.services.set_kwargs(
            "lifecycle",
            cache_dir=self.cache_dir,
            work_dir=self._work_dir,
            platform=platform,
            build_for=build_for,
        )

    @override
    def _extra_yaml_transform(
        self,
        yaml_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        # TODO: Apply extensions to the yaml

        # The method documentation says to return a new yaml dict
        new_yaml = deepcopy(yaml_data)

        # Make sure not to stage or prime the gadget, as it should not be
        # part of the rootfs - if the gadget is defined in the project.
        if "gadget" in new_yaml["parts"]:
            gadget = new_yaml["parts"]["gadget"]
            gadget["override-stage"] = "true"
            gadget["override-prime"] = "true"

        return new_yaml
