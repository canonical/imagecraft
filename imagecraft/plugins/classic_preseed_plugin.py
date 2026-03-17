import shlex
from typing import Literal, cast, override
from craft_parts.plugins import Plugin, PluginProperties


class ClassicPreseedPluginProperties(PluginProperties, frozen=True):
    """Properties for the 'classic-preseed' plugin."""

    plugin: Literal["classic-preseed"] = "classic-preseed"

    classic_preseed_snaps: list[str]
    classic_preseed_channel: str | None = None
    classic_preseed_model_assert: str = ""
    classic_preseed_validation: Literal["ignore", "enforce"] = "ignore"
    classic_preseed_assertions: list[str] = []
    classic_preseed_revisions: str | None = None


class ClassicPreseedPlugin(Plugin):

    properties_class = ClassicPreseedPluginProperties

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
        options = cast(ClassicPreseedPluginProperties, self._options)
        cmd = [
            "snap",
            "prepare-image",
            "--classic",
            f"--arch={self._part_info.target_arch}",
            f"--validation={options.classic_preseed_validation}",
        ]
        if options.classic_preseed_channel:
            cmd.append(f"--channel={shlex.quote(options.classic_preseed_channel)}")

        if options.classic_preseed_revisions:
            cmd.append(f"--revisions={shlex.quote(options.classic_preseed_revisions)}")

        for assertion in options.classic_preseed_assertions:
            cmd.append(f"--assert={shlex.quote(assertion)}")

        for snap in options.classic_preseed_snaps:
            cmd.append(f"--snap={self._resolve_snap(snap)}")

        cmd.append(
            f'"{options.classic_preseed_model_assert}" {self._part_info.part_install_dir}'
        )
        return [" ".join(cmd)]

    def _resolve_snap(self, snap: str) -> str:
        snap = snap.strip()
        if "/" in snap and not snap.endswith(".snap"):
            name, channel = snap.split("/", 1)
            snap = f"{name}={channel}"
        return shlex.quote(snap)
