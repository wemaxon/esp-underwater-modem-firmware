#pragma once

/*
 * TUSS4470 ultrasonic driver/receiver IC: SPI register access, VDRV control
 * and transmit waveforms on IO1/IO2 (IO mode 1).
 *
 * The chip's receive outputs (VOUT, OUT3, OUT4) are plain signals and are
 * acquired elsewhere. Supports one chip; not thread-safe.
 */

#include <stdbool.h>
#include <stdint.h>

#include "driver/gpio.h"
#include "driver/spi_master.h"
#include "esp_err.h"
#include "tuss4470_regs.h"
#include "tuss4470_waveform.h"

typedef struct {
    spi_host_device_t spi_host;     /* bus must already be initialized */
    gpio_num_t spi_cs_gpio;
    int spi_clock_hz;
    gpio_num_t io1_gpio;
    gpio_num_t io2_gpio;
    bool verify_writes;             /* read back every register write and fail on mismatch */
} tuss4470_config_t;

esp_err_t tuss4470_init(const tuss4470_config_t *config);

esp_err_t tuss4470_read_register(uint8_t address, uint8_t *value);
esp_err_t tuss4470_write_register(uint8_t address, uint8_t value);
/* Read-modify-write: only the bits set in mask are replaced by value. */
esp_err_t tuss4470_update_register(uint8_t address, uint8_t mask, uint8_t value);

esp_err_t tuss4470_set_vdrv(bool enabled);
/* Fails with ESP_FAIL on a device fault and ESP_ERR_TIMEOUT if VDRV is not ready in time. */
esp_err_t tuss4470_wait_vdrv_ready(uint32_t timeout_ms);

/*
 * Starts transmitting the tones without blocking. Each frequency is rounded to
 * the nearest half period of the 20 MHz transmit clock. tones must stay valid
 * until tuss4470_transmit_poll() reports the end.
 */
esp_err_t tuss4470_transmit_start(const tuss4470_tone_t *tones, size_t count);
/* ESP_ERR_NOT_FINISHED while transmitting; afterwards the result, once. */
esp_err_t tuss4470_transmit_poll(void);
