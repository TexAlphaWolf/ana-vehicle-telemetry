# Analysis

Source: [`report.json`](report.json) (the demo log: 14 days of synthetic driving, seed 1) and [`bench.json`](bench.json) (one run
in Docker on Linux x86_64 with 12 CPUs, Python 3.14.10, NumPy 2.5.4; medians of 5 runs). **The vehicle is synthetic**: its mass,
gears and fuel model are those of an ordinary petrol hatchback, chosen to be plausible, not measured. Read the structure of the
results, not the litres.

## 1. The log and its quality

52,542 samples in 27 recording sessions (the engine is off in between), a median of 1.00 s between samples. Faults were injected
at known times; what the analysis found:

| What | Count |
|---|---|
| Samples outside the physical range (made missing) | 7 (speed 4, rpm 1, coolant 2) |
| Speed spikes (made missing) | 13 |
| Holes in the speed signal | 20 (15 interpolated, 5 left as holes) |
| Very short trips dropped | 0 |

- **A hole of up to 10 s is repaired by interpolation, a longer one is not.** Of the 20 holes, 15 were short and were filled; 5
  were 14 to 24 s long and stayed holes. Four trips have a share of their time with no known speed; their distance is a lower bound
  (section 5).
- **The out-of-range values are the codes an adapter reports for a failed sensor** (255 km/h, 16,383.75 rpm, -40 C), not noise.

## 2. Trips and consumption

27 trips, 806.9 km in 13.2 hours of driving, 5.99 L/100 km. The vehicle stands for 15.9% of the driving time. Per trip,
consumption goes from 4.94 to 7.54 L/100 km.

| Average speed of the trip | Trips | km | L/100 km |
|---|---|---|---|
| 0-25 km/h | 3 | 10.1 | 6.26 |
| 25-40 km/h | 2 | 11.0 | 5.53 |
| 40-60 km/h | 8 | 228.3 | 5.28 |
| 60-80 km/h | 12 | 443.8 | 6.25 |
| 80-100 km/h | 2 | 113.7 | 6.45 |

- **The curve is U-shaped, as it should be.** Slow trips spend fuel idling (the engine burns 0.8 L/h standing), fast trips spend
  it against drag, which grows with the square of the speed. The minimum is in the 40 to 60 km/h group.
- **Three groups hold few trips.** The short trips are the least reliable points; the 40 to 80 km/h groups hold 20 of the 27 trips
  and 83% of the distance.

## 3. Driving style

18 harsh accelerations (2.23 per 100 km) and 14 harsh braking events (1.74 per 100 km), counted above 2.5 and 3.0 m/s2 for at
least 1.5 s. The harshest acceleration reached 3.69 m/s2, the harshest braking 4.67 m/s2.

- **Per kilometre, the short trips are the worst**: trip 18 (3.2 km) has 2 harsh accelerations, 61.6 events per 100 km;
  trip 26 (5.1 km) has 2, 39.5 per 100 km. A count per trip would hide that.
- **Firm driving is not harsh.** The generator also produces ramps just under the thresholds (1.9 to 2.3 m/s2 accelerating, 2.4 to
  2.8 braking); none of them was reported, which is what the thresholds are for.
- **Removing the 13 speed spikes does not change the counts** (a one-sample jump is shorter than the minimum event) but it does
  change the maximum speed: without it 6 trips would report up to 212.5 km/h instead of 131.5, and the distance would be 0.25
  km longer.

## 4. Sensor faults

| Fault | Found |
|---|---|
| Coolant above 110 C for 20 s or more | 2 (75 s and 76 s, peaks of 116.0 and 115.7 C) |
| rpm or engine load stuck for 30 s or more | 3 (44, 66 and 47 s, all engine load) |

## 5. Against the truth

On the demo log, all 27 trips are matched. The total distance is off by -0.06%; per trip the distance is off by 0.03% (median) and
1.36% (worst), the consumption by 0.27% and 1.59%, and the trip length by 0.5 s and 1.1 s. All 77 injected events and faults are
found, with no false alarm.

Over 20 synthetic logs of 14 days (seeds 1 to 20; 564 trips, 18,810 km), measured in Docker:

| Detector | True | Found | Missed | Missed inside a hole | Precision | Recall |
|---|---|---|---|---|---|---|
| Harsh acceleration | 308 | 305 | 3 | 3 | 100.0% | 99.0% |
| Harsh braking | 210 | 208 | 2 | 2 | 100.0% | 99.0% |
| Speed spike | 153 | 152 | 1 | - | 100.0% | 99.3% |
| Out-of-range value | 249 | 249 | 0 | - | 100.0% | 100.0% |
| Hole in the speed signal | 409 | 409 | 0 | - | 100.0% | 100.0% |
| Overheating | 42 | 42 | 0 | - | 100.0% | 100.0% |
| Stuck sensor | 35 | 35 | 0 | - | 100.0% | 100.0% |

- **No false alarm in 1,400 detections.** Every threshold is set so that ordinary driving, firm driving and sensor noise
  stay below it.
- **Every missed harsh event fell inside a hole of the data.** A ramp of 3 seconds that happens during a 20 second hole
  is not in the log; no method could find it. This is a property of the data, and it is the reason the report says how much of each trip was
  covered.
- **A hole costs its distance.** A trip with a hole of 20 s at motorway speed is about 500 m short, which is the 1.36%
  of the worst trip. Per trip, over the 20 logs, the distance error is 0.03% at the median and 1.10% at the 95th percentile: the
  tail is the trips with holes.

### What the truth taught

Scoring against a truth found three bugs that no hand-written test had:

1. **A hole inside a long stop split the stop.** A trip ends when the vehicle stands for 10 minutes. A 20 s hole in the speed
   signal during such a stop cut it into two runs of less than 10 minutes, the parking was not seen, and the 12 minutes of
   idling were added to the trip: a consumption 46% too high. The fix is the `bridge_s` parameter: a hole of unknown speed of up
   to 60 s between two stops does not interrupt the stop.
2. **Noise at standstill broke the same stop.** A wheel-speed reading of exactly 1.0 km/h, at the stopping threshold, cut a stop in
   two. The threshold is now 2 km/h, far above the noise of a stopped sensor.
3. **The generator itself overlapped trips** (a weekend errand drawn during a long outing). The truth was wrong, and the scoring, which
   saw trips that could not be matched, was what said so.

## 6. Speed

| Samples | Hours of driving | Time | Samples per second |
|---|---|---|---|
| 10,000 | 3 | 2.6 ms | 3,809,064 |
| 100,000 | 28 | 25.5 ms | 3,927,747 |
| 1,000,000 | 278 | 306.6 ms | 3,261,458 |
| 3,000,000 | 833 | 967.7 ms | 3,099,997 |

- **Linear in the size of the log**, about 3 to 4 million samples a second. A year of driving at one sample per second, if
  the vehicle ran all day, would be 31.5 million samples: 10 seconds.
- **The plain Python implementation does 264,366 samples a second**, so the NumPy one is 12 to 15 times faster (the Python figure
  is a measurement on 20,000 samples, scaled to each size). The speed-up is modest; what the plain version is for is
  being obviously right, not being fast.
- **Reading is the slow part**: parsing the CSV text runs at 233,199 samples a second, more than ten times slower than the analysis.
- **The two agree.** 51 comparisons, 15,960 numbers, largest relative difference 2.08e-16, tolerance 1e-09.

## 7. What this does not show

- It does not show that the thresholds suit your vehicle; they are those of the synthetic one.
- It does not show detection on real faults. The injected ones are clean (a code of 255 km/h, a constant held for a minute); a
  real stuck sensor drifts, and a real overheating is slower. Precision and recall of 100% are a ceiling.
- It does not validate the fuel model: the consumption of the synthetic vehicle is plausible, not measured.
