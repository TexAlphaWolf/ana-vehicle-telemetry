# Vehicle telemetry: demo drive log (synthetic, 14 days, seed 1)

52,542 samples from 2026-03-02T08:24:03.339 to 2026-03-14T15:28:43.529 (median 1.00 s between samples), in 27 recording sessions. Channels with data: speed, rpm, throttle, load, coolant, fuel. The log holds 27 trips, 806.9 km in 13.2 hours of driving, 5.99 L/100 km on average.

## 1. Data quality

| What | Count |
|---|---|
| Samples outside the physical range (made missing) | 7 (speed 4, rpm 1, coolant 2) |
| Speed spikes (made missing) | 13 |
| Holes in the speed signal | 20 (15 interpolated, at most 10 s; 5 left as holes) |
| Samples interpolated (all channels) | 536 |
| Samples still missing (all channels) | 540 |
| Very short trips dropped (under 200 m) | 0 |

## 2. Trips

A trip ends when the vehicle stops for at least 10 minutes, or when the logger goes quiet for more than 30 seconds.

| Trip | Start | Minutes | km | Average km/h | Max km/h | Standing | L/100 km | Harsh accel. | Harsh braking |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 2026-03-02 08:24 | 31 | 36.9 | 72 | 131 | 16% | 6.59 | 2 | 1 |
| 2 | 2026-03-02 13:53 | 12 | 5.8 | 28 | 55 | 21% | 5.59 | 0 | 1 |
| 3 | 2026-03-02 17:37 | 31 | 30.9 | 60 | 131 | 19% | 7.14 | 0 | 1 |
| 4 | 2026-03-03 08:09 | 35 | 28.8 | 49 | 106 | 21% | 5.58 | 0 | 0 |
| 5 | 2026-03-03 18:05 | 24 | 21.6 | 54 | 98 | 15% | 5.15 | 0 | 0 |
| 6 | 2026-03-04 08:00 | 34 | 40.2 | 73 | 121 | 13% | 6.19 | 0 | 1 |
| 7 | 2026-03-04 17:39 | 32 | 31.6 | 59 | 102 | 11% | 5.09 | 1 | 0 |
| 8 | 2026-03-05 07:06 | 36 | 31.6 | 53 | 98 | 15% | 5.06 | 1 | 2 |
| 9 | 2026-03-05 17:16 | 29 | 28.7 | 59 | 122 | 13% | 5.69 | 0 | 0 |
| 10 | 2026-03-06 06:54 | 39 | 38.9 | 60 | 102 | 15% | 4.98 | 0 | 0 |
| 11 | 2026-03-06 13:30 | 7 | 1.8 | 16 | 48 | 49% | 7.54 | 0 | 0 |
| 12 | 2026-03-06 17:33 | 28 | 31.4 | 67 | 129 | 14% | 6.66 | 0 | 1 |
| 13 | 2026-03-08 10:56 | 43 | 62.4 | 88 | 131 | 12% | 6.61 | 1 | 0 |
| 14 | 2026-03-08 18:41 | 12 | 5.2 | 26 | 52 | 23% | 5.47 | 1 | 0 |
| 15 | 2026-03-09 06:43 | 39 | 34.5 | 53 | 107 | 15% | 4.94 | 1 | 1 |
| 16 | 2026-03-09 18:33 | 28 | 26.0 | 56 | 105 | 16% | 5.22 | 0 | 0 |
| 17 | 2026-03-10 08:20 | 38 | 43.6 | 68 | 132 | 18% | 6.60 | 0 | 2 |
| 18 | 2026-03-10 13:03 | 8 | 3.2 | 23 | 52 | 35% | 6.46 | 2 | 0 |
| 19 | 2026-03-10 17:55 | 31 | 25.4 | 50 | 109 | 21% | 5.62 | 4 | 0 |
| 20 | 2026-03-11 07:46 | 32 | 33.8 | 64 | 130 | 19% | 6.60 | 0 | 1 |
| 21 | 2026-03-11 18:11 | 38 | 48.1 | 75 | 130 | 10% | 6.00 | 0 | 0 |
| 22 | 2026-03-12 08:10 | 29 | 30.1 | 63 | 123 | 16% | 6.52 | 0 | 1 |
| 23 | 2026-03-12 18:01 | 38 | 39.8 | 63 | 117 | 12% | 5.20 | 1 | 1 |
| 24 | 2026-03-13 06:47 | 37 | 37.6 | 61 | 131 | 17% | 6.71 | 0 | 0 |
| 25 | 2026-03-13 18:21 | 31 | 32.5 | 63 | 124 | 14% | 6.27 | 2 | 0 |
| 26 | 2026-03-14 09:48 | 13 | 5.1 | 24 | 52 | 26% | 5.67 | 2 | 0 |
| 27 | 2026-03-14 14:36 | 37 | 51.3 | 83 | 121 | 10% | 6.26 | 0 | 1 |

## 3. Fuel consumption by average speed

Slow, stop-and-go trips burn fuel idling; fast trips spend it against drag. Trips are grouped by their average speed, and the consumption of a group is its fuel over its distance.

| Average speed of the trip | Trips | km | L/100 km |
|---|---|---|---|
| 0-25 km/h | 3 | 10.1 | 6.26 |
| 25-40 km/h | 2 | 11.0 | 5.53 |
| 40-60 km/h | 8 | 228.3 | 5.28 |
| 60-80 km/h | 12 | 443.8 | 6.25 |
| 80-100 km/h | 2 | 113.7 | 6.45 |

## 4. Driving style

Harsh acceleration is above 2.5 m/s2 and harsh braking above 3 m/s2, for at least 1.5 s. Samples that jump up and back down by more than 12 m/s2 on both sides are spikes, not driving, and are removed first.

| | Events | Per 100 km |
|---|---|---|
| Harsh acceleration | 18 | 2.23 |
| Harsh braking | 14 | 1.74 |

The trips with the most harsh events for their length:

| Trip | Start | km | Harsh accel. | Harsh braking | Events per 100 km |
|---|---|---|---|---|---|
| 18 | 2026-03-10 13:03 | 3.2 | 2 | 0 | 61.6 |
| 26 | 2026-03-14 09:48 | 5.1 | 2 | 0 | 39.5 |
| 14 | 2026-03-08 18:41 | 5.2 | 1 | 0 | 19.2 |
| 2 | 2026-03-02 13:53 | 5.8 | 0 | 1 | 17.3 |
| 19 | 2026-03-10 17:55 | 25.4 | 4 | 0 | 15.7 |

## 5. Sensor faults

| Fault | Start | Seconds | Detail |
|---|---|---|---|
| Coolant above 110 C | 2026-03-05 07:13:21 | 75 | peak 116.0 C |
| Coolant above 110 C | 2026-03-08 11:14:26 | 76 | peak 115.7 C |
| load stuck | 2026-03-05 07:22:48 | 44 | at 32.4 |
| load stuck | 2026-03-05 17:24:51 | 66 | at 41.5 |
| load stuck | 2026-03-11 08:05:53 | 47 | at 39.0 |

## 6. Against the truth

The log is synthetic, so the true distance and fuel of every trip, every harsh ramp and every injected fault are known.

Trips: 27 found for 27 true (27 matched, 0 extra). Distance: total error -0.06%, median per trip 0.03%, worst 1.36%. Consumption: median error per trip 0.27%, worst 1.59%. Trip duration: median error 0.5 s, worst 1.1 s.

| Detector | True | Found | Correct | False alarms | Missed | Precision | Recall |
|---|---|---|---|---|---|---|---|
| Harsh acceleration | 18 | 18 | 18 | 0 | 0 | 100% | 100% |
| Harsh braking | 14 | 14 | 14 | 0 | 0 | 100% | 100% |
| Speed spike | 13 | 13 | 13 | 0 | 0 | 100% | 100% |
| Out-of-range value | 7 | 7 | 7 | 0 | 0 | 100% | 100% |
| Hole in the speed signal | 20 | 20 | 20 | 0 | 0 | 100% | 100% |
| Overheating | 2 | 2 | 2 | 0 | 0 | 100% | 100% |
| Stuck sensor | 3 | 3 | 3 | 0 | 0 | 100% | 100% |

Of the 20 holes injected (15 short, 5 long), 15 were interpolated and 5 left as holes.
