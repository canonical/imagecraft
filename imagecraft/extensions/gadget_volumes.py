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

"""Gadget volumes extension for Imagecraft."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING, Any

from craft_application import errors
from craft_application.extensions import Extension
from craft_application.util import safe_yaml_load
from craft_cli import emit
from typing_extensions import override

if TYPE_CHECKING:
    from collections.abc import Sequence


class GadgetVolumesExtension(Extension):
    """Extension that extracts volume definitions from a gadget snap or file."""

    name = "gadget-volumes"

    @staticmethod
    @override
    def get_supported_bases() -> Sequence[str]:
        return ("ubuntu@24.04", "ubuntu@26.04", "devel")

    @staticmethod
    @override
    def is_experimental(base: str | None) -> bool:
        return True

    @override
    def get_root_snippet(self) -> dict[str, Any]:
        """Obtain volume definitions and return root snippet."""
        gadget_yaml_content = self._obtain_gadget_yaml()
        raw_volumes = gadget_yaml_content.get("volumes", {})
        cleaned_volumes = _clean_volumes(raw_volumes)
        return {"volumes": cleaned_volumes}

    def _obtain_gadget_yaml(self) -> dict[str, Any]:
        """Resolve and extract gadget.yaml from file, local snap, or store."""
        # 1. Local gadget YAML file
        if content := self._find_gadget_file():
            return content

        # 2. Local packed gadget snap file
        if content := self._find_local_gadget_snap():
            return content

        # 3. Model assertion in uc-prepare part
        if content := self._find_from_uc_prepare():
            return content

        raise errors.ExtensionError(
            "Could not find a gadget definition for 'gadget-volumes' extension.",
            details=(
                "Checked for local gadget YAML files, local .snap files, "
                "and uc-prepare model assertion."
            ),
            resolution=(
                "Provide a gadget.yaml file, a gadget snap in the project directory, "
                "or a uc-prepare part with model.assert."
            ),
        )

    def _find_gadget_file(self) -> dict[str, Any] | None:
        """Find local gadget.yaml or gadget-{arch}.yaml file."""
        candidates = []
        if self.build_for:
            candidates.append(self.project_root / f"gadget-{self.build_for}.yaml")
            candidates.append(
                self.project_root / "gadget" / f"gadget-{self.build_for}.yaml"
            )
        candidates.append(self.project_root / "gadget.yaml")
        candidates.append(self.project_root / "gadget" / "gadget.yaml")

        for path in candidates:
            if path.is_file():
                emit.debug(f"gadget-volumes: using gadget file at {path}")
                data = safe_yaml_load(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
        return None

    def _find_local_gadget_snap(self) -> dict[str, Any] | None:
        """Find a local gadget snap in the project directory."""
        candidates = [
            file
            for file in self.project_root.iterdir()
            if file.is_file() and file.name.endswith(".snap")
        ]

        # Prioritize snaps containing 'gadget' in the filename
        candidates.sort(key=lambda p: 0 if "gadget" in p.name else 1)

        for snap_path in candidates:
            content = _extract_gadget_from_snap(snap_path)
            if content is not None:
                emit.debug(f"gadget-volumes: extracted gadget.yaml from {snap_path}")
                return content
        return None

    def _find_from_uc_prepare(self) -> dict[str, Any] | None:
        """Find model assertion from a uc-prepare part and fetch gadget from store."""
        parts = self.yaml_data.get("parts", {})
        if not isinstance(parts, dict):
            return None

        for part in parts.values():
            if not isinstance(part, dict):
                continue
            if part.get("plugin") != "uc-prepare":
                continue

            model_file_name = part.get("uc_prepare_model_assert") or part.get(
                "uc-prepare-model-assert"
            )
            if not model_file_name:
                continue

            model_path = self.project_root / model_file_name
            if not model_path.is_file():
                continue

            return self._fetch_gadget_from_model_assert(
                model_path,
                default_channel=part.get("uc_prepare_channel")
                or part.get("uc-prepare-channel"),
            )

        return None

    def _fetch_gadget_from_model_assert(
        self,
        model_path: Path,
        *,
        default_channel: str | None = None,
    ) -> dict[str, Any]:
        """Parse model assertion and download gadget snap from store."""
        raw_text = model_path.read_text(encoding="utf-8")
        yaml_section = raw_text.split("\n\n", 1)[0]
        model_data = safe_yaml_load(yaml_section)

        if not isinstance(model_data, dict):
            raise errors.ExtensionError(
                f"Invalid model assertion file at {model_path}.",
                resolution="Ensure model assertion contains valid YAML headers.",
            )

        gadget_snap_info = None
        for snap_info in model_data.get("snaps", []):
            if isinstance(snap_info, dict) and snap_info.get("type") == "gadget":
                gadget_snap_info = snap_info
                break

        if not gadget_snap_info:
            raise errors.ExtensionError(
                f"Model assertion at {model_path} does not declare a gadget snap.",
                resolution="Ensure the model assertion declares a snap with type 'gadget'.",
            )

        snap_name = gadget_snap_info.get("name")
        channel = (
            default_channel
            or gadget_snap_info.get("default-channel")
            or gadget_snap_info.get("channel")
            or "stable"
        )
        arch = self.build_for or model_data.get("architecture") or "amd64"

        emit.debug(
            f"gadget-volumes: downloading gadget snap '{snap_name}' "
            f"(channel='{channel}', arch='{arch}') from store"
        )
        return _fetch_gadget_from_store(snap_name=snap_name, channel=channel, arch=arch)


def _clean_volumes(volumes: dict[str, Any]) -> dict[str, Any]:
    """Clean and convert gadget.yaml volumes into Imagecraft volume specification."""
    cleaned: dict[str, Any] = {}
    for volume_name, volume_data in volumes.items():
        if not isinstance(volume_data, dict):
            continue

        schema = volume_data.get("schema", "gpt")
        structures: list[dict[str, Any]] = []

        for item in volume_data.get("structure", []):
            if not isinstance(item, dict):
                continue

            ptype = item.get("type")
            # Skip MBR boot sectors embedded in GPT schemas
            if ptype == "mbr":
                continue

            # Skip partitions lacking role or filesystem (e.g. raw BIOS boot code)
            if "role" not in item or "filesystem" not in item:
                continue

            struct_item: dict[str, Any] = {
                "name": item.get("name", "").lower().replace(" ", "-"),
                "role": item["role"],
                "filesystem": item["filesystem"],
            }

            if "size" in item:
                struct_item["size"] = str(item["size"])

            if "filesystem-label" in item:
                struct_item["filesystem-label"] = item["filesystem-label"]

            if ptype:
                # Handle hybrid MBR/GPT partition types like "EF,C12A7328-F81F-11D2-BA4B-00A0C93EC93B"
                if "," in str(ptype):
                    mbr_t, gpt_t = str(ptype).split(",", 1)
                    struct_item["type"] = (
                        gpt_t.strip() if schema == "gpt" else mbr_t.strip()
                    )
                else:
                    struct_item["type"] = str(ptype)

            structures.append(struct_item)

        cleaned[volume_name] = {
            "schema": schema,
            "structure": structures,
        }

    return cleaned


def _extract_gadget_from_snap(snap_path: Path) -> dict[str, Any] | None:
    """Extract and parse meta/gadget.yaml from a local snap archive."""
    if not shutil.which("unsquashfs"):
        raise errors.ExtensionError(
            "The 'unsquashfs' utility is required to extract gadget snaps.",
            resolution="Install squashfs-tools on the system.",
        )

    for target in ("meta/gadget.yaml", "gadget.yaml"):
        result = subprocess.run(
            ["unsquashfs", "-p", "1", "-cat", str(snap_path), target],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            parsed = safe_yaml_load(result.stdout)
            if isinstance(parsed, dict) and "volumes" in parsed:
                return parsed
    return None


def _fetch_gadget_from_store(
    *,
    snap_name: str,
    channel: str,
    arch: str,
) -> dict[str, Any]:
    """Fetch snap details from the Snap Store API and extract gadget.yaml."""
    api_url = (
        f"https://api.snapcraft.io/api/v1/snaps/details/{snap_name}"
        f"?channel={channel}&fields=anon_download_url"
    )
    headers = {
        "X-Ubuntu-Series": "16",
        "X-Ubuntu-Architecture": arch,
    }

    req = urllib.request.Request(api_url, headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:  # noqa: S310
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError) as err:
        raise errors.ExtensionError(
            f"Failed to query Snap Store for gadget snap {snap_name!r}: {err}",
            resolution="Check network connection and gadget snap name/channel.",
        ) from err

    download_url = payload.get("anon_download_url")
    if not download_url:
        raise errors.ExtensionError(
            f"Snap Store did not provide a download URL for {snap_name!r} ({channel}, {arch}).",
            resolution="Ensure the gadget snap is published for this architecture and channel.",
        )

    with tempfile.NamedTemporaryFile(suffix=".snap", delete=True) as temp_snap:
        snap_req = urllib.request.Request(download_url)  # noqa: S310
        try:
            with urllib.request.urlopen(snap_req) as resp:  # noqa: S310
                shutil.copyfileobj(resp, temp_snap)
            temp_snap.flush()
        except urllib.error.URLError as err:
            raise errors.ExtensionError(
                f"Failed to download gadget snap from {download_url}: {err}",
                resolution="Check internet connectivity.",
            ) from err

        content = _extract_gadget_from_snap(Path(temp_snap.name))
        if content is None:
            raise errors.ExtensionError(
                f"Downloaded gadget snap {snap_name!r} does not contain meta/gadget.yaml.",
                resolution="Verify that the snap is a valid gadget snap.",
            )
        return content
