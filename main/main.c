#include <stdio.h>

#include "esp_log.h"
#include "driver/spi_master.h"

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "board.h"
#include "tuss4470.h"


static const char *TAG = "MAIN";

void app_main(void)
{
    spi_bus_config_t buscfg = {
        .miso_io_num = PIN_TUSS4470_SDO,
        .mosi_io_num = PIN_TUSS4470_SDI,
        .sclk_io_num = PIN_TUSS4470_SCK,

        .quadwp_io_num = -1,
        .quadhd_io_num = -1,
        .data4_io_num = -1,
        .data5_io_num = -1,
        .data6_io_num = -1,
        .data7_io_num = -1,
    };
    ESP_ERROR_CHECK(spi_bus_initialize(SPI2_HOST, &buscfg, SPI_DMA_CH_AUTO));


    tuss4470_config_t config = {
        .host_id = SPI2_HOST,
        .spics_io_num = PIN_TUSS4470_CS,
        .io1_io_num = PIN_TUSS4470_IO1,
        .io2_io_num = PIN_TUSS4470_IO2,
        .out3_io_num = PIN_TUSS4470_OUT3,
        .out4_io_num = PIN_TUSS4470_OUT4,
        .vout_io_num = PIN_TUSS4470_VOUT,
    };
    ESP_ERROR_CHECK(tuss4470_init(&config));



    tuss4470_status_t status;
    while(1) {
        vTaskDelay(pdMS_TO_TICKS(1000));
        esp_err_t err = tuss4470_get_status(&status);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "Failed to get TUSS4470 status: %s", esp_err_to_name(err));
        }
        tuss4470_log_status(&status);
    }

}
