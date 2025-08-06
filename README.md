# Imagecraft

[![Imagecraft][imagecraft-badge]][imagecraft-site]
[![tests][qa-badge]][qa-status]
[![Documentation Status][rtd-badge]][rtd-latest]
[![Codecov Status][codecov-badge]][codecov-status]
[![Ruff status][ruff-badge]][ruff-site]

Imagecraft is a craft tool used to create Ubuntu bootable images. It
follows the same principles as Snapcraft, but is focused on creating
bootable images instead.

## Documentation

Imagecraft documentation is built from reStructuredText (`.rst`) files,
most of them under the `docs/` folder in the source tree. [Build and
browse the documentation
locally](#build-and-browse-the-documentation-locally) if you prefer,
although the [product
website](https://canonical-imagecraft.readthedocs-hosted.com) is
recommended.

### Build and browse the documentation locally

Clone the official source tree from GitHub into your computer\'s home
directory. Its default location will then be `~/imagecraft/`. (You may
clone the [Imagecraft
repository](https://github.com/canonical/imagecraft) directly. However,
it\'s protected: if you plan on [contributing to the
project](#project-and-community), consider forking it to your own GitHub
account then cloning that instead.)

Install the documentation tools:

```bash
make setup-docs
```

Build and serve the documentation:

```bash
make docs-auto
```

Point your web browser to address `127.0.0.1:8080`.

## Community and support

You can report any issues or bugs on the project's [GitHub
repository](https://github.com/canonical/imagecraft/issues).

Imagecraft is covered by the [Ubuntu Code of
Conduct](https://ubuntu.com/community/ethos/code-of-conduct).

## Contribute to Imagecraft

Imagecraft is open source and part of the Canonical family. We would love your help.

If you're interested, start with the [contribution guide](HACKING.md).

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
