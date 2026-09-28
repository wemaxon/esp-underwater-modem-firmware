#pragma once

/*
 * TUSS4470 SPI frame encoding. Pure functions without ESP-IDF dependencies so
 * they can be tested on the host.
 *
 * Request:  [15] read  [14:9] address  [8] parity  [7:0] data
 * Response: [15] previous frame parity error  [14:9] status  [8] parity  [7:0] data
 * Every frame carries odd parity over all 16 bits.
 */

#include <stdbool.h>
#include <stdint.h>

typedef struct {
    uint8_t data;
    uint8_t status_bits;
    bool previous_frame_error;
} tuss4470_response_t;

/* Device status carried in the status bits of every response. */
typedef struct {
    uint8_t raw;
    uint8_t state;              /* 0 listen, 1 burst, 2 standby, 3 sleep */
    bool vdrv_ready;
    bool pulse_count_fault;
    bool driver_pulse_fault;
    bool eeprom_crc_fault;
} tuss4470_status_t;

uint16_t tuss4470_frame_read(uint8_t address);
uint16_t tuss4470_frame_write(uint8_t address, uint8_t data);

/* Returns false when the response fails its parity check. */
bool tuss4470_frame_parse_response(uint16_t frame, tuss4470_response_t *response);

tuss4470_status_t tuss4470_status_from_bits(uint8_t status_bits);

static inline bool tuss4470_status_has_fault(const tuss4470_status_t *status)
{
    return status->pulse_count_fault || status->driver_pulse_fault || status->eeprom_crc_fault;
}
