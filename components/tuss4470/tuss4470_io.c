#include "tuss4470_io.h"

#include "esp_check.h"
#include "esp_log.h"


static const char* TAG = "TUSS4470_GPIO";


esp_err_t tuss4470_io_init(gpio_num_t io1_io_num){
    gpio_config_t io_config = {
        .pin_bit_mask = 1 << io1_io_num,
        .mode = GPIO_MODE_OUTPUT,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .pull_up_en = GPIO_PULLUP_DISABLE,
    };
    ESP_RETURN_ON_ERROR(gpio_config(&io_config), TAG, "Failed to set gpio config");
    ESP_RETURN_ON_ERROR(gpio_set_level(io1_io_num, 1), TAG, "Failed to set gpio io1 level");

    return ESP_OK;
}