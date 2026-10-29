#define MICROPY_HW_BOARD_NAME               "Seeed reTerminal Sticky"
#define MICROPY_HW_MCU_NAME                 "ESP32-S3"
#define MICROPY_PY_NETWORK_HOSTNAME_DEFAULT "mpy-sticky"

// REPL on UART0 through the CH343P bridge: native USB's pads carry the PDM mic.
#define MICROPY_HW_ENABLE_UART_REPL         (1)
#define MICROPY_HW_ENABLE_USBDEV            (0)
// Defaults back on when USBDEV is off.
#define MICROPY_HW_ESP_USB_SERIAL_JTAG      (0)

// SHT40, PCF8563, BQ27220 and LSM6DS3TR-C (the schematic calls this bus I2C1).
#define MICROPY_HW_I2C0_SCL                 (0)
#define MICROPY_HW_I2C0_SDA                 (1)

// GT911 touch only.
#define MICROPY_HW_I2C1_SCL                 (2)
#define MICROPY_HW_I2C1_SDA                 (3)

// Panel and microSD.
#define MICROPY_HW_SPI1_SCK                 (13)
#define MICROPY_HW_SPI1_MOSI                (14)
#define MICROPY_HW_SPI1_MISO                (12)

// No default pins for SPI(2): upstream's are the octal PSRAM bus (GPIO33-37), and a second SPI
// host on the panel's pins would take them from SPI(1).
#define MICROPY_HW_SPI2_SCK                 (-1)
#define MICROPY_HW_SPI2_MOSI                (-1)
#define MICROPY_HW_SPI2_MISO                (-1)

// The card shares the panel's bus, so it's read through a driver on SPI(1). machine.SDCard's
// SPI slots default to the PSRAM pins (slot 2) and to touch and panel pins on SPI(1)'s host (3).
#define MICROPY_PY_MACHINE_SDCARD           (0)

// Holds power and enables charging, before Python starts.
#define MICROPY_BOARD_STARTUP               STICKY_board_startup
void STICKY_board_startup(void);
