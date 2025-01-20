# This file is part of imagecraft.
#
# # Copyright 2025 Canonical Ltd.
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License version 3 as published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""GPT related utility functions and data structures."""

import enum

GPT_NAME_MAX_LENGTH = 36


class GptType(str, enum.Enum):
    """Supported GUID Partition types."""

    LINUX_DATA = "0FC63DAF-8483-4772-8E79-3D69D8477DE4"
    WINDOWS_BASIC = "EBD0A0A2-B9E5-4433-87C0-68B6B72699C7"
    EFI_SYSTEM = "C12A7328-F81F-11D2-BA4B-00A0C93EC93B"
    BIOS_BOOT = "21686148-6449-6E6F-744E-656564454649"
