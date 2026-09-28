idf_component_register(
    SRCS
        "edge_capture.c"
        "edge_trace.c"

    INCLUDE_DIRS
        "include"

    REQUIRES
        esp_driver_gpio

    PRIV_REQUIRES
        esp_driver_rmt
)
