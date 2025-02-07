PROJECT=imagecraft

ifneq ($(wildcard /etc/os-release),)
include /etc/os-release
export
endif

ifneq ($(VERSION_CODENAME),)
SETUP_TESTS_EXTRA_ARGS=--extra apt-$(VERSION_CODENAME)
endif

include common.mk

.PHONY: format
format: format-ruff format-prettier  ## Run all automatic formatters

.PHONY: lint
lint: lint-ruff lint-codespell lint-mypy lint-prettier lint-pyright lint-shellcheck lint-docs lint-twine  ## Run all linters

.PHONY: pack
pack: pack-pip pack-snap ## Build all packages

.PHONY: pack-snap
pack-snap: snap/snapcraft.yaml  ##- Build snap package
ifeq ($(shell which snapcraft),)
	sudo snap install --classic snapcraft
endif
	snapcraft pack

.PHONY: publish
publish: publish-pypi  ## Publish packages

.PHONY: publish-pypi
publish-pypi: clean package-pip lint-twine  ##- Publish Python packages to pypi
	uv tool run twine upload dist/*

# Used for installing build dependencies in CI.
.PHONY: install-build-deps
install-build-deps: install-lint-build-deps install-common-build-deps
ifeq ($(shell which apt-get),)
	$(warning Cannot install build dependencies without apt.)
else ifeq ($(wildcard /usr/include/libxml2/libxml/xpath.h),)
	sudo $(APT) install libxml2-dev libxslt1-dev python3-venv libgit2-dev
else ifeq ($(wildcard /usr/include/libxslt/xslt.h),)
	sudo $(APT) install libxslt1-dev python3-venv
else ifeq ($(wildcard /usr/share/doc/python3-venv/copyright),)
	sudo $(APT) install python3-venv
endif

.PHONY: install-common-build-deps
install-common-build-deps:
ifeq ($(shell which apt-get),)
	$(warning Cannot install build dependencies without apt.)
else
	sudo $(APT) install fuse-overlayfs
endif

# If additional build dependencies need installing in order to build the linting env.
.PHONY: install-lint-build-deps
install-lint-build-deps:
