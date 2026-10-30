metadata(
    description="Animations on the reTerminal Sticky's e-paper panel, in step with a slide deck.",
    version="0.1.0",
)

# sim.py runs on the host only; ble.py is installed by sticky-ble.
package("sticky", files=("__init__.py", "display.py"))
