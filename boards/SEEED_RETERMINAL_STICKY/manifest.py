include("$(PORT_DIR)/boards/manifest.py")

# This repository's packages, laid out like micropython-lib.
add_library("sticky-lib", "../../lib")
require("sticky", library="sticky-lib")
