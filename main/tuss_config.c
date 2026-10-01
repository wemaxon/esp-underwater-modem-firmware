#include "tuss_config.h"

#include "esp_check.h"
#include "esp_log.h"
#include "tuss4470.h"

static const char *TAG = "TUSS_CONFIG";

static const struct {
    uint8_t address;
    uint8_t writable;
    const char *name;
} registers[TUSS_CONFIG_REGISTER_COUNT] = {
    {TUSS4470_REGISTER_BPF_CONFIG_1, 0xFF, "BPF_CONFIG_1"},
    {TUSS4470_REGISTER_BPF_CONFIG_2, 0x3F, "BPF_CONFIG_2"},
    {TUSS4470_REGISTER_DEV_CTRL_1, 0xFF, "DEV_CTRL_1"},
    {TUSS4470_REGISTER_DEV_CTRL_2, 0xC3, "DEV_CTRL_2"},           /* VOUT_SCALE_SEL stays at 3.3 V for the VOUT ADC */
    {TUSS4470_REGISTER_ECHO_INT_CONFIG, 0x1F, "ECHO_INT_CONFIG"},
    {TUSS4470_REGISTER_ZC_CONFIG, 0x7F, "ZC_CONFIG"},             /* ZC_CMP_EN stays set: OUT3 is captured */
    {TUSS4470_REGISTER_VDRV_CTRL, 0x1F, "VDRV_CTRL"},             /* VDRV is switched on only for bursts */
    {TUSS4470_REGISTER_BURST_PULSE, 0x80, "BURST_PULSE"},         /* bursts are timed on IO2; no external pre-driver */
};

esp_err_t tuss_config_read(uint8_t values[TUSS_CONFIG_REGISTER_COUNT])
{
    for (size_t i = 0; i < TUSS_CONFIG_REGISTER_COUNT; ++i) {
        ESP_RETURN_ON_ERROR(tuss4470_read_register(registers[i].address, &values[i]), TAG, "Failed to read %s", registers[i].name);
    }
    return ESP_OK;
}

esp_err_t tuss_config_write(const uint8_t requested[TUSS_CONFIG_REGISTER_COUNT], uint8_t applied[TUSS_CONFIG_REGISTER_COUNT])
{
    for (size_t i = 0; i < TUSS_CONFIG_REGISTER_COUNT; ++i) {
        ESP_RETURN_ON_ERROR(tuss4470_update_register(registers[i].address, registers[i].writable, requested[i]),
                            TAG, "Failed to write %s", registers[i].name);
    }
    ESP_RETURN_ON_ERROR(tuss_config_read(applied), TAG, "Failed to read back");
    tuss_config_log("Applied", applied);
    return ESP_OK;
}

void tuss_config_log(const char *event, const uint8_t values[TUSS_CONFIG_REGISTER_COUNT])
{
    ESP_LOGI(TAG, "%s: %s=0x%02X %s=0x%02X %s=0x%02X %s=0x%02X %s=0x%02X %s=0x%02X %s=0x%02X %s=0x%02X", event,
             registers[0].name, values[0], registers[1].name, values[1], registers[2].name, values[2],
             registers[3].name, values[3], registers[4].name, values[4], registers[5].name, values[5],
             registers[6].name, values[6], registers[7].name, values[7]);
}
