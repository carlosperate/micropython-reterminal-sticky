include("$(PORT_DIR)/boards/manifest.py")
freeze("modules")

# This repository's packages, laid out like micropython-lib.
add_library("sticky-lib", "../../lib")
require("sticky", library="sticky-lib")
require("sticky-bleuart", library="sticky-lib")
require("ssd1677", library="sticky-lib")
require("bq27220", library="sticky-lib")

# For programmes that use aioble rather than sticky.bleuart.
require("aioble-peripheral")
require("aioble-server")
