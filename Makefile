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
snap:  ## Create a Imagecraft snap
	@snapcraft clean && snapcraft --use-lxd
