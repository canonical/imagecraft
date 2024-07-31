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
series: jammy
platforms:
  amd64:
    build-for: [amd64]
    build-on: [amd64]
package-repositories:
  - type: apt
    components: [main,restricted]
    url: http://archive.ubuntu.com/ubuntu/
    flavor: ubuntu
    series: jammy
    pocket: proposed
    used-for: build
  - type: apt
    components: [restricted,universe]
    pocket: updates
    used-for: run
parts:
  gadget:
    plugin: gadget
    source: https://github.com/snapcore/pc-gadget.git
    source-branch: classic
  rootfs:
    plugin: ubuntu-seed
    ubuntu-seed-germinate:
      urls:
        - "git://git.launchpad.net/~ubuntu-core-dev/ubuntu-seeds/+git/"
      branch: jammy
      names:
        - server
        - minimal
        - standard
        - cloud-image
    ubuntu-seed-pocket: updates
    ubuntu-seed-extra-snaps: [core20, snapd]
    ubuntu-seed-kernel: linux-generic
    stage:
      - -etc/cloud/cloud.cfg.d/90_dpkg.cfg
"""

IMAGECRAFT_YAML_NO_GADGET = """
name: ubuntu-server-amd64
version: "1"
series: jammy
platforms:
  amd64:
    build-for: [amd64]
    build-on: [amd64]

parts:
  rootfs:
    plugin: ubuntu-seed
    ubuntu-seed-germinate:
      names:
        - server
        - minimal
        - standard
        - cloud-image
      urls:
        - "git://git.launchpad.net/~ubuntu-core-dev/ubuntu-seeds/+git/"
      branch: jammy
    ubuntu-seed-pocket: updates
    ubuntu-seed-extra-snaps: [core20, snapd]
    ubuntu-seed-kernel: linux-generic
"""


def test_application(default_application, new_dir):
    project_file = Path(new_dir) / "imagecraft.yaml"
    project_file.write_text(IMAGECRAFT_YAML)

    project = default_application.project

    assert (
        project.parts["gadget"].get("source")
        == "https://github.com/snapcore/pc-gadget.git"
    )


def test_application_no_gadget(default_application, new_dir):
    project_file = Path(new_dir) / "imagecraft.yaml"
    project_file.write_text(IMAGECRAFT_YAML_NO_GADGET)

    project = default_application.project

    assert project.parts["rootfs"].get("ubuntu-seed-germinate").get("branch") == "jammy"
