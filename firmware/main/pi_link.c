#include "pi_link.h"
#include "config.h"

#include <string.h>

#include "driver/gpio.h"
#include "driver/uart.h"
#include "esp_log.h"
#include "esp_system.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char *TAG = "pi_link";

#define PI_UART         UART_NUM_2
#define PI_UART_RX_BUF  1024
#define WAKE_PULSE_MS   250

// The Pi 4 wakes when its GPIO3 (physical pin 5) is briefly pulled to ground.
// Open-drain is exactly right for that: level 1 floats like an open switch,
// level 0 pulls to ground like a pressed button. It never drives 3.3 V into the
// Pi, which matters because pin 5 is not a 5 V-tolerant input.
void pi_link_wake(void)
{
    gpio_set_level(PIN_PI_WAKE, 1);   // released before the pin becomes an output
    gpio_config_t cfg = {
        .pin_bit_mask = 1ULL << PIN_PI_WAKE,
        .mode         = GPIO_MODE_OUTPUT_OD,
        .pull_up_en   = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type    = GPIO_INTR_DISABLE,
    };
    gpio_config(&cfg);

    ESP_LOGI(TAG, "pulsing Pi wake line");
    gpio_set_level(PIN_PI_WAKE, 0);
    vTaskDelay(pdMS_TO_TICKS(WAKE_PULSE_MS));
    gpio_set_level(PIN_PI_WAKE, 1);
}

void pi_link_init(void)
{
    // Only press the button on a real start. After a deep-sleep wake the Pi is
    // already running, and pulsing here would restart it on every cycle.
    if (esp_reset_reason() != ESP_RST_DEEPSLEEP) {
        pi_link_wake();
    } else {
        ESP_LOGI(TAG, "deep-sleep wake, not pulsing the Pi");
    }

    uart_config_t cfg = {
        .baud_rate  = 115200,
        .data_bits  = UART_DATA_8_BITS,
        .parity     = UART_PARITY_DISABLE,
        .stop_bits  = UART_STOP_BITS_1,
        .flow_ctrl  = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_DEFAULT,
    };
    ESP_ERROR_CHECK(uart_driver_install(PI_UART, PI_UART_RX_BUF, 0, 0, NULL, 0));
    ESP_ERROR_CHECK(uart_param_config(PI_UART, &cfg));
    ESP_ERROR_CHECK(uart_set_pin(PI_UART, PIN_PI_UART_TX, PIN_PI_UART_RX,
                                 UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE));

    ESP_LOGI(TAG, "UART2 up: TX=GPIO%d RX=GPIO%d at 115200 8N1",
             PIN_PI_UART_TX, PIN_PI_UART_RX);
}

void pi_link_send(const char *text)
{
    uart_write_bytes(PI_UART, text, strlen(text));
    uart_write_bytes(PI_UART, "\n", 1);
}

// One line at a time, with the rest kept for the next call.
//
// The UART hands over whatever happens to be in the FIFO, which can be several
// lines at once: the Pi writes a rule push as five lines 50 ms apart and this
// task polls every 100 ms. Returning the whole block made the caller parse only
// the first line and silently drop the rest, which is how a three-rule push
// ended up saving one rule.
#define PI_RX_LINE 160

static char   s_line[PI_RX_LINE];
static size_t s_line_len;

int pi_link_recv(char *buf, size_t len)
{
    if (len < 2) {
        return 0;
    }

    while (1) {
        char *nl = memchr(s_line, '\n', s_line_len);
        if (nl != NULL) {
            size_t n = (size_t)(nl - s_line);
            if (n > len - 1) {
                n = len - 1;
            }
            memcpy(buf, s_line, n);
            buf[n] = '\0';
            if (n > 0 && buf[n - 1] == '\r') {
                buf[n - 1] = '\0';   // tolerate a CRLF sender
            }

            size_t consumed = (size_t)(nl - s_line) + 1;
            memmove(s_line, s_line + consumed, s_line_len - consumed);
            s_line_len -= consumed;
            return (int)n;
        }

        if (s_line_len >= sizeof(s_line)) {
            s_line_len = 0;   // a line longer than the buffer: drop it, do not wedge
        }

        int got = uart_read_bytes(PI_UART, s_line + s_line_len,
                                  sizeof(s_line) - s_line_len, 0);
        if (got <= 0) {
            return 0;         // nothing more yet
        }
        s_line_len += (size_t)got;
    }
}
