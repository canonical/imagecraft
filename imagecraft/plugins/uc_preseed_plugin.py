from typing import Literal, cast, override
import shlex
from craft_parts.plugins import Plugin, PluginProperties


class UcPreseedPluginProperties(PluginProperties, frozen=True):
    """Properties for the uc-preseed plugin."""

    plugin: Literal["uc-preseed"] = "uc-preseed"

    uc_preseed_model_assert: str
    uc_preseed_snaps: list[str] = []
    uc_preseed_channel: str | None = None
    uc_preseed_validation: Literal["ignore", "enforce"] = "ignore"
    uc_preseed_assertions: list[str] = []
    uc_preseed_revisions: str | None = None
    uc_preseed_preseed: bool = False
    uc_preseed_preseed_sign_key: str | None = None
    uc_preseed_apparmor_features_dir: str | None = None
    uc_preseed_sysfs_overlay: str | None = None


class UcPreseedPlugin(Plugin):
    """Prepare snaps for Ubuntu Core using 'snap prepare-image'."""

    properties_class = UcPreseedPluginProperties

    @override
    def get_build_snaps(self) -> set[str]:
        return set()

    @override
    def get_build_packages(self) -> set[str]:
        return set()

    @override
    def get_build_environment(self) -> dict[str, str]:
        return {}

    @override
    def get_build_commands(self) -> list[str]:
        options = cast(UcPreseedPluginProperties, self._options)

        cmd = ["snap", "prepare-image"]

        if options.uc_preseed_preseed:
            cmd.append("--preseed")

        if options.uc_preseed_preseed_sign_key:
            cmd.append(f"--preseed-sign-key={options.uc_preseed_preseed_sign_key}")

        if options.uc_preseed_apparmor_features_dir:
            cmd.append(
                f"--apparmor-features-dir={options.uc_preseed_apparmor_features_dir}"
            )

        if options.uc_preseed_sysfs_overlay:
            cmd.append(f"--sysfs-overlay={options.uc_preseed_sysfs_overlay}")

        cmd.append(f"--validation={options.uc_preseed_validation}")

        if options.uc_preseed_channel:
            cmd.append(f"--channel={options.uc_preseed_channel}")

        if options.uc_preseed_revisions:
            cmd.append(f"--revisions={options.uc_preseed_revisions}")

        for assertion in options.uc_preseed_assertions:
            cmd.append(f"--assert={assertion}")

        for snap in options.uc_preseed_snaps:
            cmd.append(f"--snap={self._resolve_snap(snap)}")

        cmd.append(
            f"{options.uc_preseed_model_assert} {self._part_info.part_install_dir}"
        )

        return [" ".join(cmd)]

    def _resolve_snap(self, snap: str) -> str:
        snap = snap.strip()
        if "/" in snap and not snap.endswith(".snap"):
            name, channel = snap.split("/", 1)
            snap = f"{name}={channel}"
        return shlex.quote(snap)
