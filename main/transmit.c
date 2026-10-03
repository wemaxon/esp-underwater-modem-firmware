#include "transmit.h"

#include "esp_log.h"
#include "tuss4470.h"

#define VDRV_READY_TIMEOUT_MS 100U

static const char *TAG = "TRANSMIT";

static bool busy;

static bool is_valid(const tuss4470_tone_t *tones, size_t count)
{
    for (size_t i = 0; i < count; ++i) {
        if (tones[i].frequency_hz < TUSS4470_TONE_MIN_HZ || tones[i].frequency_hz > TUSS4470_TONE_MAX_HZ || !tones[i].cycles) {
            return false;
        }
    }
    return count > 0;
}

static transmit_status_t status_of(esp_err_t error)
{
    return error == ESP_OK ? TRANSMIT_OK : error == ESP_ERR_TIMEOUT ? TRANSMIT_TIMEOUT : TRANSMIT_ERROR;
}

/* Switches VDRV off again; a failure there overrides the transmit result. */
static transmit_status_t finish(esp_err_t error)
{
    esp_err_t cleanup = tuss4470_set_vdrv(false);
    if (cleanup != ESP_OK) {
        ESP_LOGE(TAG, "Failed to disable VDRV: %s", esp_err_to_name(cleanup));
        return TRANSMIT_ERROR;
    }
    return status_of(error);
}

transmit_status_t transmit_start(const tuss4470_tone_t *tones, size_t count)
{
    if (busy || !is_valid(tones, count)) {
        ESP_LOGW(TAG, "Rejected waveform of %u tones", (unsigned)count);
        return TRANSMIT_INVALID;
    }
    ESP_LOGI(TAG, "Transmitting %u tones", (unsigned)count);
    const char *stage = "enable VDRV";
    esp_err_t error = tuss4470_set_vdrv(true);
    if (error == ESP_OK) {
        stage = "wait for VDRV readiness (nothing transmitted)";
        error = tuss4470_wait_vdrv_ready(VDRV_READY_TIMEOUT_MS);
    }
    if (error == ESP_OK) {
        stage = "start transmitting";
        error = tuss4470_transmit_start(tones, count);
    }
    if (error != ESP_OK) {
        ESP_LOGE(TAG, "Failed to %s: %s", stage, esp_err_to_name(error));
        return finish(error);
    }
    busy = true;
    return TRANSMIT_PENDING;
}

transmit_status_t transmit_poll(void)
{
    if (!busy) {
        return TRANSMIT_OK;
    }
    esp_err_t error = tuss4470_transmit_poll();
    if (error == ESP_ERR_NOT_FINISHED) {
        return TRANSMIT_PENDING;
    }
    busy = false;
    if (error != ESP_OK) {
        ESP_LOGE(TAG, "Transmission failed: %s", esp_err_to_name(error));
    }
    transmit_status_t status = finish(error);
    if (status == TRANSMIT_OK) {
        ESP_LOGI(TAG, "Transmission complete; VDRV disabled");
    }
    return status;
}

bool transmit_busy(void)
{
    return busy;
}
