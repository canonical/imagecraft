[![Release](https://github.com/canonical/imagecraft/actions/workflows/release-publish.yaml/badge.svg?branch=main&event=push)](https://github.com/canonical/imagecraft/actions/workflows/release-publish.yaml)
[![Documentation](https://readthedocs.com/projects/canonical-imagecraft/badge/?version=latest)](https://canonical-imagecraft.readthedocs-hosted.com/en/latest/?badge=latest)
[![tests](https://github.com/canonical/imagecraft/actions/workflows/qa.yaml/badge.svg?branch=main&event=push)](https://github.com/canonical/imagecraft/actions/workflows/qa.yaml)
[![spread tests](https://github.com/canonical/imagecraft/actions/workflows/spread-test.yaml/badge.svg?branch=main&event=push)](https://github.com/canonical/imagecraft/actions/workflows/spread-test.yaml)

# Imagecraft

The base repository for Imagecraft projects.

## Description

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
