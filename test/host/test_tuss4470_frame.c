#include <stdint.h>

#include "check.h"
#include "tuss4470_frame.h"

static unsigned ones(uint16_t value)
{
    unsigned count = 0;
    for (; value; value >>= 1) {
        count += value & 1U;
    }
    return count;
}

static void encodes_requests_with_odd_parity(void)
{
    uint16_t read = tuss4470_frame_read(0x1D);
    CHECK((read & 0xFEFFU) == 0xBA00U);         /* read bit, address 0x1D */
    CHECK(ones(read) % 2 == 1);

    uint16_t write = tuss4470_frame_write(0x16, 0x20);
    CHECK(write == 0x2D20U);                    /* address 0x16, data 0x20, parity set */
    CHECK(ones(write) % 2 == 1);
}

static void parses_responses(void)
{
    uint16_t frame = (uint16_t)(0x8000U | (0x2AU << 9) | 0x5AU);
    if (ones(frame) % 2 == 0) {
        frame |= 1U << 8;
    }
    tuss4470_response_t response;
    CHECK(tuss4470_frame_parse_response(frame, &response));
    CHECK(response.data == 0x5A);
    CHECK(response.status_bits == 0x2A);
    CHECK(response.previous_frame_error);
    CHECK(!tuss4470_frame_parse_response((uint16_t)(frame ^ 1U), &response));
}

static void decodes_status_bits(void)
{
    tuss4470_status_t status = tuss4470_status_from_bits(0x21);
    CHECK(status.raw == 0x21);
    CHECK(status.state == 1);    /* burst */
    CHECK(status.vdrv_ready);
    CHECK(!status.pulse_count_fault && !status.driver_pulse_fault && !status.eeprom_crc_fault);

    status = tuss4470_status_from_bits(0x1C);
    CHECK(status.pulse_count_fault && status.driver_pulse_fault && status.eeprom_crc_fault);
}

int main(void)
{
    encodes_requests_with_odd_parity();
    parses_responses();
    decodes_status_bits();
    return 0;
}
