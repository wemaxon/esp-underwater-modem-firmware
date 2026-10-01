idf_component_register(
    SRCS
        "main.c"
        "board.c"
        "usb_interface.c"
        "tf_protocol.c"
        "acquisition.c"
        "afe.c"
        "transmit.c"
        "usb_transport.c"
        "device_log.c"

    INCLUDE_DIRS
        "."

    REQUIRES
        tuss4470
        edge_capture
        tinyframe
        esp_adc
        esp_driver_spi
        esp_driver_usb_serial_jtag
        esp_timer
)
