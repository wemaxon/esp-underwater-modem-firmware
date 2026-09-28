#include "transmit.h"

#include "esp_log.h"
#include "tuss4470.h"

#define VDRV_READY_TIMEOUT_MS 100U

static const char *TAG = "TRANSMIT";

static bool is_valid(const tone_burst_t *tone)
{
    return tone->frequency_hz >= TUSS4470_BURST_MIN_HZ && tone->frequency_hz <= TUSS4470_BURST_MAX_HZ
        && tone->cycles && tone->cycles <= TUSS4470_BURST_MAX_CYCLES;
}

transmit_status_t transmit_send(const tone_burst_t *tone)
{
    if (!is_valid(tone)) {
        ESP_LOGW(TAG, "Rejected invalid tone parameters");
        return TRANSMIT_INVALID;
    }
    ESP_LOGI(TAG, "Tone requested: %lu Hz, %u cycles", (unsigned long)tone->frequency_hz, tone->cycles);

    const char *stage = "enable VDRV";
    esp_err_t error = tuss4470_set_vdrv(true);
    if (error == ESP_OK) {
        stage = "wait for VDRV readiness (burst not started)";
        error = tuss4470_wait_vdrv_ready(VDRV_READY_TIMEOUT_MS);
    }
    if (error == ESP_OK) {
        stage = "send RMT burst";
        ESP_LOGI(TAG, "VDRV ready; starting burst");
        error = tuss4470_burst(tone->frequency_hz, tone->cycles);
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
    if (error != ESP_OK) {
        return TRANSMIT_ERROR;
    }
    ESP_LOGI(TAG, "Burst complete; VDRV disabled");
    return TRANSMIT_OK;
}
