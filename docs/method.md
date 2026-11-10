# Method

The analysis is a pipeline of seven steps, implemented twice: vectorised in
[`pipeline.py`](../src/vehicletelemetry/pipeline.py) and sample by sample in
[`reference.py`](../src/vehicletelemetry/reference.py). Times are seconds since the first sample; speed is converted to m/s.

## Thresholds

| Parameter (`vtel analyze` option) | Default | Meaning |
|---|---|---|
| `gap_s` | 30 s | Two samples further apart than this: the logger was off, nothing is known in between |
| `max_fill_s` | 10 s | A hole is interpolated when it is at most this long (between the good samples around it) |
| `stop_kmh` | 2 km/h | Below this speed the vehicle is stopped |
| `park_s` | 600 s | A stop this long is parking: the trip ended |
| `bridge_s` | 60 s | A hole of unknown speed this short, between two stops, does not interrupt the stop |
| `min_trip_m` | 200 m | Shorter trips are dropped |
| `accel_ms2` | 2.5 m/s2 | Harsh acceleration threshold |
| `brake_ms2` | 3.0 m/s2 | Harsh braking threshold (a deceleration, so a positive number) |
| `min_event_s` | 1.5 s | A harsh event lasts at least this long |
| `phys_ms2` | 12 m/s2 | No road car accelerates harder: a sample that jumps this much up and back is a spike |
| `rpm_high` | 4000 rpm | Engine speed counted as high |
| `coolant_max_c`, `overheat_s` | 110 C, 20 s | Overheating: the coolant stays above the first for at least the second |
| `flat_s` | 30 s | rpm or engine load that does not change at all for this long: a stuck sensor |
| `afr`, `density_g_l` | 14.7, 745 | Turn a mass air flow column into fuel flow (petrol) |

The validity rules are in [`params.py`](../src/vehicletelemetry/params.py): every number is finite and positive and
`max_fill_s` does not exceed `gap_s`.

## The steps

1. **Range.** A value outside the physical range of its channel (speed 0 to 250 km/h, rpm 0 to 8000, throttle and load 0 to
   100%, coolant -30 to 150 C, fuel 0 to 100 L/h) is a sensor fault and becomes missing. The faults are recorded.
2. **Spikes.** A speed sample is a spike when both neighbours are at most `gap_s` away, the speed jumps by more than `phys_ms2`
   on both sides and the two jumps have opposite signs (up and back, or down and back). It becomes missing. All spikes are
   found on the data as it is after step 1, at once.
3. **Fill.** For every channel, a run of missing samples with a good sample on each side and at most `max_fill_s` between those
   two is replaced by linear interpolation in time. Longer holes stay.
4. **Intervals.** Between two consecutive samples at most `gap_s` apart there is an interval. It is *valid* when the speed is known
   at both ends, and *stopped* when it is valid and both speeds are below `stop_kmh`.
5. **Parking.** A run of stopped intervals is extended over a hole of unknown speed (covered intervals that are not valid) of at
   most `bridge_s`, when another stop follows. A run that lasts `park_s` or more is parking.
6. **Trips.** A trip is a maximal run of covered intervals that are not parking, trimmed to its first and last valid interval,
   at least `min_trip_m` long.
7. **Metrics.** For every trip, over its valid intervals:
   - distance: the trapezoid of the speed, `(v0 + v1) / 2 * dt`;
   - fuel: the trapezoid of the fuel flow over the intervals where speed and fuel are both known, and *L/100 km* is that fuel over
     the distance of the same intervals (so a hole in the fuel channel does not bias it);
   - standing time: the stopped intervals; moving time: the rest;
   - the *covered share*: valid time over the span of the trip, which says how much of it was a hole;
   - high rpm seconds, maximum speed and maximum coolant temperature.

   **Harsh events** are maximal runs of valid intervals inside a trip whose acceleration `(v1 - v0) / dt` is at least `accel_ms2`
   (or at most `-brake_ms2`) and that last at least `min_event_s`. **Overheating** is a run of intervals with the coolant above
   `coolant_max_c` for `overheat_s`; a **stuck sensor** is a run of intervals where rpm (or engine load) is exactly the same for
   `flat_s`.

## The synthetic truth

[`generate.py`](../src/vehicletelemetry/generate.py) draws a plan of trips (commutes, errands and outings, never overlapping, at
least half an hour apart), a speed profile for each (a chain of ramps and holds at ordinary, firm or harsh acceleration), and derives
the channels from a vehicle model: gears chosen by speed, a power balance (inertia, rolling resistance, drag), engine load and
throttle from the power, fuel flow from the power (with a fuel cut when coasting), and a coolant temperature that warms up with a
time constant of 240 s. A sensor then adds noise, rounds the values and jitters the sampling time by up to 0.12 s. The truth of
a trip (distance and fuel) is computed on a 10 Hz grid, independent of the sampling, and ends when the vehicle parks.

Faults are injected after that, at random times and without overlapping: short and long holes (all channels missing), speed spikes,
the out-of-range codes of a failed sensor, overheating (the coolant blends to 113 to 119 C over 70 to 120 s) and stuck sensors
(rpm or load held for 40 to 90 s).

Harsh ramps are built to last at least 3.2 s, so at one sample per second at least two full intervals fall inside them; ordinary
ramps stay at 0.8 to 1.8 m/s2 and firm ones just under the thresholds.

## Scoring

[`score.py`](../src/vehicletelemetry/score.py) matches each true trip to the found trip that covers most of it (at least half),
and each true event to a found event that overlaps it (with a slack of 1.5 s for harsh events, 0.5 s for samples, none for the rest),
one to one. Precision is correct over found, recall correct over true. For harsh events it also counts the misses that fall inside
an injected hole.

## Verification

[`verify.py`](../src/vehicletelemetry/verify.py) runs both implementations on a generated log and on random logs, made hostile at
random (irregular timing, long silences, holes in some channels, impossible and wild values, stuck channels, a cut tail) with
random valid thresholds, and compares every number of the result: floats to a relative 1e-9, everything else exactly.
