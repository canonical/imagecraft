# Imagecraft

[![Imagecraft][imagecraft-badge]][imagecraft-site]
[![Tests][qa-badge]][qa-status]
[![Documentation Status][rtd-badge]][rtd-latest]
[![Codecov Status][codecov-badge]][codecov-status]
[![Code Style][ruff-badge]][ruff-site]

Imagecraft is the command-line tool for building bootable disk images. It centralizes
the definition and maintenance of images by keeping their essential details in one place
and incorporating processes from common tools.

## Basic usage

The structure, content, and build details of an image are declared in a project file
called `imagecraft.yaml`.

Create a minimal project file with:

```
imagecraft init
```

After declaring all of the images essential details, pack it with:

```
imagecraft pack
```

If you want to learn more about this workflow by working directly with the tool, follow
along with the [Build an Ubuntu
image](https://ubuntu.com/docs/imagecraft/latest/tutorials/build-an-ubuntu-image/)
tutorial.

## Installation

Imagecraft is available on all major Linux distributions through its snap.

```bash
sudo snap install imagecraft --classic
```

## Documentation

The [Imagecraft documentation](https://ubuntu.com/docs/imagecraft) provides guidance
and learning material about the full process of crafting images, installing additional
software, and configuring instances.

## Community and support

Ask your questions about Imagecraft and see who's working on what in the [Imagecraft
Matrix channel](https://matrix.to/#/#imagecraft:ubuntu.com).

You can report any issues or bugs on the project's [GitHub
repository](https://github.com/canonical/imagecraft/issues).

Imagecraft is covered by the [Ubuntu Code of
Conduct](https://ubuntu.com/community/ethos/code-of-conduct).

## Contribute to Imagecraft

Imagecraft is open source and part of the Canonical family. We would love your help.

If you're interested, start with the [contribution guide](CONTRIBUTING.md).

We welcome any suggestions and help with the docs. The [Canonical Open Documentation
Academy](https://github.com/canonical/open-documentation-academy) is the hub for doc
development, including Imagecraft docs. No prior coding experience is required.

## License and copyright

Imagecraft is released under the [GPL-3.0 license](LICENSE).

© 2023-2025 Canonical Ltd.

[imagecraft-badge]: https://snapcraft.io/imagecraft/badge.svg
[imagecraft-site]: https://snapcraft.io/imagecraft
[rtd-badge]: https://readthedocs.com/projects/canonical-imagecraft/badge/?version=latest
[rtd-latest]: https://canonical-imagecraft.readthedocs-hosted.com/latest/
[ruff-badge]: https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json
[ruff-site]: https://github.com/astral-sh/ruff
[codecov-badge]: https://codecov.io/github/canonical/imagecraft/coverage.svg?branch=main
[codecov-status]: https://codecov.io/github/canonical/imagecraft?branch=main
[qa-badge]: https://github.com/canonical/imagecraft/actions/workflows/qa.yaml/badge.svg?branch=main&event=push
[qa-status]: https://github.com/canonical/imagecraft/actions/workflows/qa.yaml
