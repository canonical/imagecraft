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

"""Command-line application entry point."""

from typing import Any

from craft_cli import Dispatcher

from imagecraft.application import Imagecraft
from imagecraft.services.service_factory import ImagecraftServiceFactory


def run() -> int:
    """Command-line interface entrypoint."""
    app = _create_app()

    return app.run()


def _create_app() -> Imagecraft:
    # pylint: disable=import-outside-toplevel
    # Import these here so that the script that generates the docs for the
    # commands doesn't need to know *too much* of the application.
    from .application import APP_METADATA, Imagecraft

    services = ImagecraftServiceFactory(
        app=APP_METADATA,
    )  # type: ignore[assignment]

    return Imagecraft(app=APP_METADATA, services=services)


def get_app_info() -> tuple[Dispatcher, dict[str, Any]]:
    """Retrieve application info. Used by craft-cli's completion module."""
    app = _create_app()
    dispatcher = app._create_dispatcher()  # noqa: SLF001 (private member access)  # pyright: ignore[reportPrivateUsage]

    return dispatcher, app.app_config
