metadata(
    description="BLE link between a sticky programme and a page using Web Bluetooth, and run().",
    version="0.1.0",
)

require("sticky")
require("aioble-peripheral")
require("aioble-server")

# The source sits with the rest of sticky, as aioble's parts share one folder.
package("sticky", files=("app.py", "ble.py"), base_path="../sticky")
