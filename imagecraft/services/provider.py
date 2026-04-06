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

"""Imagecraft provider service."""

import contextlib
import os
import pathlib
from collections.abc import Generator
from typing import Any

import craft_platforms
import craft_providers
from craft_application.services.provider import ProviderService
from craft_cli import CraftError, emit
from craft_providers.lxd import LXDInstance, LXDProvider


class Provider(ProviderService):
    """Imagecraft-specific project service."""

    @contextlib.contextmanager
    def instance(
        self,
        build_info: craft_platforms.BuildInfo,
        *,
        work_dir: pathlib.Path,
        **kwargs: Any,
    ) -> Generator[craft_providers.Executor, None, None]:
        """Context manager for a provider instance.

        When using the LXD provider, also mounts $SNAP_DATA/losetup into
        /dev/losetup inside the instance so the losetup server socket is
        accessible.
        """
        with super().instance(build_info, work_dir=work_dir, **kwargs) as instance:
            if isinstance(self.get_provider(), LXDProvider) and isinstance(
                instance, LXDInstance
            ):
                snap_data = os.environ.get("SNAP_DATA", "")
                if snap_data:
                    losetup_host = pathlib.Path(snap_data) / "losetup"
                    losetup_host.mkdir(parents=True, exist_ok=True)
                    self._mount_with_shift(instance, losetup_host)
                    emit.debug(f"Mounted {losetup_host} -> /dev/losetup in instance")
                else:
                    emit.debug("SNAP_DATA not set; skipping losetup mount")
            yield instance

    @staticmethod
    def _mount_with_shift(instance: LXDInstance, host_source: pathlib.Path) -> None:
        """Mount host_source into /dev/losetup in the instance with UID/GID shifting.

        Uses pylxd directly to set shift=true, which remaps host UIDs/GIDs into
        the container's namespace so the directory appears owned by root inside.
        """
        device_name = "disk-dev-losetup"
        target = "/dev/losetup"
        lxd_inst = instance._client.instances.get(instance.instance_name)
        if device_name not in lxd_inst.devices:
            lxd_inst.devices[device_name] = {
                "type": "disk",
                "source": str(host_source),
                "path": target,
                "shift": "true",
            }
            lxd_inst.save(wait=True)

    def get_provider(self, name: str | None = None) -> craft_providers.Provider:
        """Get the provider to use. This method is a workaround for #253.

        :param name: if set, uses the given provider name.

        The provider is determined in the following order:
        (1) use provider specified in the function argument,
        (2) get the provider from the environment (CRAFT_BUILD_ENVIRONMENT),
        (3) use provider specified with snap configuration,
        (4) default to platform default (LXD on Linux, otherwise Multipass).

        :returns: The Provider to use.

        :raises CraftError: If already running in managed mode.
        """
        if self._provider is not None:
            return self._provider

        if self.is_managed():
            raise CraftError("Cannot nest managed environments.")

        # (1) use provider specified in the function argument,
        if name:
            emit.debug(f"Using provider {name!r} passed as an argument.")
            chosen_provider: str = name

        # (2) get the provider from build_environment
        elif provider := self._services.config.get("build_environment"):
            emit.debug(f"Using provider {provider!r} from system configuration.")
            chosen_provider = provider

        # (3) use provider specified in snap configuration
        elif snap_provider := self._get_provider_from_snap_config():
            emit.debug(f"Using provider {snap_provider!r} from snap config.")
            chosen_provider = snap_provider

        # (4) Use multipass as a workaround for #253
        # https://github.com/canonical/imagecraft/issues/253
        else:
            emit.debug("Using default provider 'multipass'.")
            chosen_provider = "multipass"

        self._provider = self._get_provider_by_name(chosen_provider)
        return self._provider
