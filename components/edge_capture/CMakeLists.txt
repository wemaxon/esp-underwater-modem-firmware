idf_component_register(
    SRCS
        "edge_capture.c"
        "edge_decoder.c"

    INCLUDE_DIRS
        "include"

    REQUIRES
        esp_driver_gpio

    PRIV_REQUIRES
        esp_driver_rmt
        esp_ringbuf
        esp_timer
)
