#include "tuss4470.h"

#include "driver/gpio.h"
#include "esp_check.h"
#include "esp_log.h"

#include "tuss4470_regs.h"
#include "tuss4470_spi.h"

typedef struct {
    tuss4470_config_t config;
    spi_device_handle_t spi_device;
} tuss4470_t;


static const char *TAG = "TUSS4470";
static tuss4470_t tuss4470;


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

uint8_t tuss4470_has_fault(tuss4470_status_t *status)
{
    return status->ee_crc_flt || status->drv_pulse_flt || status->pulse_num_flt || !status->vdrv_ready ;
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
    // ESP_RETURN_ON_FALSE(!tuss4470_has_fault(&status), ESP_ERR_INVALID_STATE, TAG, "TUSS4470 status error: %02X", status.raw);

    tuss4470_spi_response_t spi_response;
    ESP_RETURN_ON_ERROR(tuss4470_spi_read_register(tuss4470.spi_device, TUSS4470_REGISTER_DEVICE_ID, &spi_response), TAG, "Failed to read DEVICE_ID register");
    ESP_LOGI(TAG, "DEVICE_ID raw=%04X status=%02X payload=%02X parity=%u previous_error=%u", spi_response.raw, spi_response.status, spi_response.payload, spi_response.parity, spi_response.previous_frame_parity_error);   

    ESP_RETURN_ON_ERROR(tuss4470_spi_read_register(tuss4470.spi_device, TUSS4470_REGISTER_REV_ID, &spi_response), TAG, "Failed to read REV_ID register");
    ESP_LOGI(TAG, "REV_ID raw=%04X status=%02X payload=%02X parity=%u previous_error=%u", spi_response.raw, spi_response.status, spi_response.payload, spi_response.parity, spi_response.previous_frame_parity_error);   

    ESP_RETURN_ON_ERROR(tuss4470_spi_read_register(tuss4470.spi_device, TUSS4470_REGISTER_VDRV_CTRL, &spi_response), TAG, "Failed to read VDRV_CTRL register");
    ESP_LOGI(TAG, "VDRV_CTRL raw=%04X status=%02X payload=%02X parity=%u previous_error=%u", spi_response.raw, spi_response.status, spi_response.payload, spi_response.parity, spi_response.previous_frame_parity_error);   


    // Enable VDRV
    tuss4470_spi_write_register(tuss4470.spi_device, TUSS4470_REGISTER_VDRV_CTRL, 0x00, &spi_response);
    ESP_LOGI(TAG, "Wrote VDRV_CTRL register: %02X", 0x00);

    ESP_RETURN_ON_ERROR(tuss4470_spi_read_register(tuss4470.spi_device, TUSS4470_REGISTER_VDRV_CTRL, &spi_response), TAG, "Failed to read VDRV_CTRL register");
    ESP_LOGI(TAG, "Read VDRV_CTRL register: %02X", spi_response.payload);

    // // set burst pulse
    // tuss4470_spi_write_register(tuss4470.spi_device, TUSS4470_REGISTER_BURST_PULSE, TUSS4470_BURST_PULSE_MASK | 16, &response);




    ESP_LOGI(TAG, "TUSS4470 initialized");
    return ESP_OK;
}
