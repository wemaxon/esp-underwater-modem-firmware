#pragma once

/*
 * TUSS4470 configuration registers of the receiver (band-pass filter, LNA, log
 * amplifier, echo and zero-crossing comparators) and transmitter (VDRV, drive
 * mode), handled as one block of raw values in a fixed order (README "CONFIG").
 *
 * Bits the firmware relies on are not writable and keep their value: VOUT
 * scaling, the zero-crossing comparator for OUT3, VDRV switching around bursts
 * and continuous burst mode.
 */

#include <stdint.h>

#include "esp_err.h"

#define TUSS_CONFIG_REGISTER_COUNT 8U

esp_err_t tuss_config_read(uint8_t values[TUSS_CONFIG_REGISTER_COUNT]);
/* Writes the writable bits, then reads the result back into applied and logs it. */
esp_err_t tuss_config_write(const uint8_t requested[TUSS_CONFIG_REGISTER_COUNT], uint8_t applied[TUSS_CONFIG_REGISTER_COUNT]);
void tuss_config_log(const char *event, const uint8_t values[TUSS_CONFIG_REGISTER_COUNT]);
