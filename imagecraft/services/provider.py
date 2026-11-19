# This file is part of imagecraft.
#
# Copyright 2026 Canonical Ltd.
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

"""Imagecraft-specific provider service."""

from __future__ import annotations

import contextlib
import pathlib
from typing import TYPE_CHECKING

from craft_application.services import ProviderService
from typing_extensions import override

from imagecraft.extensions.gadget_volumes import get_gadget_cache_dir

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

    import craft_platforms
    import craft_providers

MANAGED_GADGET_CACHE_PATH = pathlib.PurePosixPath("/root/.cache/imagecraft/gadgets")


class ImagecraftProviderService(ProviderService):
    """Provider service that mounts the shared gadget cache into managed instances."""

    @override
    @contextlib.contextmanager
    def instance(
        self,
        build_info: craft_platforms.BuildInfo,
        *,
        work_dir: pathlib.Path,
        allow_unstable: bool = True,
        clean_existing: bool = False,
        use_base_instance: bool = True,
        project_name: str | None = None,
        prepare_instance: Callable[[craft_providers.Executor], None] | None = None,
        **kwargs: bool | str | None,
    ) -> Generator[craft_providers.Executor, None, None]:
        """Launch a managed instance and mount the shared gadget cache directory."""
        cache_dir = get_gadget_cache_dir()
        cache_dir.mkdir(parents=True, exist_ok=True)

        with super().instance(
            build_info,
            work_dir=work_dir,
            allow_unstable=allow_unstable,
            clean_existing=clean_existing,
            use_base_instance=use_base_instance,
            project_name=project_name,
            prepare_instance=prepare_instance,
            **kwargs,
        ) as instance:
            instance.mount(
                host_source=cache_dir,
                target=MANAGED_GADGET_CACHE_PATH,
            )
            yield instance
