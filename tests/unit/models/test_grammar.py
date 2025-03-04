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

from imagecraft.models import get_grammar_aware_volume_keywords


def test_get_grammar_aware_volume_keywords():
    """Test get_grammar_aware_volume_keywords."""
    assert get_grammar_aware_volume_keywords() == ["structure"]
