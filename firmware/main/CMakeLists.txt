idf_component_register(
    SRCS
        "main.c"
        "sensors.c"
        "dht11.c"
        "buzzer.c"
        "pi_link.c"
        "sample_log.c"
        "rules.c"
    INCLUDE_DIRS "."
    PRIV_REQUIRES
        esp_driver_gpio
        esp_driver_uart
        esp_driver_ledc
        esp_adc
        esp_timer
        esp_hw_support
)
