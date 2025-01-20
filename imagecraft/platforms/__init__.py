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

"""Platform support."""

from imagecraft.platforms.gptutil import GptType, GPT_NAME_MAX_LENGTH
from imagecraft.platforms.diskutil import FileSystem

__all__ = ["GptType", "GPT_NAME_MAX_LENGTH", "FileSystem"]
