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
import os
import yaml

from xdg import BaseDirectory

from craft_parts import ActionType, LifecycleManager, Step
from craft_cli import ArgumentParsingError

from imagecraft.project import Project
from imagecraft.ubuntu_image import ubuntu_image_pack
from imagecraft.utils import host_deb_arch


class ImagecraftLifecycle:

    def __init__(self, args):
        self.cache_dir = BaseDirectory.save_cache_path("imagecraft")
        self.work_dir = "."
        self.output_dir = args.output_dir if args.output_dir else "."

        self.load("imagecraft.yaml", args.platform)

    def load(self, path, platforms=None):
        with open(path, "r") as f:
            self.yaml = yaml.safe_load(f)
        if not yaml:
            raise ArgumentParsingError(
                "The specified command needs a valid 'imagecraft.yaml' configuration file (in "
                "the current directory or where specified with --project-dir option)"
            )
        parts_yaml = self.yaml.get("parts")
        if parts_yaml is None or len(parts_yaml) == 0:
            raise ArgumentParsingError(
                "The project 'imagecraft.yaml' needs to have at least one part defined"
            )
        
        # Setup the grand project object
        self.project = Project.unmarshal(self.yaml)

        # Finalize by only considering selected platforms
        self.selected_platforms = self.project.select_platforms(
            platforms, [host_deb_arch()])
        
    def parse_step(self, name):
        step_map = {
            "pull": Step.PULL,
            "overlay": Step.OVERLAY,
            "build": Step.BUILD,
            "stage": Step.STAGE,
            "prime": Step.PRIME,
        }

        return step_map.get(name, Step.PRIME)
    
    def _action_message(self, action):
        msg = {
            Step.PULL: {
                ActionType.RUN: "Pull",
                ActionType.RERUN: "Repull",
                ActionType.SKIP: "Skip pull",
                ActionType.UPDATE: "Update sources for",
            },
            Step.OVERLAY: {
                ActionType.RUN: "Overlay",
                ActionType.RERUN: "Re-overlay",
                ActionType.SKIP: "Skip overlay",
                ActionType.REAPPLY: "Reapply overlay for",
                ActionType.UPDATE: "Update overlay for",
            },
            Step.BUILD: {
                ActionType.RUN: "Build",
                ActionType.RERUN: "Rebuild",
                ActionType.SKIP: "Skip build",
                ActionType.UPDATE: "Update build for",
            },
            Step.STAGE: {
                ActionType.RUN: "Stage",
                ActionType.RERUN: "Restage",
                ActionType.SKIP: "Skip stage",
            },
            Step.PRIME: {
                ActionType.RUN: "Prime",
                ActionType.RERUN: "Re-prime",
                ActionType.SKIP: "Skip prime",
            },
        }

        message = f"{msg[action.step][action.action_type]} {action.part_name}"
        if action.reason:
            message += f" ({action.reason})"

        return message
    
    def prepare_platform(self, label, platform):
        # Add any platform-specific parts - like the gadget
        if platform.gadget:
            gadget_name = f"{label}_gadget"

            # Add the gadget part
            gadget = {
                "source": platform.gadget.source,
                "plugin": "gadget",
                # Now some overrides for steps that we do not want to happen.
                # The gadget part is special, we don't want to stage or prime
                # it. We just want to have it built and ready for image
                # creation.
                "override-stage": "true",
                "override-prime": "true",
            }
            if platform.gadget.gadget_target:
                gadget["gadget-target"] = platform.gadget.gadget_target
            if platform.gadget.source_branch:
                gadget["source-branch"] = platform.gadget.source_branch
            self.yaml["parts"][gadget_name] = gadget

        if platform.kernel:
            if platform.kernel.kernel_package:
                # Workaround until we get a better germinate plugin
                for part in self.project.parts.values():
                    if part["plugin"] == "germinate":
                        part["germinate-active-kernel"] = \
                            platform.kernel.kernel_package
            # TODO: this will be done better with a native germinate plugin
            # if platform.kernel.kernel_package:
            #     kernel_name = f"{label}_kernel"

            #     # We need to make sure the kernel is built after the rootfs
            #     # TODO: maybe we should be smarter than just finiding by the
            #     # label
            #     if "rootfs" in self.yaml["parts"]:
            #         self.yaml["parts"]["rootfs"]["after"].append(
            #             kernel_name)

            #     # Add the kernel part
            #     kernel = {
            #         "plugin": "nil",
            #         "stage-packages": [platform.kernel.kernel_package],
            #     }
            #     self.yaml["parts"][kernel_name] = kernel

    def pack_platform(self, label, platform):
        # The gadget is not always required
        if platform.gadget:
            gadget_name = f"{label}_gadget"
            gadget_path = os.path.join(
                self.work_dir, "parts", gadget_name, "install")
        else:
            gadget_path = None

        # The prime directory contains our final filesystem
        prime_path = os.path.join(
            self.work_dir, "prime")
        
        # Create per-platform output directories
        platform_output = os.path.join(self.output_dir, label)
        os.makedirs(platform_output, exist_ok=True)

        ubuntu_image_pack(prime_path, gadget_path, platform_output)

    def pack_selected_platforms(self):
        # Helper function to iterate over selected platforms and
        # prepare images for them
        for (label, platform) in self.selected_platforms:
            print(f"Preparing image for platform: {label}")
            self.pack_platform(label, platform)
 
    def run(self, target_step):
        for (label, platform) in self.selected_platforms:
            print(f"Preparing platform: {label}")
            self.prepare_platform(label, platform)

        self.lcm = LifecycleManager(
            self.yaml,
            application_name="imagecraft",
            base=self.project.base,
            work_dir=self.work_dir,
            cache_dir=self.cache_dir,
        )

        actions = self.lcm.plan(self.parse_step(target_step))
        with self.lcm.action_executor() as ctx:
            for action in actions:
                if action.action_type != ActionType.SKIP:
                    print(f"Execute: {self._action_message(action)}")
                    ctx.execute(action)

        self.pack_selected_platforms()

    def clean(self):
        pass

