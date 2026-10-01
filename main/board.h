#pragma once

/*
 * Board wiring and bring-up: the only place that knows GPIO numbers.
 * GPIO8 and GPIO9 (IO1, IO2) are ESP32-C3 strapping pins: GPIO9 must not be
 * pulled low during reset, or the chip enters download mode.
 */

#include "driver/gpio.h"
#include "esp_err.h"

#define BOARD_PIN_TUSS4470_IO1   GPIO_NUM_8
#define BOARD_PIN_TUSS4470_IO2   GPIO_NUM_9
#define BOARD_PIN_TUSS4470_OUT3  GPIO_NUM_3
#define BOARD_PIN_TUSS4470_OUT4  GPIO_NUM_2
#define BOARD_PIN_TUSS4470_VOUT  GPIO_NUM_1
#define BOARD_PIN_TUSS4470_SCK   GPIO_NUM_4
#define BOARD_PIN_TUSS4470_SDI   GPIO_NUM_6
#define BOARD_PIN_TUSS4470_SDO   GPIO_NUM_5
#define BOARD_PIN_TUSS4470_CS    GPIO_NUM_7

/* VOUT reaches its ADC pin through a divider: 10 kOhm in series, 4.7 kOhm to GND. */
#define BOARD_VOUT_DIVIDER_TOP_OHMS     10000U
#define BOARD_VOUT_DIVIDER_BOTTOM_OHMS  4700U

/* Initializes the SPI bus and the TUSS4470, configured to output zero crossings on OUT3. */
esp_err_t board_init(void);
