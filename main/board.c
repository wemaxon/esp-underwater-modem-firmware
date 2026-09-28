#include "board.h"

#include "driver/spi_master.h"
#include "esp_check.h"
#include "tuss4470.h"

#define TUSS4470_SPI_HOST     SPI2_HOST
#define TUSS4470_SPI_CLOCK_HZ 100000

static const char *TAG = "BOARD";

esp_err_t board_init(void)
{
    spi_bus_config_t bus = {
        .miso_io_num = BOARD_PIN_TUSS4470_SDO,
        .mosi_io_num = BOARD_PIN_TUSS4470_SDI,
        .sclk_io_num = BOARD_PIN_TUSS4470_SCK,
        .quadwp_io_num = -1,
        .quadhd_io_num = -1,
        .data4_io_num = -1,
        .data5_io_num = -1,
        .data6_io_num = -1,
        .data7_io_num = -1,
    };
    ESP_RETURN_ON_ERROR(spi_bus_initialize(TUSS4470_SPI_HOST, &bus, SPI_DMA_CH_AUTO), TAG, "SPI bus initialization failed");

    tuss4470_config_t config = {
        .spi_host = TUSS4470_SPI_HOST,
        .spi_cs_gpio = BOARD_PIN_TUSS4470_CS,
        .spi_clock_hz = TUSS4470_SPI_CLOCK_HZ,
        .io1_gpio = BOARD_PIN_TUSS4470_IO1,
        .io2_gpio = BOARD_PIN_TUSS4470_IO2,
        .verify_writes = true,
    };
    ESP_RETURN_ON_ERROR(tuss4470_init(&config), TAG, "TUSS4470 initialization failed");
    ESP_RETURN_ON_ERROR(tuss4470_update_register(TUSS4470_REGISTER_ZC_CONFIG, TUSS4470_ZC_ENABLE, TUSS4470_ZC_ENABLE),
                        TAG, "Failed to enable OUT3 zero-crossing output");
    return ESP_OK;
}
