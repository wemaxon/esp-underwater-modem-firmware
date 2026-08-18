idf_component_register(
    SRCS
        "tuss4470.c"

    INCLUDE_DIRS
        "include"

    REQUIRES
        esp_driver_spi
        esp_driver_gpio
)