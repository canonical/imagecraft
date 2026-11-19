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

"""Unit tests for ImagecraftProviderService."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest import mock

import craft_platforms
from craft_application import ServiceFactory
from imagecraft.application import APP_METADATA
from imagecraft.services.provider import (
    MANAGED_GADGET_CACHE_PATH,
    ImagecraftProviderService,
)

if TYPE_CHECKING:
    import pathlib


def test_provider_service_mounts_gadget_cache(tmp_path: pathlib.Path, monkeypatch):
    cache_home = tmp_path / "cache"
    monkeypatch.setenv("XDG_CACHE_HOME", str(cache_home))

    work_dir = tmp_path / "work"
    work_dir.mkdir()

    services = ServiceFactory(app=APP_METADATA)
    provider_service = ImagecraftProviderService(
        app=APP_METADATA,
        services=services,
        work_dir=work_dir,
    )

    mock_instance = mock.Mock()
    mock_provider = mock.Mock()
    mock_provider.launched_environment.return_value.__enter__ = mock.Mock(
        return_value=mock_instance
    )
    mock_provider.launched_environment.return_value.__exit__ = mock.Mock(
        return_value=False
    )

    monkeypatch.setattr(
        provider_service, "get_provider", mock.Mock(return_value=mock_provider)
    )
    monkeypatch.setattr(provider_service, "get_base", mock.Mock())
    monkeypatch.setattr(
        provider_service,
        "_get_instance_name",
        mock.Mock(return_value="test-instance"),
    )
    monkeypatch.setattr(provider_service, "_setup_instance_bashrc", mock.Mock())
    monkeypatch.setattr(provider_service, "_capture_logs_from_instance", mock.Mock())

    mock_state = mock.Mock()
    mock_config = mock.Mock()
    mock_config.get.return_value = None
    monkeypatch.setattr(
        services,
        "get",
        mock.Mock(
            side_effect=lambda name: mock_state if name == "state" else mock_config
        ),
    )

    build_info = craft_platforms.BuildInfo(
        platform="amd64",
        build_on=craft_platforms.DebianArchitecture.AMD64,
        build_for=craft_platforms.DebianArchitecture.AMD64,
        build_base=craft_platforms.DistroBase("ubuntu", "24.04"),
    )

    with provider_service.instance(
        build_info, work_dir=work_dir, project_name="test-project"
    ) as inst:
        assert inst is mock_instance

    expected_cache = cache_home / "imagecraft" / "gadgets"
    assert expected_cache.is_dir()
    mock_instance.mount.assert_any_call(
        host_source=expected_cache,
        target=MANAGED_GADGET_CACHE_PATH,
    )
