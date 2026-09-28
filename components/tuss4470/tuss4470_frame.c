#include "tuss4470_frame.h"

#define FRAME_READ              (1U << 15)
#define FRAME_ADDRESS_SHIFT     9U
#define FRAME_ADDRESS_MASK      0x3FU
#define FRAME_PARITY            (1U << 8)

#define RESPONSE_PREVIOUS_ERROR (1U << 15)
#define RESPONSE_STATUS_SHIFT   9U
#define RESPONSE_STATUS_MASK    0x3FU

#define STATUS_VDRV_READY       (1U << 5)
#define STATUS_PULSE_NUM_FLT    (1U << 4)
#define STATUS_DRV_PULSE_FLT    (1U << 3)
#define STATUS_EE_CRC_FLT       (1U << 2)
#define STATUS_STATE_MASK       0x03U

static uint16_t with_odd_parity(uint16_t frame)
{
    uint16_t value = (uint16_t)(frame & ~FRAME_PARITY);
    unsigned ones = 0;
    for (uint16_t bits = value; bits; bits >>= 1) {
        ones += bits & 1U;
    }
    return (ones & 1U) ? value : (uint16_t)(value | FRAME_PARITY);
}

static uint16_t request(bool read, uint8_t address, uint8_t data)
{
    uint16_t frame = (uint16_t)((address & FRAME_ADDRESS_MASK) << FRAME_ADDRESS_SHIFT) | data;
    if (read) {
        frame |= FRAME_READ;
    }
    return with_odd_parity(frame);
}

uint16_t tuss4470_frame_read(uint8_t address)
{
    return request(true, address, 0);
}

uint16_t tuss4470_frame_write(uint8_t address, uint8_t data)
{
    return request(false, address, data);
}

bool tuss4470_frame_parse_response(uint16_t frame, tuss4470_response_t *response)
{
    if (with_odd_parity(frame) != frame) {
        return false;
    }
    response->data = (uint8_t)frame;
    response->status_bits = (uint8_t)((frame >> RESPONSE_STATUS_SHIFT) & RESPONSE_STATUS_MASK);
    response->previous_frame_error = (frame & RESPONSE_PREVIOUS_ERROR) != 0;
    return true;
}

tuss4470_status_t tuss4470_status_from_bits(uint8_t status_bits)
{
    return (tuss4470_status_t){
        .raw = status_bits,
        .state = (uint8_t)(status_bits & STATUS_STATE_MASK),
        .vdrv_ready = (status_bits & STATUS_VDRV_READY) != 0,
        .pulse_count_fault = (status_bits & STATUS_PULSE_NUM_FLT) != 0,
        .driver_pulse_fault = (status_bits & STATUS_DRV_PULSE_FLT) != 0,
        .eeprom_crc_fault = (status_bits & STATUS_EE_CRC_FLT) != 0,
    };
}
