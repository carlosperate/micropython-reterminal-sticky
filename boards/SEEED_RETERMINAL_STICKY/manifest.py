include("$(PORT_DIR)/boards/manifest.py")
freeze("modules")

# This repository's packages, laid out like micropython-lib.
add_library("sticky-lib", "../../lib")
require("sticky", library="sticky-lib")
require("sticky-ble", library="sticky-lib")
require("ssd1677", library="sticky-lib")
