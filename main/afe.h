#pragma once

/*
 * TUSS4470 receive front-end configuration: the band-pass filter, LNA, log
 * amplifier, echo comparator and zero-crossing comparator registers, handled
 * as one block of raw register values in a fixed order (README "AFE_CONFIG").
 */

#include <stdint.h>

#include "esp_err.h"

#define AFE_REGISTER_COUNT 6U

esp_err_t afe_read(uint8_t values[AFE_REGISTER_COUNT]);
/* Writes all registers, verified by the driver, and logs the configuration. */
esp_err_t afe_write(const uint8_t values[AFE_REGISTER_COUNT]);
void afe_log(const char *event, const uint8_t values[AFE_REGISTER_COUNT]);
