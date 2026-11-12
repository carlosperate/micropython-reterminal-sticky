include(boards/mpconfigboard_esp32s3_common.cmake)

# The IDF resolves a relative partition table path against the port, not this board.
file(WRITE ${CMAKE_BINARY_DIR}/sdkconfig.partitions
    "CONFIG_PARTITION_TABLE_CUSTOM_FILENAME=\"${MICROPY_BOARD_DIR}/partitions.csv\"\n"
)

# No sdkconfig.flash_qio_80m: the stock firmware runs the flash in DIO.
list(APPEND SDKCONFIG_DEFAULTS
    boards/sdkconfig.240mhz
    boards/sdkconfig.spiram_oct
    ${MICROPY_BOARD_DIR}/sdkconfig.board
    ${CMAKE_BINARY_DIR}/sdkconfig.partitions
)

# The IDF applies these only when it creates sdkconfig, and MicroPython reads them unwatched:
# reconfigure when one changes, with sdkconfig made afresh from them.
file(REMOVE ${SDKCONFIG})
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS ${SDKCONFIG_DEFAULTS})

set(MICROPY_SOURCE_BOARD ${MICROPY_BOARD_DIR}/board_init.c)

set(MICROPY_FROZEN_MANIFEST ${MICROPY_BOARD_DIR}/manifest.py)
