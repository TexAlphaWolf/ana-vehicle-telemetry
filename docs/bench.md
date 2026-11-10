# Benchmark

Run on Linux x86_64, 12 CPUs, Python 3.14.10, NumPy 2.5.4; seed 1; each time is the median of 5 runs; command `bench --sizes 10000,100000,1000000,3000000 --repeat 5 --draws 50 --seeds 20 --out /out`.

## 1. Analysis time by log size

Logs are synthetic drive logs at about one sample per second (about 3,750 samples, an hour, per day of driving). *Literal implementation* is the time of the sample-by-sample Python version on a log of 20,000 samples, scaled to each size: an extrapolation, not a measurement.

| Samples | Hours of driving | Time | Samples per second | Literal implementation (extrapolated) | Speed-up |
|---|---|---|---|---|---|
| 10,000 | 3 | 2.6 ms | 3,809,064 | 37.8 ms | 14x |
| 100,000 | 28 | 25.5 ms | 3,927,747 | 378.3 ms | 15x |
| 1,000,000 | 278 | 306.6 ms | 3,261,458 | 3.78 s | 12x |
| 3,000,000 | 833 | 967.7 ms | 3,099,997 | 11.35 s | 12x |

The literal implementation analyses 20,000 samples in 75.7 ms (264,366 samples per second).

## 2. Reading, writing and generating

| Step | Samples | Time | Samples per second |
|---|---|---|---|
| Generate a log with its truth | 52,542 | 60.2 ms | 872,779 |
| Write the CSV text | 52,542 | 226.6 ms | 231,867 |
| Parse the CSV text | 52,542 | 225.3 ms | 233,199 |

## 3. Accuracy against the truth, over 20 synthetic logs

Logs of 14 days with seeds 1 to 20 (18,810 km, 564 trips). Trips: 564 of 564 matched, 0 extra. Error against the true value, per trip, median and 95th percentile: distance 0.03% and 1.10%; consumption 0.17% and 1.35%; trip length 0.4 s and 1.0 s.

| Detector | True | Found | Correct | False alarms | Missed | Missed inside a hole | Precision | Recall |
|---|---|---|---|---|---|---|---|---|
| Harsh acceleration | 308 | 305 | 305 | 0 | 3 | 3 | 100.0% | 99.0% |
| Harsh braking | 210 | 208 | 208 | 0 | 2 | 2 | 100.0% | 99.0% |
| Speed spike | 153 | 152 | 152 | 0 | 1 | - | 100.0% | 99.3% |
| Out-of-range value | 249 | 249 | 249 | 0 | 0 | - | 100.0% | 100.0% |
| Hole in the speed signal | 409 | 409 | 409 | 0 | 0 | - | 100.0% | 100.0% |
| Overheating | 42 | 42 | 42 | 0 | 0 | - | 100.0% | 100.0% |
| Stuck sensor | 35 | 35 | 35 | 0 | 0 | - | 100.0% | 100.0% |

## 4. Agreement with the literal implementation

51 comparisons (a generated log and 50 random, partly spoiled logs with random thresholds): 15,960 numbers compared. Largest relative difference 2.08e-16 (tolerance 1e-09); all match.
