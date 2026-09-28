idf_component_register(
    SRCS
        "tuss4470.c"
        "tuss4470_frame.c"

    INCLUDE_DIRS
        "include"

    PRIV_INCLUDE_DIRS
        "private_include"

    REQUIRES
        esp_driver_spi
        esp_driver_gpio

    PRIV_REQUIRES
        esp_driver_rmt
        esp_timer
)
