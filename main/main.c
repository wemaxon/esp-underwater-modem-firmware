#include "driver/spi_master.h"

#include "board.h"
#include "device_log.h"
#include "tf/tf_messages.h"
#include "usb_transport.h"
#include "esp_timer.h"
#include "tuss4470.h"

void app_main(void)
{
    ESP_ERROR_CHECK(device_log_init());
    spi_bus_config_t bus = {
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
    ESP_ERROR_CHECK(spi_bus_initialize(SPI2_HOST, &bus, SPI_DMA_CH_AUTO));

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
    ESP_ERROR_CHECK(usb_transport_init());
    tf_messages_init();
    int64_t last_tick = esp_timer_get_time();
    for (;;) {
        uint8_t incoming[64];
        int count = usb_transport_read(incoming, sizeof(incoming));
        if (!usb_transport_connected()) {
            tf_messages_reset();
            last_tick = esp_timer_get_time();
            continue;
        }
        if (count > 0) {
            tf_messages_accept(incoming, count);
        }
        int64_t now = esp_timer_get_time();
        while (now - last_tick >= 10000) {
            tf_messages_tick();
            last_tick += 10000;
        }
        tf_messages_poll();
        if (tf_messages_write_failed()) {
            tf_messages_reset();
        }
    }
}
