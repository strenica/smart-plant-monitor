#pragma once

void buzzer_init(void);

// Blocking. Emits `times` short beeps, which is how the spec encodes which rule
// fired: rule 2 buzzes twice, rule 3 buzzes three times.
void buzzer_beep(int times);
