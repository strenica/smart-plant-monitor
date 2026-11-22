# Measured results

Raw captures are in `measurement/data/`, one folder per run. They are not in
git; this file is the record of what they contain.

Reproduce with:

```bash
python3 measurement/summarise_csv.py              # whole capture
python3 measurement/summarise_csv.py --from 120   # skip the first 120 s
```

`--from 120` matters for V3: those captures start with the Pi still running and
booting, so the whole-file mean is not the idle figure.

## The numbers

All at 5 V. Mean current over the steady window.

| Run | Captures | Mean current | Mean power | Wh/day |
|---|---|---|---|---|
| V0 baseline | 3 | 381.4 mA | 1.91 W | 45.8 |
| V1 duty | 3 | 660.6 mA | 3.30 W | 79.3 |
| V2 adaptive | 2 | 380.5 mA | 1.90 W | 45.7 |
| V3 deep sleep | 2 | 268.8 mA | 1.34 W | 32.3 |
| V3 loop | 1 | 522.4 mA | 2.61 W | 62.7 |
| V3, ESP32 not sampling | 1 | 268.8 mA | 1.34 W | 32.3 |
| null (nothing connected) | 1 | −0.03 mA | −0.1 mW | 0 |

Per-capture spread:

| Run | Captures | Spread |
|---|---|---|
| V0 | 379.9, 381.9, 382.4 mA | 2.5 mA |
| V1 | 710.0, 640.6, 631.2 mA | 78.8 mA |
| V2 | 379.7, 381.3 mA | 1.6 mA |
| V3 | 268.3, 269.2 mA | 0.9 mA |

## What the numbers say

**V3 saves 29.5% against V0** (381.4 → 268.8 mA). Not the order of magnitude
the design intends, and the reason is measurable: a halted Pi 4 still draws
268.8 mA, which is the whole of V3's idle.

**The ESP32 contributes almost nothing.** With it deep sleeping and not
sampling the rig draws 268.8 mA; with it deep sleeping and sampling every 60 s
it draws 269.2 mA. The sampling is worth 0.4 mA, which is 0.15% of the total.

There is **no capture with the ESP32 physically unplugged**. An earlier version
of this file claimed one; the folder `v3_esp_only_deepsleep` was misread as
that, but it draws 268.8 mA, so the Pi was connected and the ESP32 was merely
not sampling. Do not claim the unplugged test.

**V2 saves nothing against V0.** 380.5 against 381.4 mA, inside the spread.
Adaptive sampling changes the ESP32's duty cycle by 5×, and the ESP32 is too
small a share of the total for that to show. This is the clearest evidence that
the Pi dominates.

**V1 is the worst rung.** 660.6 mA, 73% above V0, because the camera runs every
60 s and the Pi is on throughout. Fixed duty cycling costs more than doing
nothing, which is worth saying plainly rather than hiding.

**V3 loop costs more than V0.** 522.4 mA. Waking the Pi every 40 s means it is
booting most of the time. That is the point of the run — it measures the cost
of a wake, not a deployment.

## What a slower sampling rate would buy

The deck quotes 380.3 mA for sampling every 60 s instead of every 2 s, a saving
of 1.1 mA or 0.3%. That row is an extrapolation, not a measurement, and this is
where it comes from.

Model the ESP32's average draw as `E/T + idle`, where `E` is the energy of one
sample-and-transmit and `T` is the interval. The 2 s to 10 s step removes
0.9 mA, so

    E * (1/2 - 1/10) = 0.9 mA   ->   E = 2.25 mA*s

Going from 2 s to 60 s then removes

    E * (1/2 - 1/60) = 2.25 * 0.4833 = 1.09 mA

which is 0.3% of 381.4 mA. The honest range is 0 to 1.1 mA, because the 0.9 mA
it is derived from is itself inside the run-to-run spread. Either way the
saving is a fraction of a percent: with the Pi on, the sampling interval is not
a lever. A 30x reduction in the ESP32's work moves the total by less than the
run-to-run spread.

With the Pi halted the answer is the same and simpler — 269.2 mA with the ESP32
sampling every 60 s and 268.8 mA with it not sampling, so there is nothing left
to trade.

## Caveats

- **V0 and V1 captures are 59.6 s, not 180 s.** Both are steady states, and
  V1's camera fires every 60 s, so one capture holds exactly one cycle. Short
  but representative.
- **V2 has two captures, not three.** Spread is 1.6 mA, so a third would not
  change the mean.
- **The V3 captures include a boot transient.** `3deepsleep/1.csv` is
  contaminated for its whole length (496.6 mA even after t > 120 s) and is
  excluded from the V3 figure; `2.csv` and the PowerBox export agree at
  268–269 mA.
- **The PowerBox exports disagree with the HVPM CSVs for V0** — 529.3 against
  381.4 mA for the same variant. The HVPM CSVs are the ones with `.cd5`/`.pt5`
  companions, so they are treated as primary and the PowerBox export is not
  used.
- **A few captures end with a single sample in the megawatt range.** A logging
  artefact; `summarise_csv.py` drops anything above 20 W.
- **`WAKE_ON_GPIO=1` is the load-bearing setting, not `POWER_OFF_ON_HALT`.** It
  is what makes `sudo poweroff` a low-power state that GPIO3 can wake, which is
  the whole of V3. The state below it — `POWER_OFF_ON_HALT=1` together with
  `WAKE_ON_GPIO=0` — switches off every PMIC output, and then GPIO3 cannot wake
  the Pi at all. The 5 V rail is not a PMIC output, so it stays up either way:
  the ESP32 would survive, it would just have nothing to wake. V3's 268.8 mA is
  the price of staying wakeable by a GPIO pulse. Going below it needs the 5 V
  rail cut by a MOSFET, which we did not build.

## Null test

Nothing connected to the HVPM output, 10 s at 5 V: **−0.03 mA**. The meter has
no offset, so the 268.8 mA is real and not an instrument artefact.
