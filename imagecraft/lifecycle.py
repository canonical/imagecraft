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
import yaml

from xdg import BaseDirectory

from craft_parts import ActionType, LifecycleManager, Step
from craft_cli import ArgumentParsingError

from imagecraft.project import Project
from imagecraft.helpers import host_deb_arch



class ImagecraftLifecycle:

    def __init__(self, args):
        self.cache_dir = BaseDirectory.save_cache_path("imagecraft")
        self.work_dir = "."

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
        print(platform)
        if platform.gadget:
            print("aaa")
            gadget_name = f"{label}_gadget"

            # We need to make sure the gadget is built first
            for part in self.yaml["parts"].values():
                if "after" in part:
                    part["after"].append(gadget_name)
                else:
                    part["after"] = [gadget_name]

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
                gadget["gadget_target"] = platform.gadget.gadget_target
            self.yaml["parts"][gadget_name] = gadget

            
 
    def run(self, target_step):
        for (label, platform) in self.selected_platforms:
            print(f"Preparing platform: {label}")
            self.prepare_platform(label, platform)

        print(self.yaml)

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

        for (label, platform) in self.selected_platforms:
            print(f"Preparing image for platform: {label}")
            # TODO

    def clean(self):
        pass

