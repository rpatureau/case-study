#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Simplified thermal model for NovaCool — standalone script.

Per-rack ODE:  (m·cp)_rack · dT_rack/dt = P_IT − ṁ_rack · cp_air · (T_rack − T_supply)

@author: remi
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# %% Load workload trace and pivot to (n_steps, n_racks) array

workload = pd.read_csv(
    r'/Users/remi/My Drive/CV_US/Hammerhead/case study/instructions/workload_trace.csv',
    parse_dates=['timestamp'],
)
n_racks = workload['rack_id'].nunique()
n_steps = workload['timestamp'].nunique()

# pivot: rows = timesteps (1440), columns = rack_id (200), values = power_kw
P_IT = workload.pivot(index='timestamp', columns='rack_id', values='power_kw').values  # (1440, 200)

# %% Physical constants and facility parameters

Cp_air = 1005.0       # J/(kg·K)

m_rack = 700.0        # kg — effective rack mass (steel + servers)
Cp_rack = 500.0       # J/(kg·K) — effective specific heat
Cap_rack = m_rack * Cp_rack  # 350 000 J/K per rack

n_crahs = 4
racks_per_zone = n_racks // n_crahs   # 50

T_supply = 18.0       # CRAH supply setpoint [°C] — baseline (no control)
fan_speed = 0.85      # fraction of max fan speed
m_dot_crah = 65.0     # kg/s per CRAH at 100% speed
m_dot_rack = m_dot_crah * fan_speed / racks_per_zone  # kg/s per rack

dt = 60.0             # time step [s]

# %% Zone assignment: rack i -> CRAH zone i // racks_per_zone

zone_of_rack = np.arange(n_racks) // racks_per_zone  # (200,)

# %% Time integration — forward Euler

T_rack = np.full(n_racks, T_supply + 12.0)  # initial condition [°C]

# Storage for time-series outputs
T_rack_hist = np.zeros((n_steps, n_racks))

for t in range(n_steps):
    P_w = P_IT[t, :] * 1000.0  # kW -> W
    cooling_w = m_dot_rack * Cp_air * (T_rack - T_supply)
    dT_dt = (P_w - cooling_w) / Cap_rack
    T_rack = T_rack + dt * dT_dt
    T_rack_hist[t, :] = T_rack

# %% Derived quantities

T_outlet = T_rack_hist                            # T_rack ≈ T_outlet
T_inlet = np.full_like(T_outlet, T_supply)        # cold-aisle = supply temp

cold_aisle_mean = T_inlet.mean(axis=1)            # constant here (= T_supply)
hot_aisle_mean = T_outlet.mean(axis=1)
peak_outlet = T_outlet.max(axis=1)

# Cooling power per zone = m_dot_crah * Cp_air * (T_return - T_supply)
# where T_return is the mass-flow-weighted average outlet temp of the zone
cooling_kw_total = np.zeros(n_steps)
for t in range(n_steps):
    for z in range(n_crahs):
        mask = zone_of_rack == z
        T_return_z = T_supply + P_IT[t, mask].sum() * 1000.0 / (m_dot_crah * fan_speed * Cp_air)
        cooling_kw_total[t] += m_dot_crah * fan_speed * Cp_air * (T_return_z - T_supply) / 1000.0

time_h = np.arange(n_steps) * dt / 3600.0  # hours

# %% Plots

fig, axes = plt.subplots(2, 2, figsize=(12, 8), sharex=True)

axes[0, 0].plot(time_h, cold_aisle_mean, label='Cold-aisle mean')
axes[0, 0].set_ylabel('Temperature [°C]')
axes[0, 0].set_title('(a) Average cold-aisle temperature')
axes[0, 0].legend()

axes[0, 1].plot(time_h, hot_aisle_mean, label='Hot-aisle mean')
axes[0, 1].set_ylabel('Temperature [°C]')
axes[0, 1].set_title('(b) Average hot-aisle temperature')
axes[0, 1].legend()

axes[1, 0].plot(time_h, peak_outlet, label='Peak rack outlet')
axes[1, 0].axhline(40.0, color='r', ls='--', label='Safety limit (40 °C)')
axes[1, 0].set_ylabel('Temperature [°C]')
axes[1, 0].set_xlabel('Time [h]')
axes[1, 0].set_title('(c) Peak rack outlet temperature')
axes[1, 0].legend()

axes[1, 1].plot(time_h, cooling_kw_total, label='Total cooling')
axes[1, 1].set_ylabel('Power [kW]')
axes[1, 1].set_xlabel('Time [h]')
axes[1, 1].set_title('(d) Total cooling power')
axes[1, 1].legend()

fig.suptitle('NovaCool — 24 h thermal simulation (lumped rack ODE)', fontsize=14)
fig.tight_layout()
plt.savefig('/Users/remi/My Drive/CV_US/Hammerhead/case study/perso/thermal_results.png', dpi=150)
plt.show()
