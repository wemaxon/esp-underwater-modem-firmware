#include "tuss4470.h"

#include "driver/gpio.h"
#include "driver/rmt_tx.h"
#include "esp_check.h"
#include "esp_log.h"
#include "esp_timer.h"

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "tuss4470_io.h"
#include "tuss4470_regs.h"
#include "tuss4470_rmt.h"
#include "tuss4470_spi.h"


typedef struct {
    tuss4470_config_t config;
    spi_device_handle_t spi_device;

    tuss4470_rmt_t rmt;
    rmt_symbol_word_t tx_period;
    bool tx_active;
} tuss4470_t;


static const char *TAG = "TUSS4470";
static tuss4470_t tuss4470;


esp_err_t tuss4470_send_burst(uint32_t frequency_hz, uint16_t cycles)
{
    if (frequency_hz < TUSS4470_TX_MIN_HZ || frequency_hz > TUSS4470_TX_MAX_HZ || !cycles || cycles > TUSS4470_TX_MAX_CYCLES) {
        return ESP_ERR_INVALID_ARG;
    }
    if (!tuss4470.rmt.tx_channel || tuss4470.tx_active) {
        return ESP_ERR_INVALID_STATE;
    }
    uint32_t half_period = (BURST_RMT_RESOLUTION_HZ + frequency_hz) / (2U * frequency_hz);
    tuss4470.tx_period = (rmt_symbol_word_t){
        .level0 = 0, .duration0 = half_period,
        .level1 = 1, .duration1 = half_period,
    };
    rmt_transmit_config_t config = {.loop_count = cycles, .flags.eot_level = 1};
    ESP_RETURN_ON_ERROR(gpio_set_level(tuss4470.config.io1_io_num, 0), TAG, "Failed to enable burst");
    tuss4470.tx_active = true;
    esp_err_t error = rmt_transmit(tuss4470.rmt.tx_channel, tuss4470.rmt.rmt_encoder, &tuss4470.tx_period, sizeof(tuss4470.tx_period), &config);
    if (error == ESP_OK) {
        error = rmt_tx_wait_all_done(tuss4470.rmt.tx_channel, 10);
    }
    esp_err_t released = gpio_set_level(tuss4470.config.io1_io_num, 1);
    if (error != ESP_OK) {
        ESP_RETURN_ON_ERROR(rmt_disable(tuss4470.rmt.tx_channel), TAG, "Failed to stop burst");
        ESP_RETURN_ON_ERROR(rmt_enable(tuss4470.rmt.tx_channel), TAG, "Failed to reset burst channel");
    }
    tuss4470.tx_active = released != ESP_OK;
    return released != ESP_OK ? released : error;
}

esp_err_t tuss4470_get_status(tuss4470_status_t *status)
{
    ESP_RETURN_ON_FALSE(status != NULL, ESP_ERR_INVALID_ARG, TAG, "status is NULL");
    ESP_RETURN_ON_FALSE(tuss4470.spi_device != NULL, ESP_ERR_INVALID_STATE, TAG, "TUSS4470 not initialized");

    tuss4470_spi_response_t response = {0};
    ESP_RETURN_ON_ERROR(tuss4470_spi_read_register(tuss4470.spi_device, TUSS4470_REGISTER_DEV_STAT, &response), TAG, "Failed to read device status");

    if(response.previous_frame_parity_error) {
        ESP_LOGW(TAG, "Previous frame parity error");
    }

    status->raw = response.status;
    return ESP_OK;
}

bool tuss4470_has_fault(tuss4470_status_t *status)
{
    return status->ee_crc_flt || status->drv_pulse_flt || status->pulse_num_flt;
}

void tuss4470_log_status(tuss4470_status_t* status)
{
    static const char *const state_names[] = {
        "LISTEN",
        "BURST",
        "STANDBY",
        "SLEEP",
    };

    ESP_LOGI(TAG, "Device state: %s", state_names[status->dev_state]);

    if (status->vdrv_ready) {
        ESP_LOGI(TAG, "VDRV ready");
    } else {
        ESP_LOGW(TAG, "VDRV not ready");
    }

    if (status->pulse_num_flt) {
        ESP_LOGW(TAG, "Pulse number fault");
    }

    if (status->drv_pulse_flt) {
        ESP_LOGW(TAG, "Driver pulse fault");
    }

    if (status->ee_crc_flt) {
        ESP_LOGW(TAG, "EEPROM CRC fault");
    }
}

esp_err_t tuss4470_set_io_mode(tuss4470_io_mode_t io_mode){
    ESP_RETURN_ON_FALSE(io_mode <= TUSS4470_IO_MODE_3, ESP_ERR_INVALID_ARG, TAG, "Invalid io_mode");

    tuss4470_spi_response_t spi_response = {0};
    ESP_RETURN_ON_ERROR(tuss4470_spi_read_register(tuss4470.spi_device, TUSS4470_REGISTER_DEV_CTRL_3, &spi_response), TAG, "Failed to read IO_MODE register");

    uint8_t value = spi_response.payload;
    value &= (uint8_t)~TUSS4470_DEV3_IO_MODE_MASK;
    value |= (uint8_t)io_mode;

    ESP_RETURN_ON_ERROR(tuss4470_spi_write_register(tuss4470.spi_device, TUSS4470_REGISTER_DEV_CTRL_3, value, &spi_response), TAG, "Failed to write IO_MODE register");
    ESP_LOGV(TAG, "DEV_CTRL_3 raw=0x%04X status=0x%02X payload=0x%02X parity=%u previous_error=%u", spi_response.raw, spi_response.status, spi_response.payload, spi_response.parity, spi_response.previous_frame_parity_error);
    return ESP_OK;
}

esp_err_t tuss4470_set_vdrv(bool enabled) {
    tuss4470_spi_response_t spi_response;
    ESP_RETURN_ON_ERROR(tuss4470_spi_read_register(tuss4470.spi_device, TUSS4470_REGISTER_VDRV_CTRL, &spi_response), TAG, "Failed to read VDRV_CTRL register");

    uint8_t value = spi_response.payload;
    value &= (uint8_t)~TUSS4470_VDRV_HIGH_Z;

    if(!enabled){
        value |= TUSS4470_VDRV_HIGH_Z;
    }

    ESP_RETURN_ON_ERROR(tuss4470_spi_write_register(tuss4470.spi_device, TUSS4470_REGISTER_VDRV_CTRL, value, &spi_response), TAG, "Failed to write VDRV_CTRL register");
    ESP_LOGI(TAG, "VDRV_CTRL raw=0x%04X status=0x%02X payload=0x%02X parity=%u previous_error=%u", spi_response.raw, spi_response.status, spi_response.payload, spi_response.parity, spi_response.previous_frame_parity_error);   
    return ESP_OK;
}

esp_err_t tuss4470_wait_vdrv_ready(uint32_t timeout_ms)
{
    const int64_t deadline_us = esp_timer_get_time() + ((int64_t)timeout_ms * 1000);

    do {
        tuss4470_status_t status = {0};

        ESP_RETURN_ON_ERROR(tuss4470_get_status(&status), TAG, "Failed to read status");
        ESP_RETURN_ON_FALSE(!tuss4470_has_fault(&status), ESP_FAIL, TAG, "Device fault: 0x%02X", status.raw);

        if (status.vdrv_ready) {
            return ESP_OK;
        }

        vTaskDelay(1);
    } while (esp_timer_get_time() < deadline_us);

    return ESP_ERR_TIMEOUT;
}

static esp_err_t tuss4470_set_out3(void) {
    tuss4470_spi_response_t spi_response = {0};

    ESP_RETURN_ON_ERROR(tuss4470_spi_read_register(tuss4470.spi_device, TUSS4470_REGISTER_ZC_CONFIG, &spi_response), TAG, "Failed to read ZC_CONFIG register");

    uint8_t value = spi_response.payload | TUSS4470_ZC_ENABLE;

    ESP_RETURN_ON_ERROR(tuss4470_spi_write_register(tuss4470.spi_device, TUSS4470_REGISTER_ZC_CONFIG, value, &spi_response), TAG, "Failed to write ZC_CONFIG register");
    ESP_LOGI(TAG, "ZC_CONFIG raw=0x%04X status=0x%02X payload=0x%02X parity=%u previous_error=%u", spi_response.raw, spi_response.status, spi_response.payload, spi_response.parity, spi_response.previous_frame_parity_error);

    return ESP_OK;
}

esp_err_t tuss4470_receive_start(void){
    ESP_RETURN_ON_FALSE(tuss4470.spi_device != NULL, ESP_ERR_INVALID_STATE, TAG, "TUSS4470 not initialized");
    return tuss4470_rmt_receive_start(&tuss4470.rmt);
}

esp_err_t tuss4470_receive_stop(void)
{
    ESP_RETURN_ON_ERROR(rmt_disable(tuss4470.rmt.rx_channel), TAG, "Failed to stop RMT RX");
    xQueueReset(tuss4470.rmt.rx_done_queue);
    return rmt_enable(tuss4470.rmt.rx_channel);
}

esp_err_t tuss4470_receive_wait(tuss4470_rx_capture_t *capture, uint32_t timeout_ms){
    ESP_RETURN_ON_FALSE(capture != NULL, ESP_ERR_INVALID_ARG, TAG, "capture is NULL");

    capture->symbols = NULL;
    capture->num_symbols = 0;

    return tuss4470_rmt_receive_wait(&tuss4470.rmt, &capture->symbols, &capture->num_symbols, timeout_ms);
}


esp_err_t tuss4470_init(tuss4470_config_t *config){
    ESP_RETURN_ON_FALSE(config != NULL, ESP_ERR_INVALID_ARG, TAG, "config is NULL");
    ESP_RETURN_ON_FALSE(config->host_id < SPI_HOST_MAX, ESP_ERR_INVALID_ARG, TAG, "Invalid host_id");
    ESP_RETURN_ON_FALSE(GPIO_IS_VALID_OUTPUT_GPIO(config->spics_io_num), ESP_ERR_INVALID_ARG, TAG, "Invalid spics_io_num");
    ESP_RETURN_ON_FALSE(config->io1_io_num >= 0, ESP_ERR_INVALID_ARG, TAG, "Invalid io1_io_num");
    ESP_RETURN_ON_FALSE(config->io2_io_num >= 0, ESP_ERR_INVALID_ARG, TAG, "Invalid io2_io_num");
    ESP_RETURN_ON_FALSE(config->out3_io_num >= 0, ESP_ERR_INVALID_ARG, TAG, "Invalid out3_io_num");
    ESP_RETURN_ON_FALSE(config->out4_io_num >= 0, ESP_ERR_INVALID_ARG, TAG, "Invalid out4_io_num");
    ESP_RETURN_ON_FALSE(config->vout_io_num >= 0, ESP_ERR_INVALID_ARG, TAG, "Invalid vout_io_num");

    tuss4470.config = *config;

    spi_device_interface_config_t devcfg = {
        .clock_speed_hz = 100000,
        .mode = 1,
        .spics_io_num = tuss4470.config.spics_io_num,
        .cs_ena_pretrans = 2,
        .cs_ena_posttrans = 2,
        .queue_size = 1,
    };
    ESP_RETURN_ON_ERROR(spi_bus_add_device(tuss4470.config.host_id, &devcfg, &tuss4470.spi_device), TAG, "Failed to add SPI device");
    ESP_LOGI(TAG, "Added TUSS4470 spi device");

    // tuss4470_status_t status = {0};
    // ESP_RETURN_ON_ERROR(tuss4470_get_status(&status), TAG, "Failed to read status register");
    // tuss4470_log_status(&status);
    // ESP_RETURN_ON_FALSE(!tuss4470_has_fault(&status), ESP_ERR_INVALID_STATE, TAG, "TUSS4470 status error: 0x%02X", status.raw);

    tuss4470_spi_response_t spi_response;
    ESP_RETURN_ON_ERROR(tuss4470_spi_read_register(tuss4470.spi_device, TUSS4470_REGISTER_DEVICE_ID, &spi_response), TAG, "Failed to read DEVICE_ID register");
    ESP_LOGI(TAG, "DEVICE_ID raw=0x%04X status=0x%02X payload=0x%02X parity=%u previous_error=%u", spi_response.raw, spi_response.status, spi_response.payload, spi_response.parity, spi_response.previous_frame_parity_error);   

    ESP_RETURN_ON_ERROR(tuss4470_spi_read_register(tuss4470.spi_device, TUSS4470_REGISTER_REV_ID, &spi_response), TAG, "Failed to read REV_ID register");
    ESP_LOGI(TAG, "REV_ID raw=0x%04X status=0x%02X payload=0x%02X parity=%u previous_error=%u", spi_response.raw, spi_response.status, spi_response.payload, spi_response.parity, spi_response.previous_frame_parity_error);   

    ESP_RETURN_ON_ERROR(tuss4470_set_out3(), TAG, "Failed to configure OUT3");

    ESP_RETURN_ON_ERROR(tuss4470_io_init(tuss4470.config.io1_io_num), TAG, "Failed to init io");

    ESP_RETURN_ON_ERROR(tuss4470_rmt_init(&tuss4470.rmt, tuss4470.config.io2_io_num, tuss4470.config.out3_io_num), TAG, "Failed to init rmt");

    ESP_LOGI(TAG, "TUSS4470 initialized");
    return ESP_OK;
}
