#------------------------------------------------
# SNAPSHOT PYTHON PACKAGE DEPENDENCIES
#------------------------------------------------

.PHONY: freeze-requirements
freeze-requirements:  ## Re-freeze requirements.
	tools/freeze-requirements.sh
	
	
#------------------------------------------------
# CREATE IMAGECRAFT SNAP
#------------------------------------------------

.PHONY: snap
snap:  ## Create a clean Imagecraft snap
	@snapcraft clean --use-lxd && snapcraft --use-lxd


.PHONY: snap-imagecraft-only
snap-imagecraft-only:  ## Create a Imagecraft snap while only cleaning the imagecraft part
	@snapcraft clean imagecraft --use-lxd && snapcraft --use-lxd
