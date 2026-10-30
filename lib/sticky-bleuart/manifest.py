metadata(
    description="The Nordic UART Service over BLE as a stream, usable as a REPL terminal.",
    version="0.1.0",
)

require("sticky")

# The source sits with the rest of sticky, as aioble's parts share one folder.
package("sticky", files=("bleuart.py",), base_path="../sticky")
