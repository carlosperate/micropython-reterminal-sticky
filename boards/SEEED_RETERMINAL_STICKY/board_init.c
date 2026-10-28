/*
 * This file is part of the MicroPython project, http://micropython.org/
 *
 * The MIT License (MIT)
 *
 * Copyright (c) 2026 Carlos Pereira Atencio
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in
 * all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
 * THE SOFTWARE.
 */

#include "py/mpconfig.h"

#include "driver/gpio.h"
#include "esp_rom_gpio.h"
#include "esp_rom_sys.h"

#define PIN_SD_CS       (GPIO_NUM_8)
#define PIN_SD_EN       (GPIO_NUM_10)
#define PIN_MIC_EN      (GPIO_NUM_38)
#define PIN_CHG_EN_N    (GPIO_NUM_39)
#define PIN_TP_RST      (GPIO_NUM_41)
#define PIN_TP_EN       (GPIO_NUM_42)
#define PIN_PWR_HOLD    (GPIO_NUM_45)
#define PIN_PWR_LOCK    (GPIO_NUM_46)
#define PIN_EPD_EN      (GPIO_NUM_47)
#define PIN_BUZZER      (GPIO_NUM_48)

// Level first, hold released last, so a pin held through deep sleep never glitches.
// The reset pulls come off, or each would draw about 70uA against the driven level.
static void drive(gpio_num_t pin, int level) {
    gpio_set_level(pin, level);
    esp_rom_gpio_pad_select_gpio(pin);
    gpio_set_pull_mode(pin, GPIO_FLOATING);
    gpio_set_direction(pin, GPIO_MODE_INPUT_OUTPUT);
    gpio_hold_dis(pin);
}

void STICKY_board_startup(void) {
    // On battery the rail stays up only while a flip-flop holds PWR_HOLD, clocked
    // in by a rising edge on PWR_LOCK. The deadline is unknown, so this runs first
    // in app_main, and sdkconfig.board skips the PSRAM test to get here sooner.
    drive(PIN_PWR_HOLD, 1);
    drive(PIN_PWR_LOCK, 0);
    // Levels are set, so release every pad esp32.gpio_deep_sleep_hold() kept in deep sleep.
    gpio_deep_sleep_hold_dis();
    esp_rom_delay_us(10);
    gpio_set_level(PIN_PWR_LOCK, 1);

    // Active low, and the pad's reset pull-up stops charging.
    drive(PIN_CHG_EN_N, 0);

    // The panel never shows an image unless the SD card on its bus is powered and deselected.
    drive(PIN_SD_EN, 1);
    drive(PIN_SD_CS, 1);

    // Other rails off until a driver needs them; touch reset low so it can't power the GT911.
    drive(PIN_EPD_EN, 0);
    drive(PIN_TP_EN, 0);
    drive(PIN_TP_RST, 0);
    drive(PIN_MIC_EN, 0);
    drive(PIN_BUZZER, 0);

    boardctrl_startup();
}
