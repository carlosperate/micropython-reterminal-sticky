# Builds run in Espressif's IDF image, so every machine gets the same toolchain.
# Flashing runs on the host: Docker on macOS can't reach USB devices.

IDF_IMAGE ?= espressif/idf:v5.5.2

BOARD ?= SEEED_RETERMINAL_STICKY
BOARD_VARIANT ?=

BUILD ?= $(CURDIR)/build
# Absolute: each make -C below would read a relative path from a different folder.
override BUILD := $(abspath $(BUILD))
FIRMWARE_BUILD = $(BUILD)/$(BOARD)$(if $(BOARD_VARIANT),-$(BOARD_VARIANT))

ESP32_ARGS = BOARD=$(BOARD) BOARD_VARIANT=$(BOARD_VARIANT) BUILD=$(FIRMWARE_BUILD)
# A board in boards/ is ours; any other name is one of upstream's.
ifneq ($(wildcard boards/$(BOARD)/.),)
ESP32_ARGS += BOARD_DIR=$(CURDIR)/boards/$(BOARD)
endif

# The image has no pkg-config to find libffi, and nothing here needs ffi.
UNIX_ARGS = MICROPY_PY_FFI=0
# x86-64 everywhere, emulated on Apple silicon: MicroPython has no arm64 native emitter for viper.
UNIX_PLATFORM = --platform linux/amd64
UNIX_MPYCROSS = $(BUILD)/unix-mpy-cross

# Mounted at the same path, so build files and errors name host paths; BUILD too if it's elsewhere.
# safe.directory: on Linux the checkout's owner isn't the container's root.
docker_run = docker run --rm $(1) -v $(CURDIR):$(CURDIR) -w $(CURDIR) \
	$(if $(filter $(CURDIR)/%,$(BUILD)),,-v $(BUILD):$(BUILD)) \
	-e GIT_CONFIG_COUNT=1 -e GIT_CONFIG_KEY_0=safe.directory -e GIT_CONFIG_VALUE_0='*' \
	$(IDF_IMAGE)

.PHONY: all firmware submodules mpy-cross unix packages test test-device info clean

all: firmware

# Not --recursive: that would fetch the submodules of every MicroPython port.
submodules:
	git submodule update --init micropython
	$(call docker_run) make -C micropython/ports/esp32 $(ESP32_ARGS) submodules
	$(call docker_run) make -C micropython/ports/unix $(UNIX_ARGS) submodules

mpy-cross:
	$(call docker_run) make -C micropython/mpy-cross

# Without MICROPY_MPYCROSS the build remakes mpy-cross itself, passing it BUILD=, and fails.
firmware: mpy-cross
	$(call docker_run,-e MICROPY_MPYCROSS=$(CURDIR)/micropython/mpy-cross/build/mpy-cross) \
		make -C micropython/ports/esp32 $(ESP32_ARGS)

# Its own x86-64 mpy-cross: the firmware's runs natively.
unix:
	$(call docker_run,$(UNIX_PLATFORM)) make -C micropython/mpy-cross BUILD=$(UNIX_MPYCROSS)
	$(call docker_run,$(UNIX_PLATFORM)) make -C micropython/ports/unix $(UNIX_ARGS) \
		BUILD=$(BUILD)/unix MICROPY_MPYCROSS=$(UNIX_MPYCROSS)/mpy-cross

# Each lib/ package's package.json, from its manifest.py.
packages:
	$(call docker_run) python3 tools/packages.py

# In Docker too: the unix binary is built for Linux.
test: unix
	$(call docker_run) python3 tools/packages.py --check
	$(call docker_run,$(UNIX_PLATFORM)) $(BUILD)/unix/micropython tests/run.py tests/unix

# PORT is required: mpremote on its own connects to the first device it finds.
require_port = @test -n "$(PORT)" || { echo "Set PORT to the board's serial port"; exit 1; }

# esptool ends with a reset through the EN pin, so the tests see the pins as board_init.c leaves
# them. machine.reset() keeps the GPIO matrix and I2C setup of whatever ran before it.
test-device:
	$(require_port)
	esptool --port $(PORT) chip-id > /dev/null
	mpremote connect $(PORT) sleep 2 mount . run tests/run.py

# Battery, charging and USB state, read without a reset.
info:
	$(require_port)
	mpremote connect $(PORT) run tools/info.py

# mpy-cross builds in its default place in the submodule.
clean:
	rm -rf $(BUILD) micropython/mpy-cross/build
