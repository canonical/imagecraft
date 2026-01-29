# -*- Mode:Python; indent-tabs-mode:nil; tab-width:4 -*-
#
# Copyright 2026 Canonical Ltd.
#
# LGPLv3

"""Ubuntu Core preseed plugin.

Runs `snap prepare-image` (optionally with preseeding) to generate a UC
filesystem tree in the part's install area.
"""

from __future__ import annotations

import shlex
from pathlib import Path
from typing import Literal, cast

from craft_parts.plugins.base import Plugin
from craft_parts.plugins.properties import PluginProperties
from pydantic import Field, model_validator
from typing_extensions import Self, override


def _shquote(value: object) -> str:
    return shlex.quote(str(value))


def _split_args(arg_string: str) -> list[str]:
    """Split a shell-like arg string into tokens (safe for plugin config use)."""
    return shlex.split(arg_string)


def _is_probably_path(spec: str) -> bool:
    """Heuristically decide whether *spec* looks like a local path."""
    return ("/" in spec or spec.startswith((".", "~"))) and (
        spec.endswith((".snap", ".assert")) or "/" in spec
    )


def _normalize_snap_spec(spec: str) -> str:
    """Normalize snap specs to the form accepted by `snap prepare-image`.

    - Store snap with per-snap channel: name=track/risk (or name=risk)
    - Store snap without channel: name
    - Local snap: /path/to/foo.snap (passed as-is)
    """
    spec = spec.strip()
    if not spec:
        raise ValueError("Empty snap spec is not allowed")

    # If it's clearly a local file, keep as-is.
    if spec.endswith(".snap"):
        return spec

    # Already in name=channel form.
    if "=" in spec:
        return spec

    # Plain store snap name.
    return spec


class UcPreseedPluginProperties(PluginProperties, frozen=True):
    """Properties for the `uc-preseed` plugin."""

    plugin: Literal["uc-preseed"] = "uc-preseed"

    # Required: model assertion path (relative to src/)
    uc_preseed_model_assert: str

    # Assertions (relative to src/)
    uc_preseed_assertions: list[str] = Field(default_factory=list)

    # Global channel applied to all model-resolved snaps (uc-image style)
    uc_preseed_channel: str | None = None

    # Convenience overrides (store spec or local .snap path; relative paths are relative to src/)
    uc_preseed_gadget_snap: str | None = None
    uc_preseed_kernel_snap: str | None = None
    uc_preseed_base_snap: str | None = None

    # Extra snaps / overrides (store specs or local .snap paths; relative paths are relative to src/)
    uc_preseed_snaps: list[str] = Field(default_factory=list)

    # Arbitrary passthrough args to snap prepare-image.
    # Each element can be either:
    # - a single token: "--revisions"
    # - or a mini arg-string: "--revisions=/path/to/seeds.manifest"
    # - or multi-token: "--write-revisions ./seed.manifest"
    uc_preseed_prepare_image_args: list[str] = Field(default_factory=list)

    # AppArmor feature directory (absolute, or relative to src/)
    uc_preseed_apparmor_features_dir: str | None = None

    # Preseed options
    uc_preseed_preseed: bool = True
    uc_preseed_preseed_sign_key: str | None = None
    uc_preseed_validation: Literal["ignore", "enforce"] = "ignore"

    @model_validator(mode="after")
    def _validate(self) -> Self:
        if not self.uc_preseed_model_assert.strip():
            raise ValueError("uc-preseed-model-assert must be a non-empty string")
        return self


class UcPreseedPlugin(Plugin):
    """Prepare a (preseeded) Ubuntu Core filesystem tree via `snap prepare-image`."""

    properties_class = UcPreseedPluginProperties

    @override
    def get_build_snaps(self) -> set[str]:
        return set()

    @override
    def get_build_packages(self) -> set[str]:
        # Needed for unsquashfs when staging gadget content/blobs.
        return {"squashfs-tools"}

    @override
    def get_build_environment(self) -> dict[str, str]:
        return {"TMPDIR": "/tmp"}  # noqa: S108

    @override
    def get_pull_commands(self) -> list[str]:
        return []

    def _resolve_snap_arg(self, src: Path, spec: str) -> str:
        """Convert a user spec into the string passed to `--snap`.

        Relative local paths resolve against src/.
        Store specs are normalized and passed unchanged.
        """
        spec = spec.strip()
        if not spec:
            raise ValueError("Empty snap spec is not allowed")

        # Local .snap: allow relative paths from src.
        if spec.endswith(".snap"):
            p = Path(spec)
            p2 = p if p.is_absolute() else (src / p)
            return str(p2)

        # Store snap spec.
        return _normalize_snap_spec(spec)

    @override
    def get_build_commands(self) -> list[str]:
        options = cast(UcPreseedPluginProperties, self._options)

        src = Path(self._part_info.part_src_dir)
        install = Path(self._part_info.part_install_dir)

        cmds: list[str] = [
            # prepare-image expects an empty systems dir in system-seed between rebuilds
            'rm -rf "${CRAFT_PART_INSTALL}/system-seed/systems" || true',
            'mkdir -p "${CRAFT_PART_INSTALL}/system-seed/systems"',
        ]

        cmd_parts: list[str] = ["snap", "prepare-image"]

        # Global channel (uc-image style)
        if options.uc_preseed_channel:
            cmd_parts.append(f"--channel={_shquote(options.uc_preseed_channel)}")

        # Preseed controls
        if options.uc_preseed_preseed:
            cmd_parts.append("--preseed")

        if options.uc_preseed_preseed_sign_key:
            cmd_parts.append(
                f"--preseed-sign-key={_shquote(options.uc_preseed_preseed_sign_key)}"
            )

        cmd_parts.append(f"--validation={_shquote(options.uc_preseed_validation)}")

        # AppArmor features dir
        if options.uc_preseed_apparmor_features_dir:
            p_afd = Path(options.uc_preseed_apparmor_features_dir)
            afd = p_afd if p_afd.is_absolute() else (src / p_afd)
            cmd_parts.append(f"--apparmor-features-dir={_shquote(afd)}")

        # Extra assertions
        cmd_parts.extend(
            [f"--assert {_shquote(src / a)}" for a in options.uc_preseed_assertions]
        )

        # Arbitrary passthrough args (uc-image style)
        # Each list item may expand to multiple tokens.
        for arg_string in options.uc_preseed_prepare_image_args:
            cmd_parts.extend([_shquote(tok) for tok in _split_args(arg_string)])

        # Convenience overrides (implemented via --snap)
        # Keep track of a local gadget snap path (if provided) so we can
        # optionally unpack it to extract raw boot blobs (uc-image style).
        gadget_snap_for_unpack: str | None = None
        overrides: list[str] = []

        if options.uc_preseed_gadget_snap:
            overrides.append(options.uc_preseed_gadget_snap)
            # Only local gadget snaps (ending in .snap) can be unpacked here.
            if options.uc_preseed_gadget_snap.strip().endswith(".snap"):
                gadget_snap_for_unpack = self._resolve_snap_arg(
                    src, options.uc_preseed_gadget_snap
                )
        if options.uc_preseed_kernel_snap:
            overrides.append(options.uc_preseed_kernel_snap)
        if options.uc_preseed_base_snap:
            overrides.append(options.uc_preseed_base_snap)

        cmd_parts.extend(
            [
                f"--snap {_shquote(self._resolve_snap_arg(src, spec))}"
                for spec in overrides
            ]
        )

        # Extra snaps / overrides (store or local)
        cmd_parts.extend(
            [
                f"--snap {_shquote(self._resolve_snap_arg(src, spec))}"
                for spec in options.uc_preseed_snaps
            ]
        )

        # Model assertion (positional)
        cmd_parts.append(_shquote(src / options.uc_preseed_model_assert))

        # Target dir (positional)
        cmd_parts.append(_shquote(install))

        cmds.append(" ".join(cmd_parts))

        # --- uc-image compatibility helpers ---
        # If a local gadget snap is provided, unpack it and stage a few
        # well-known artifacts for the pack step to export (e.g. imx-boot.bin).
        #
        # We keep this intentionally lightweight: pack will simply copy these
        # staged files into the final artefacts directory.
        if gadget_snap_for_unpack:
            cmds.extend(
                [
                    'rm -rf "${CRAFT_PART_INSTALL}/_gadget_unpacked" || true',
                    'mkdir -p "${CRAFT_PART_INSTALL}/_gadget_unpacked"',
                    f'unsquashfs -n -d "${{CRAFT_PART_INSTALL}}/_gadget_unpacked" {_shquote(gadget_snap_for_unpack)}',
                    # Stage raw boot blobs if present (e.g. blobs/imx-boot.bin)
                    'if [ -f "${CRAFT_PART_INSTALL}/_gadget_unpacked/blobs/imx-boot.bin" ]; then '
                    'mkdir -p "${CRAFT_PART_INSTALL}/_gadget/blobs"; '
                    'cp -a "${CRAFT_PART_INSTALL}/_gadget_unpacked/blobs/imx-boot.bin" "${CRAFT_PART_INSTALL}/_gadget/blobs/imx-boot.bin"; '
                    "fi",
                    # Stage boot.sel if present (used by some gadgets for ubuntu-boot)
                    'if [ -f "${CRAFT_PART_INSTALL}/_gadget_unpacked/boot.sel" ]; then '
                    'mkdir -p "${CRAFT_PART_INSTALL}/_gadget"; '
                    'cp -a "${CRAFT_PART_INSTALL}/_gadget_unpacked/boot.sel" "${CRAFT_PART_INSTALL}/_gadget/boot.sel"; '
                    "fi",
                ]
            )

        return cmds
