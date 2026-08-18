#include "tuss4470.h"

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


esp_err_t tuss4470_get_status(tuss4470_t* tuss4470, uint8_t *status){
    ESP_RETURN_ON_FALSE(tuss4470->spi_device != NULL, 0, TAG, "TUSS4470 not initialized");
    ESP_RETURN_ON_ERROR(tuss4470_spi_read_register(tuss4470->spi_device, TUSS4470_REGISTER_STATUS, status), TAG, "Failed to read status register");

    if (*status & TUSS4470_DEVSTAT_VDRV_READY) {
        ESP_LOGW(TAG, "VDRV ready");
    }

    if (*status & TUSS4470_DEVSTAT_PULSE_NUM_FLT) {
        ESP_LOGW(TAG, "Pulse number fault");
    }

    if (*status & TUSS4470_DEVSTAT_DRV_PULSE_FLT) {
        ESP_LOGW(TAG, "Driver pulse fault");
    }

    if (*status & TUSS4470_DEVSTAT_EE_CRC_FLT) {
        ESP_LOGW(TAG, "EEPROM CRC fault");
    }
    return ESP_OK;
}



esp_err_t tuss4470_init(tuss4470_config_t *config){
    ESP_RETURN_ON_FALSE(config != NULL, ESP_ERR_INVALID_ARG, TAG, "config is NULL");
    ESP_RETURN_ON_FALSE(config->host_id < SPI_HOST_MAX, ESP_ERR_INVALID_ARG, TAG, "Invalid host_id");
    ESP_RETURN_ON_FALSE(config->spics_io_num >= 0, ESP_ERR_INVALID_ARG, TAG, "Invalid spics_io_num");
    ESP_RETURN_ON_FALSE(config->io1_io_num >= 0, ESP_ERR_INVALID_ARG, TAG, "Invalid io1_io_num");
    ESP_RETURN_ON_FALSE(config->io2_io_num >= 0, ESP_ERR_INVALID_ARG, TAG, "Invalid io2_io_num");
    ESP_RETURN_ON_FALSE(config->out3_io_num >= 0, ESP_ERR_INVALID_ARG, TAG, "Invalid out3_io_num");
    ESP_RETURN_ON_FALSE(config->out4_io_num >= 0, ESP_ERR_INVALID_ARG, TAG, "Invalid out4_io_num");
    ESP_RETURN_ON_FALSE(config->vout_io_num >= 0, ESP_ERR_INVALID_ARG, TAG, "Invalid vout_io_num");

    tuss4470.config = *config;

    spi_device_interface_config_t devcfg = {
        .clock_speed_hz = 1 * 1000 * 1000,
        .mode = 1,
        .spics_io_num = tuss4470.config.spics_io_num,
        .queue_size = 1,
    };
    ESP_RETURN_ON_ERROR(spi_bus_add_device(tuss4470.config.host_id, &devcfg, &tuss4470.spi_device), TAG, "Failed to add SPI device");
    ESP_LOGI(TAG, "Added TUSS4470 spi device");


    // Do not enable when VDRV is below configured voltage
    uint8_t status = 0;
    ESP_RETURN_ON_ERROR(tuss4470_get_status(&tuss4470, &status), TAG, "Failed to read status register");
    ESP_RETURN_ON_FALSE(status == 0, ESP_ERR_INVALID_STATE, TAG, "TUSS4470 status error: %02X", status);



    // Enable VDRV
    tuss4470_spi_write_register(tuss4470.spi_device, TUSS4470_REGISTER_VDRV_CONTROL, TUSS4470_VDRV_HIGH_Z);

    ESP_RETURN_ON_ERROR(tuss4470_get_status(&tuss4470, &status), TAG, "Failed to read status register");
    ESP_RETURN_ON_FALSE(status == 0, ESP_ERR_INVALID_STATE, TAG, "TUSS4470 status error: %02X", status);

    // set burst pulse
    tuss4470_spi_write_register(tuss4470.spi_device, TUSS4470_REGISTER_VDRV_CONTROL, TUSS4470_VDRV_HIGH_Z);




    ESP_LOGI(TAG, "TUSS4470 initialized");
    return ESP_OK;
}