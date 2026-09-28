idf_component_register(
    SRCS 
        "main.c"
        "led.c"
        "usb_transport.c"
        "device_log.c"
        "capture.c"
        "transmit.c"
        "tf/tf_messages.c"
        "tf/tf_protocol.c"
        "../third_party/tinyframe/TinyFrame.c"
    
    INCLUDE_DIRS
        "."
        "include"

    PRIV_INCLUDE_DIRS
        "tf"
        "../third_party/tinyframe"

    REQUIRES
        tuss4470
        esp_driver_usb_serial_jtag
        esp_timer
)
