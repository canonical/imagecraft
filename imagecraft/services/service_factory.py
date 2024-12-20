# -*- Mode:Python; indent-tabs-mode:nil; tab-width:4 -*-
#
# Copyright 2023 Canonical Ltd.
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

"""Imagecraft Service Factory."""

from dataclasses import dataclass

from craft_application import ServiceFactory
from craft_application import services as base_services

from imagecraft import services


@dataclass
class ImagecraftServiceFactory(ServiceFactory):
    """Imagecraft-specific Service Factory."""

    # These are overrides of default ServiceFactory services
    LifecycleClass: type[base_services.LifecycleService] = (
        services.ImagecraftLifecycleService
    )
    PackageClass: type[base_services.PackageService] = services.ImagecraftPackService
