#include "tuss4470_spi.h"

#include "esp_check.h"


#define TUSS4470_PARITY_BIT     (1U << 8)
#define TUSS4470_READ_BIT       (1U << 15)

static const char *TAG = "TUSS4470_SPI";


uint16_t tuss4470_spi_set_parity(uint16_t frame)
{
    uint16_t value = frame & ~TUSS4470_PARITY_BIT;
    uint16_t temp = value;
    uint8_t ones = 0;

    while (temp != 0U)
    {
        ones += (uint8_t)(temp & 1U);
        temp >>= 1U;
    }

    if ((ones & 1U) == 0U)
    {
        value |= TUSS4470_PARITY_BIT;
    }

    return value;
}

esp_err_t tuss4470_spi_write_register(spi_device_handle_t spi, uint8_t address, uint8_t data){
    ESP_RETURN_ON_FALSE(spi != NULL, ESP_ERR_INVALID_ARG, TAG, "spi is NULL");

    uint16_t frame = 0U;
    frame |= (uint16_t)(address & 0x3FU) << 9U;
    frame |= (uint16_t)(data & 0xFFU);
    frame = tuss4470_spi_set_parity(frame);

    spi_transaction_t t = {
        .flags = SPI_TRANS_USE_TXDATA,
        .tx_data = { (uint8_t)(frame >> 8U), (uint8_t)(frame & 0xFFU) },
        .length = 16,
    };
    return spi_device_transmit(spi, &t);
}

esp_err_t tuss4470_spi_read_register(spi_device_handle_t spi, uint8_t address, uint8_t *data){
    ESP_RETURN_ON_FALSE(spi != NULL, ESP_ERR_INVALID_ARG, TAG, "spi is NULL");
    ESP_RETURN_ON_FALSE(data != NULL, ESP_ERR_INVALID_ARG, TAG, "data is NULL");

    uint16_t frame = 0U;
    frame |= TUSS4470_READ_BIT;
    frame |= (uint16_t)(address & 0x3FU) << 9U;
    frame = tuss4470_spi_set_parity(frame);

    spi_transaction_t t = {
        .flags = SPI_TRANS_USE_TXDATA | SPI_TRANS_USE_RXDATA,
        .length = 16,
        .rxlength = 16,

        .tx_data = {
            (uint8_t)(frame >> 8U),
            (uint8_t)(frame & 0xFFU)
        },
    };

    ESP_RETURN_ON_ERROR(spi_device_transmit(spi, &t), TAG, "Failed to transmit SPI transaction");

    *data = t.rx_data[1];
    return ESP_OK;
}