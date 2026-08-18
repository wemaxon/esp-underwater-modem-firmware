#include "tuss4470.h"

#include "esp_check.h"
#include "esp_log.h"

#include "tuss4470_regs.h"


typedef struct {
    tuss4470_config_t config;
    spi_device_handle_t spi_device;
} tuss4470_t;


static const char *TAG = "TUSS4470";
static tuss4470_t tuss4470;



esp_err_t tuss4470_init(tuss4470_config_t *config){
    ESP_RETURN_ON_FALSE(config != NULL, ESP_ERR_INVALID_ARG, TAG, "config is NULL");

    tuss4470.config = *config;

    spi_device_interface_config_t devcfg = {
        .clock_speed_hz = 1 * 1000 * 1000,
        .mode = 1,
        .spics_io_num = tuss4470.config.spics_io_num,
        .queue_size = 1,
    };
    
    esp_err_t err = spi_bus_add_device(tuss4470.config.host_id, &devcfg, &tuss4470.spi_device);
    ESP_ERROR_CHECK(err);

    ESP_LOGI(TAG, "Initializing TUSS4470");

    return ESP_OK;
}