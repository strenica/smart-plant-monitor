#include "buzzer.h"
#include "config.h"

#include "driver/ledc.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

// The Grove Buzzer is a passive piezo: a DC level only clicks it. It needs a
// square wave, and it is loudest at its 2300 Hz resonant frequency. LEDC gives
// us that in hardware, so the CPU does not have to toggle the pin.
//
// 10-bit resolution at 2300 Hz is well within the LEDC divider range. The duty
// sets the volume: 50% is the loudest square wave and is far too loud for a
// desk, so BUZZER_DUTY_PCT in config.h scales it down.

#define BUZZER_MODE     LEDC_LOW_SPEED_MODE
#define BUZZER_TIMER    LEDC_TIMER_0
#define BUZZER_CHANNEL  LEDC_CHANNEL_0
#define BUZZER_RES      LEDC_TIMER_10_BIT
#define BUZZER_FREQ_HZ  2300

#define BUZZER_DUTY_MAX 1024   // 10-bit
#define BUZZER_DUTY_ON  ((BUZZER_DUTY_MAX * BUZZER_DUTY_PCT) / 100)

#define BEEP_ON_MS   150
#define BEEP_GAP_MS  150

void buzzer_init(void)
{
    ledc_timer_config_t timer = {
        .speed_mode      = BUZZER_MODE,
        .duty_resolution = BUZZER_RES,
        .timer_num       = BUZZER_TIMER,
        .freq_hz         = BUZZER_FREQ_HZ,
        .clk_cfg         = LEDC_AUTO_CLK,
    };
    ledc_timer_config(&timer);

    ledc_channel_config_t ch = {
        .gpio_num   = PIN_BUZZER,
        .speed_mode = BUZZER_MODE,
        .channel    = BUZZER_CHANNEL,
        .timer_sel  = BUZZER_TIMER,
        .duty       = 0,
        .hpoint     = 0,
    };
    ledc_channel_config(&ch);
}

static void buzzer_on(void)
{
    ledc_set_duty(BUZZER_MODE, BUZZER_CHANNEL, BUZZER_DUTY_ON);
    ledc_update_duty(BUZZER_MODE, BUZZER_CHANNEL);
}

static void buzzer_off(void)
{
    ledc_set_duty(BUZZER_MODE, BUZZER_CHANNEL, 0);
    ledc_update_duty(BUZZER_MODE, BUZZER_CHANNEL);
}

void buzzer_beep(int times)
{
    for (int i = 0; i < times; i++) {
        buzzer_on();
        vTaskDelay(pdMS_TO_TICKS(BEEP_ON_MS));
        buzzer_off();
        if (i < times - 1) {
            vTaskDelay(pdMS_TO_TICKS(BEEP_GAP_MS));
        }
    }
}
