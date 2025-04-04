# This file is part of imagecraft.
#
# Copyright 2025 Canonical Ltd.
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

"""Tests for grammar-aware project models."""

import pydantic
import pytest
from imagecraft.models import get_grammar_aware_volume_keywords
from imagecraft.models.grammar import _GrammarAwareVolume


def test_get_grammar_aware_volume_keywords():
    """Test get_grammar_aware_volume_keywords."""
    assert get_grammar_aware_volume_keywords() == ["structure"]


@pytest.mark.parametrize(
    ("volume"),
    [
        ({}),
        (
            {
                "schema": "gpt",
                "structure": [
                    {
                        "name": "rootfs",
                        "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                        "filesystem": "ext4",
                        "filesystem-label": "writable",
                        "role": "system-data",
                        "size": "6G",
                    },
                    {
                        "name": "rootfs",
                        "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                        "filesystem": "ext4",
                        "filesystem-label": "writable",
                        "role": "system-data",
                        "size": "6G",
                    },
                ],
            }
        ),
    ],
)
def test_grammar_aware_volume(volume):
    """Test the grammar-aware volume should be able to parse the input data."""
    _GrammarAwareVolume(**volume)


@pytest.mark.parametrize(
    ("volume"),
    [
        (
            {
                "structure": {},
            }
        ),
        (
            {
                "structure": [
                    "test",
                ],
            }
        ),
    ],
)
def test_grammar_aware_volume_error(volume):
    """Test the grammar-aware volume should be able to report error."""
    with pytest.raises(pydantic.ValidationError):
        _GrammarAwareVolume(**volume)
