metadata(
    description="Animations on the reTerminal Sticky's e-paper panel, in step with a slide deck.",
    version="0.1.0",
)

# ble.py and app.py, which needs the link, come with sticky-ble.
package("sticky", files=("__init__.py", "anim.py", "display.py"))
