# Limitations

- **The vehicle is synthetic.** Mass, drag, gears and the fuel model are those of an ordinary petrol hatchback, chosen to be plausible;
  consumption of 5 to 7 L/100 km is an output of that model, not a measurement. The analysis was not run on a real log in this
  repository.
- **The injected faults are clean.** A stuck sensor is a constant held for a minute, an out-of-range value is the code an adapter
  reports, an overheating ramps to a plateau. Real faults drift, flicker and overlap, so precision and recall of 100% are a ceiling,
  not a forecast.
- **The thresholds are those of this vehicle.** 2.5 m/s2 for harsh acceleration and 3.0 for braking suit a hatchback; a van or a
  sports car needs others. A stop of 10 minutes ends a trip, and a driver who waits 8 minutes with the engine running is still on the
  same trip.
- **A hole hides what happened in it.** Holes of more than 10 s are not repaired; a harsh braking inside one is not found (the 5
  misses over 20 logs), and the distance of the trip is a lower bound (its covered share says by how much). A hole of unknown speed
  longer than `bridge_s` inside a long stop splits the stop.
- **Standing is judged from the speed alone.** A noisy speed sensor at standstill, with readings above 2 km/h, would break a
  stop; the default is far above the noise of the synthetic sensor, not necessarily of a real one.
- **Stuck sensors need unquantised values.** A channel that does not change is stuck only if it is *exactly* constant; real adapters
  quantise (coolant in whole degrees, throttle in steps), so a perfectly steady coolant would be reported. Only rpm and engine load
  are checked for this reason, and coolant is not.
- **Fuel comes from the log.** `fuel_lph` or a mass air flow column converted for petrol (diesel engines run lean and the conversion
  is wrong for them). Nothing here measures the tank.
- **Times are medians of a few runs on one computer.** The Python implementation's time is measured on 20,000 samples and scaled.
