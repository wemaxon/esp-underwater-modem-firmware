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

    ESP_ERROR_CHECK(tuss4470_set_io_mode(TUSS4470_IO_MODE_1));
    ESP_ERROR_CHECK(tuss4470_set_vdrv(true));


    while(1) {
        tuss4470_status_t status = {0};
        esp_err_t err = tuss4470_get_status(&status);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "Failed to get status: %s", esp_err_to_name(err));
        } else {
            tuss4470_log_status(&status);
        }

        if (tuss4470_wait_vdrv_ready(100) == ESP_OK){
            err = tuss4470_receive_start();
            if (err != ESP_OK) {
                ESP_LOGE(TAG, "Failed to start receive capture: %s", esp_err_to_name(err));
                vTaskDelay(pdMS_TO_TICKS(2000));
                continue;
            }

            err = tuss4470_send_burst(40000, 32);
            if (err != ESP_OK) {
                ESP_LOGE(TAG, "Failed to send burst: %s", esp_err_to_name(err));
            }
            else {
                ESP_LOGI(TAG, "Sent burst");

                tuss4470_rx_capture_t capture = {0};
                err = tuss4470_receive_wait(&capture, 50);
                if (err == ESP_OK) {
                    ESP_LOGI(TAG, "Captured %u OUT3 symbols", (unsigned)capture.num_symbols);

                    size_t symbols_to_log = capture.num_symbols < 16 ? capture.num_symbols : 16;
                    for (size_t i = 0; i < symbols_to_log; i++) {
                        const rmt_symbol_word_t *symbol = &capture.symbols[i];
                        ESP_LOGI(TAG, "OUT3[%u]: level0=%u duration0=%u level1=%u duration1=%u", (unsigned)i, symbol->level0, symbol->duration0, symbol->level1, symbol->duration1);
                    }
                } else {
                    ESP_LOGW(TAG, "OUT3 capture failed: %s", esp_err_to_name(err));
                }
            }
        }
        else{
            ESP_LOGW(TAG, "VDRV did not become ready" );
        }

        vTaskDelay(pdMS_TO_TICKS(2000));
    }
}
