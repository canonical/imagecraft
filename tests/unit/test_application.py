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

from pathlib import Path

IMAGECRAFT_YAML = """
name: ubuntu-server-amd64
version: "1"
base: bare
build-base: ubuntu@22.04
platforms:
  amd64:
    build-for: [amd64]
    build-on: [amd64]
"""


def test_application(new_dir, default_application):
    project_file = Path(new_dir) / "imagecraft.yaml"
    project_file.write_text(IMAGECRAFT_YAML)

    project = default_application.project

    assert project.base == "bare"
    assert project.build_base == "ubuntu@22.04"
