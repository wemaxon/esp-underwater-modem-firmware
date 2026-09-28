#include "transmit.h"

#include "tuss4470.h"

transmit_status_t transmit_send(const tone_burst_t *tone)
{
    if (!tone || tone->frequency_hz < TUSS4470_TX_MIN_HZ || tone->frequency_hz > TUSS4470_TX_MAX_HZ || !tone->cycles || tone->cycles > TUSS4470_TX_MAX_CYCLES) {
        return TRANSMIT_INVALID;
    }
    esp_err_t error = tuss4470_set_vdrv(true);
    if (error == ESP_OK) {
        error = tuss4470_wait_vdrv_ready(100);
    }
    if (error == ESP_OK) {
        error = tuss4470_send_burst(tone->frequency_hz, tone->cycles);
    }
    if (tuss4470_set_vdrv(false) != ESP_OK) {
        return TRANSMIT_ERROR;
    }
    if (error == ESP_ERR_TIMEOUT) {
        return TRANSMIT_TIMEOUT;
    }
    return error == ESP_OK ? TRANSMIT_OK : TRANSMIT_ERROR;
}
