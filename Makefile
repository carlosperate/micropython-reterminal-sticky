# Builds run in Espressif's IDF image, so every machine gets the same toolchain.
# Flashing runs on the host: Docker on macOS can't reach USB devices.

IDF_IMAGE ?= espressif/idf:v5.5.2

BOARD ?= SEEED_RETERMINAL_STICKY
BOARD_VARIANT ?=

BUILD ?= $(CURDIR)/build
FIRMWARE_BUILD = $(BUILD)/$(BOARD)$(if $(BOARD_VARIANT),-$(BOARD_VARIANT))

ESP32_ARGS = BOARD=$(BOARD) BOARD_VARIANT=$(BOARD_VARIANT) BUILD=$(FIRMWARE_BUILD)
# A board in boards/ is ours; any other name is one of upstream's.
ifneq ($(wildcard boards/$(BOARD)/.),)
ESP32_ARGS += BOARD_DIR=$(CURDIR)/boards/$(BOARD)
endif

# The image has no pkg-config to find libffi, and nothing here needs ffi.
UNIX_ARGS = MICROPY_PY_FFI=0

# Mounted at the same path, so build files and errors name host paths.
# safe.directory: on Linux the checkout's owner isn't the container's root.
docker_run = docker run --rm $(1) -v $(CURDIR):$(CURDIR) -w $(CURDIR) \
	-e GIT_CONFIG_COUNT=1 -e GIT_CONFIG_KEY_0=safe.directory -e GIT_CONFIG_VALUE_0='*' \
	$(IDF_IMAGE)

.PHONY: all firmware submodules mpy-cross unix unix-amd64 clean

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

unix: mpy-cross
	$(call docker_run) make -C micropython/ports/unix $(UNIX_ARGS) BUILD=$(BUILD)/unix

# Emulated on Apple silicon: MicroPython has no arm64 native emitter for viper.
# It needs an x86-64 mpy-cross of its own.
unix-amd64:
	$(call docker_run,--platform linux/amd64) make -C micropython/mpy-cross \
		BUILD=$(BUILD)/amd64/mpy-cross
	$(call docker_run,--platform linux/amd64) make -C micropython/ports/unix $(UNIX_ARGS) \
		BUILD=$(BUILD)/amd64/unix MICROPY_MPYCROSS=$(BUILD)/amd64/mpy-cross/mpy-cross

# mpy-cross builds in its default place in the submodule.
clean:
	rm -rf $(BUILD) micropython/mpy-cross/build
