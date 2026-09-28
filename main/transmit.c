#include "transmit.h"

#include "tuss4470.h"
#include "esp_log.h"

static const char *TAG = "TRANSMIT";

transmit_status_t transmit_send(const tone_burst_t *tone)
{
    if (!tone || tone->frequency_hz < TUSS4470_TX_MIN_HZ || tone->frequency_hz > TUSS4470_TX_MAX_HZ || !tone->cycles || tone->cycles > TUSS4470_TX_MAX_CYCLES) {
        ESP_LOGW(TAG, "Rejected invalid tone parameters");
        return TRANSMIT_INVALID;
    }
    ESP_LOGI(TAG, "Tone requested: %lu Hz, %u cycles", (unsigned long)tone->frequency_hz, tone->cycles);
    const char *stage = "enable VDRV";
    esp_err_t error = tuss4470_set_vdrv(true);
    if (error == ESP_OK) {
        stage = "wait for VDRV readiness (burst not started)";
        error = tuss4470_wait_vdrv_ready(100);
    }
    if (error == ESP_OK) {
        stage = "send RMT burst";
        ESP_LOGI(TAG, "VDRV ready; starting burst");
        error = tuss4470_send_burst(tone->frequency_hz, tone->cycles);
    }
    if (error != ESP_OK) {
        ESP_LOGE(TAG, "Failed to %s: %s", stage, esp_err_to_name(error));
    }
    esp_err_t cleanup = tuss4470_set_vdrv(false);
    if (cleanup != ESP_OK) {
        ESP_LOGE(TAG, "Failed to disable VDRV: %s", esp_err_to_name(cleanup));
        return TRANSMIT_ERROR;
    }
    if (error == ESP_ERR_TIMEOUT) {
        return TRANSMIT_TIMEOUT;
    }
    if (error == ESP_OK) {
        ESP_LOGI(TAG, "Burst complete; VDRV disabled");
    }
    return error == ESP_OK ? TRANSMIT_OK : TRANSMIT_ERROR;
}
