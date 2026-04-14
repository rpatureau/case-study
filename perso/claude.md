Good catch — I actually overstated that number in the previous message. Let me correct it, because the math leads to a cleaner and more illuminating answer.

### The mistake I made

In the previous message I wrote "ΔT_air = Q / C_air = 2,000,000 / 55,500 ≈ 36 K" by plugging in the **zone IT load** (2 MW) as the cooling duty. But that's not what Q actually is in the fixed-ε model — it's what the zone *needs*, not what the coil *can deliver*. You can't just assume the coil removes whatever heat you want; Q is constrained by the effectiveness equation.

### The correct calculation

The fixed-ε model says:

> Q = ε · C_min · (T_return_air − T_chw_supply)

At nominal conditions (ε = 0.70, C_min = C_air ≈ 55,500 W/K, T_return = 30 °C, T_chw_supply = 7 °C, driving ΔT = 23 K):

> **Q = 0.70 × 55,500 × 23 ≈ 894 kW**

Then the air temperature change across the coil comes from the air-side balance `Q = C_air · ΔT_air`:

> **ΔT_air = Q / C_air = 894,000 / 55,500 ≈ 16 K**

So the air actually cools by **16 K**, not 36 K. The coil takes the return air from 30 °C down to roughly 14 °C — which is a realistic CRAH supply temperature.

### Why this specific number — the elegant form

When C_min = C_air (the air is the limiting side), the air temperature drop simplifies dramatically. Starting from the effectiveness definition:

> ΔT_air = Q / C_air = (ε · C_min · driving) / C_air

and since C_min = C_air, the C_air cancels:

> **ΔT_air = ε · (T_return_air − T_chw_supply)**

That's the physical meaning of effectiveness on the air-limited side: ε is literally the **fraction of the maximum possible temperature drop** that the air actually achieves. With ε = 0.70 and a 23 K driving gap, you get 70% × 23 = 16.1 K. An ideal coil (ε = 1) would drop the air all the way down to T_chw_supply = 7 °C; a real coil only gets 70% of the way there.

On the water side, since C_chw > C_air, the water temperature only rises by a smaller amount:

> ΔT_chw = Q / C_chw = 894,000 / 134,000 ≈ **6.7 K**

So the water goes from 7 °C supply to ~13.7 °C return, and the air goes from 30 °C return to ~14 °C supply. The water-side rise is smaller than the air-side drop by exactly the capacity-rate ratio, C_air / C_chw ≈ 0.41.

### The sanity check that catches the error

A useful check: for any counterflow or crossflow HX, the **ratio of the two ΔTs must equal the inverse ratio of C values**:

> ΔT_air / ΔT_chw = C_chw / C_air

16 K / 6.7 K ≈ 2.4, which equals 134,000 / 55,500 ≈ 2.4 ✓. My earlier "36 K air / 15 K water" numbers had the same ratio (~2.4) because I computed both from the same Q, but they violated the effectiveness ceiling — the coil isn't capable of delivering 2 MW at ε = 0.7 and that driving temperature.

### The consequence

This is actually the point of the fixed-ε model: it **exposes the cooling capacity limit** that the baseline "perfect tracker" model hid. In the baseline code, the CRAH just magically delivers whatever supply temperature you ask for (down to T_chw + 3 K). In the fixed-ε model, with these parameters, the coil tops out at ~900 kW per zone ≈ 3.6 MW facility-wide, which is less than the peak workload. The simulator would have to either run fans harder (raising C_air), open CW valves wider (raising C_chw, though it's not the limiting side here), or accept that supply air cannot go below 14 °C — all of which are physically realistic tradeoffs the baseline model skips over.

So the short answer to your question: **the air doesn't cool by 36 K — it cools by about 16 K**, which is ε × (T_return − T_chw_supply). I was sloppy in the previous message and computed Q the wrong way. Good that you pushed back on it.