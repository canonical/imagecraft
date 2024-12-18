# Copyright 2020-2024 Canonical Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# For further info, check https://github.com/canonical/imagecraft

"""Collection of utilities for imagecraft."""

from __future__ import annotations

from typing import Any

import sh
from craft_cli import emit


def cmd(cmdname: str, *args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
    """Emit full commandline to execute, and execute it."""
    emit.debug(f"Command: {cmdname} {' '.join([str(a) for a in args])}")

    return getattr(sh, cmdname)(*args, **kwargs)
