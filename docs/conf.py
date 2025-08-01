# This file is part of imagecraft.
#
# Copyright 2024 Canonical Ltd.
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

import os
import datetime
import pathlib
import sys

import craft_parts_docs  # type: ignore

# Workaround https://github.com/sphinx-toolbox/sphinx-toolbox/issues/190
try:
    import sphinx_prompt  # type: ignore
    import sys
    sys.modules['sphinx-prompt'] = sphinx_prompt
except ImportError:
    pass

project_dir = pathlib.Path(__file__).parents[1].resolve()
sys.path.insert(0, str(project_dir.absolute()))

project = "Imagecraft"
author = "Canonical"

copyright = "2023-%s, %s" % (datetime.date.today().year, author)

# region Configuration for canonical-sphinx
ogp_site_url = "https://canonical-imagecraft.readthedocs-hosted.com/"
ogp_site_name = project
ogp_image = "https://assets.ubuntu.com/v1/253da317-image-document-ubuntudocs.svg"

html_context = {
    "product_page": "github.com/canonical/imagecraft",
    "github_url": "https://github.com/canonical/imagecraft",
    "github_issues": "https://github.com/canonical/imagecraft/issues",
    "discourse": "",  # Leave this blank to hide it from the dropdown
}

# Target repository for the edit button on pages
html_theme_options = {
    "source_edit_link": "https://github.com/canonical/imagecraft",
}

extensions = [
    "canonical_sphinx",
    "notfound.extension",
    "pydantic_kitbash",
    "sphinx_sitemap",
]

# endregion

# region General configuration
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions.extend(
    [
        "sphinx.ext.intersphinx",
        "sphinx.ext.viewcode",
        "sphinx.ext.coverage",
        "sphinx.ext.doctest",
        "sphinx.ext.ifconfig",
        "sphinx-pydantic",
        "sphinx_sitemap",
        "sphinx_toolbox",
        "sphinx_toolbox.more_autodoc",
        "sphinx.ext.autodoc",  # Must be loaded after more_autodoc
        "canonical.terminal-output",
        "sphinxcontrib.details.directive",
        "sphinxext.rediraffe",
    ]
)

# endregion


exclude_patterns = [
    "_build",
    "Thumbs.db",
    ".DS_Store",
    "env",
    "sphinx-starter-pack",
    # Excluded here because they are either included explicitly in other
    # documents (so they generate "duplicate label" errors) or they aren't
    # used in this documentation at all (so they generate "unreferenced"
    # errors).
    # Disable sections and pages that are currently empty
    "tutorials/index.rst",
    "reference/plugins.rst",
    # We do not use the overlay command, yet...
    "reference/commands/overlay.rst",
    # Disable unused pages from Craft Parts
    "common/craft-parts/explanation/file-migration.rst",
    "common/craft-parts/explanation/parts.rst",
    "common/craft-parts/explanation/overlay_parameters.rst",
    "common/craft-parts/explanation/overlays.rst",
    "common/craft-parts/explanation/how_parts_are_built.rst",
    "common/craft-parts/explanation/overlay_step.rst",
    "common/craft-parts/explanation/dump_plugin.rst",
    "common/craft-parts/explanation/gradle_plugin.rst",
    "common/craft-parts/explanation/lifecycle.rst",
    "common/craft-parts/how-to/craftctl.rst",
    "common/craft-parts/how-to/customise-the-build-with-craftctl.rst",
    "common/craft-parts/how-to/include_files.rst",
    "common/craft-parts/how-to/override_build.rst",
    "common/craft-parts/how-to/use_parts.rst",
    "common/craft-parts/reference/step_execution_environment.rst",
    "common/craft-parts/reference/step_output_directories.rst",
    "common/craft-parts/reference/parts_steps.rst",
    "common/craft-parts/reference/part_properties.rst",
    "common/craft-parts/reference/partition_specific_output_directory_variables.rst",
    "common/craft-parts/reference/plugins/ant_plugin.rst",
    "common/craft-parts/reference/plugins/autotools_plugin.rst",
    "common/craft-parts/reference/plugins/cargo_use_plugin.rst",
    "common/craft-parts/reference/plugins/cmake_plugin.rst",
    "common/craft-parts/reference/plugins/dotnet_plugin.rst",
    "common/craft-parts/reference/plugins/dotnet_v2_plugin.rst",
    "common/craft-parts/reference/plugins/dump_plugin.rst",
    "common/craft-parts/reference/plugins/go_plugin.rst",
    "common/craft-parts/reference/plugins/gradle_plugin.rst",
    "common/craft-parts/reference/plugins/make_plugin.rst",
    "common/craft-parts/reference/plugins/maven_plugin.rst",
    "common/craft-parts/reference/plugins/meson_plugin.rst",
    "common/craft-parts/reference/plugins/nil_plugin.rst",
    "common/craft-parts/reference/plugins/npm_plugin.rst",
    "common/craft-parts/reference/plugins/python_plugin.rst",
    "common/craft-parts/reference/plugins/poetry_plugin.rst",
    "common/craft-parts/reference/plugins/qmake_plugin.rst",
    "common/craft-parts/reference/plugins/rust_plugin.rst",
    "common/craft-parts/reference/plugins/scons_plugin.rst",
    "common/craft-parts/reference/plugins/go_use_plugin.rst",
    "common/craft-parts/reference/plugins/uv_plugin.rst",
    "common/craft-parts/reference/plugins/jlink_plugin.rst",
]

linkcheck_ignore = [
    "http://127.0.0.1:8000",
    "https://apt-repo.com",
    # Linkcheck is unable to properly handled matrix.to URLs containing # and :
    # See https://github.com/sphinx-doc/sphinx/issues/13620
    "https://matrix.to",
    # Ignore gnu.org URLs due to a mix of aggressive rate limiting and aggressive/buggy
    # retry from linkcheck
    "https://www.gnu.org"
]

rst_epilog = """
.. include:: /reuse/links.txt
"""

# region Options for extensions
# Intersphinx extension
# https://www.sphinx-doc.org/en/master/usage/extensions/intersphinx.html#configuration

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
}

# Type hints configuration
set_type_checking_flag = True
typehints_fully_qualified = False
always_document_param_types = True

# Github config
github_username = "canonical"
github_repository = "imagecraft"

# endregion


def generate_cli_docs(nil):
    gen_cli_docs_path = (project_dir / "tools/docs/gen_cli_docs.py").resolve()
    os.system("%s %s" % (gen_cli_docs_path, project_dir / "docs"))


def setup(app):
    app.connect("builder-inited", generate_cli_docs)


# Setup libraries documentation snippets for use in imagecraft docs.
common_docs_path = pathlib.Path(__file__).parent / "common"
craft_parts_docs_path = pathlib.Path(craft_parts_docs.__file__).parent / "craft-parts"
(common_docs_path / "craft-parts").unlink(missing_ok=True)
(common_docs_path / "craft-parts").symlink_to(
    craft_parts_docs_path, target_is_directory=True
)

# Client-side page redirects.
rediraffe_redirects = "redirects.txt"

# The full path to the RTD site.
# TODO: Change this to your project's RTD URL. If the RTD site isn't live yet, follow
# the pattern here. If the documentation has moved to documentation.ubuntu.com, enter
# the URL at that domain. It's OK to use this for private projects.
# https://sphinx-sitemap.readthedocs.io
html_baseurl = "https://canonical-imagecraft.readthedocs-hosted.com/"

# Compose the URL for remote RTD and local builds.
# TODO: If your project doesn't have a `latest` RTD branch set up, change to its default
# branch.
# https://sphinx-sitemap.readthedocs.io
if "READTHEDOCS_VERSION" in os.environ:
    version = os.environ["READTHEDOCS_VERSION"]
    sitemap_url_scheme = "{version}{link}"
else:
    sitemap_url_scheme = "latest/{link}"

# endregion
