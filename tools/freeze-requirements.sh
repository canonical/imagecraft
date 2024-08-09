#!/bin/bash -eux

PYTHON3_APT="https://launchpad.net/ubuntu/+archive/primary/+sourcefiles/python-apt/2.7.0/python-apt_2.7.0.tar.xz; sys_platform == 'linux'"


requirements_fixups() {
  req_file="$1"

  # Python apt library pinned to source.
  sed -i '/^python-apt==/d' "$req_file"
}


venv_dir="$(mktemp -d)"

python3 -m venv "$venv_dir"

# shellcheck disable=SC1090,SC1091 # don't follow sources
. "$venv_dir/bin/activate"

# Pull in host python3-apt site package to avoid installation.
site_pkgs="$(readlink -f "$venv_dir"/lib/python3.*/site-packages/)"
temp_dir="$(mktemp -d)"
pushd "$temp_dir"
apt download python3-apt
dpkg -x ./*.deb .
cp -r usr/lib/python3/dist-packages/* "$site_pkgs"
popd

pip install -e .
pip freeze --exclude-editable > requirements.txt
requirements_fixups "requirements.txt"

pip install -e .[dev]
pip freeze --exclude-editable > requirements-dev.txt
requirements_fixups "requirements-dev.txt"

# Add python3-apt from Canonical
echo -e "\n# Requirements from launchpad.net\n\n$PYTHON3_APT" >> "requirements.txt"

rm -rf "$venv_dir"
