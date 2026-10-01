#include "afe.h"

#include "esp_check.h"
#include "esp_log.h"
#include "tuss4470.h"

static const char *TAG = "AFE";

static const struct {
    uint8_t address;
    const char *name;
} registers[AFE_REGISTER_COUNT] = {
    {TUSS4470_REGISTER_BPF_CONFIG_1, "BPF_CONFIG_1"},
    {TUSS4470_REGISTER_BPF_CONFIG_2, "BPF_CONFIG_2"},
    {TUSS4470_REGISTER_DEV_CTRL_1, "DEV_CTRL_1"},
    {TUSS4470_REGISTER_DEV_CTRL_2, "DEV_CTRL_2"},
    {TUSS4470_REGISTER_ECHO_INT_CONFIG, "ECHO_INT_CONFIG"},
    {TUSS4470_REGISTER_ZC_CONFIG, "ZC_CONFIG"},
};

esp_err_t afe_read(uint8_t values[AFE_REGISTER_COUNT])
{
    for (size_t i = 0; i < AFE_REGISTER_COUNT; ++i) {
        ESP_RETURN_ON_ERROR(tuss4470_read_register(registers[i].address, &values[i]), TAG, "Failed to read %s", registers[i].name);
    }
    return ESP_OK;
}

esp_err_t afe_write(const uint8_t values[AFE_REGISTER_COUNT])
{
    for (size_t i = 0; i < AFE_REGISTER_COUNT; ++i) {
        ESP_RETURN_ON_ERROR(tuss4470_write_register(registers[i].address, values[i]), TAG, "Failed to write %s", registers[i].name);
    }
    afe_log("Applied", values);
    return ESP_OK;
}

void afe_log(const char *event, const uint8_t values[AFE_REGISTER_COUNT])
{
    ESP_LOGI(TAG, "%s: %s=0x%02X %s=0x%02X %s=0x%02X %s=0x%02X %s=0x%02X %s=0x%02X", event,
             registers[0].name, values[0], registers[1].name, values[1], registers[2].name, values[2],
             registers[3].name, values[3], registers[4].name, values[4], registers[5].name, values[5]);
}
