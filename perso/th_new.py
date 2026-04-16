#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Apr 13 21:47:50 2026

@author: remi

Thermal model for a 200-rack, 4-zone data center.
  - Task 1: air-side thermal balance (rack inlet/outlet temperatures, cooling load)
  - Task 2: full power chain (UPS, fans, pumps, chiller, PUE)
  - Task 3: validation against sensor reference data
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

# %% Task 1 — Load workload trace and pivot to (n_steps, n_racks) array

workload = pd.read_csv(
    r'C:\drive\CV_US\Hammerhead\case study\instructions\workload_trace.csv',
    parse_dates=['timestamp'])
n_racks = workload['rack_id'].nunique()   # 200 racks
n_steps = workload['timestamp'].nunique() # 1440 one-minute timesteps (24 h)

# Pivot so each row is a timestep and each column is a rack's IT power draw
P_IT = workload.pivot(index='timestamp', columns='rack_id', values='power_kw').values  # (1440, 200)

# %% Physical constants

Cp_air = 1005.0       # J/(kg·K) — specific heat of air at ~25 °C

# %% Air-side thermal model (per-rack → per-zone)

# Cold-aisle supply temperature delivered by CRAHs
T_rack_supply = 8.5   # °C

# Design air temperature rise across each rack (hot aisle − cold aisle)
dT_air = 20          # °C

# Air mass flow rate needed per rack: P = m_dot * Cp * dT  →  m_dot = P / (Cp * dT)
m_flow = P_IT * 1000 / Cp_air / dT_air  # (1440, 200) kg/s per rack

# Aggregate to 4 cooling zones — each CRAH serves 50 consecutive racks
# Zone 0: racks 0-49, Zone 1: racks 50-99, Zone 2: racks 100-149, Zone 3: racks 150-199
m_flow_crah = m_flow.reshape(n_steps, 4, 50).sum(axis=2)  # (1440, 4) kg/s per CRAH
P_IT_crah = P_IT.reshape(n_steps, 4, 50).sum(axis=2)      # (1440, 4) kW per CRAH

# Hot-aisle (return) temperature: T_return = T_supply + Q / (m_dot * Cp)
T_rack_return = T_rack_supply + P_IT_crah * 1000 / m_flow_crah / Cp_air

# %% Chilled-water loop (CRAH coil heat exchange)

Cp_water = 4186.0      # J/(kg·K) — specific heat of water
T_water_supply = 7.0   # °C — chilled water supply from chiller
T_water_return = 35.0  # °C — warm water returning to chiller
eta_water = 0.7        # CRAH coil heat-exchanger effectiveness (ε)

# Heat removed by each CRAH coil: Q = ε · C_min · (T_hot_in − T_cold_in)
# Here C_min = C_air = m_dot_air * Cp_air  (air side is the limiting stream)
Q = eta_water * m_flow_crah * Cp_air * (T_rack_return - T_water_supply)

# Water flow rate needed per CRAH to carry away Q at the design ΔT
m_flow_water = Q / Cp_water / (T_water_return - T_water_supply)

# Facility-wide totals across all 4 CRAHs
Q_water_total = Q.sum(axis=1)                  # (1440,) kW — total chiller duty
m_flow_water_total = m_flow_water.sum(axis=1)  # (1440,) kg/s — total water flow


# --- Task 1 plots: temperatures and total cooling load ---
sns.set_style("whitegrid")

fig, axes = plt.subplots(1, 2, figsize=(11, 4))

# Left: supply (cold-aisle) vs return (hot-aisle) temperature over time
axes[0].plot(T_rack_return.mean(axis = 1), label = 'Average cold-aisle temperature')
axes[0].plot([T_rack_supply] * 1440, label = 'Average hot-aisle temperature')
axes[0].set_title('Temperatures (in °C)')
axes[0].margins(x=0)
axes[0].legend(loc = 'lower center', bbox_to_anchor=[0.5, -0.2], ncol = 2)

# Right: total IT load across all zones (converted kW → MW)
axes[1].set_title('Total cooling power consumed (in MW)')
axes[1].plot(P_IT_crah.sum(axis = 1) / 1000)
axes[1].margins(x=0)
plt.tight_layout()
plt.savefig(r'C:\drive\CV_US\Hammerhead\case study\final\plots\task1.pdf', bbox_inches='tight')
plt.show()

# %% Task 2 — Power & System Coupling
#
# Build the full power chain from IT load through UPS, cooling subsystems,
# and ancillary loads to compute the Power Usage Effectiveness (PUE).

P_IT_total = P_IT.sum(axis=1)  # (1440,) kW — total IT load across all racks

# --- UPS efficiency (quadratic model, 2N redundant topology) ---
# In 2N redundancy each UPS module carries half the total IT load.
# Efficiency peaks at x_peak and falls off quadratically.
IT_capacity_kw = 10_000.0  # 10 MW design IT capacity
x_load = (P_IT_total / 2) / (IT_capacity_kw / 2)  # per-module load fraction
eta_ups_peak = 0.965  # peak efficiency at optimal load
x_peak = 0.65         # load fraction where peak efficiency occurs
k_ups = 0.20          # curvature of the quadratic roll-off
eta_ups = np.clip(eta_ups_peak - k_ups * (x_load - x_peak) ** 2, 0.80, eta_ups_peak)
P_UPS_input = P_IT_total / eta_ups  # kW — electrical power drawn from grid by UPS

# --- CRAH fans (affinity law: P ∝ speed³) ---
fan_speed = 0.85              # constant fan speed fraction (85 %)
P_fan_nominal = 55.0          # kW per CRAH at 100 % speed
P_fans = 4 * P_fan_nominal * fan_speed ** 3  # kW — all 4 CRAHs, constant

# --- Chilled-water pumps (affinity law: P ∝ flow³) ---
P_pump_nominal = 18.0  # kW per pump at design flow
# Design flow at full IT capacity
m_flow_water_design = IT_capacity_kw * 1000 / (Cp_water * (T_water_return - T_water_supply))
flow_frac = np.clip(m_flow_water_total / m_flow_water_design, 0.0, 1.0)
P_pumps = 4 * P_pump_nominal * flow_frac ** 3  # kW — scales with cube of flow fraction

# --- Chiller (electrical power = thermal duty / COP) ---
COP = 4.8
P_chiller = Q_water_total / COP  # kW

# --- Ancillary loads (lighting, network gear, security ≈ 1 % of IT capacity) ---
P_other = 0.01 * IT_capacity_kw  # kW — constant

# --- PUE: ratio of total facility power to IT power ---
P_total = P_UPS_input + P_fans + P_pumps + P_chiller + P_other
PUE = P_total / P_IT_total


# --- Task 2 plots: 2×2 dashboard of power chain quantities ---
time_h = np.arange(n_steps) / 60.0  # convert minute index to hours

fig, axes = plt.subplots(2, 2, figsize=(12, 8), sharex=True)

# Top-left: total IT load over time
axes[0, 0].plot(time_h, P_IT_total / 1000)
axes[0, 0].set_ylabel('Power [MW]')
axes[0, 0].set_title('IT Load')

# Top-right: UPS efficiency tracks load fraction
axes[0, 1].plot(time_h, eta_ups)
axes[0, 1].set_ylabel('Efficiency')
axes[0, 1].set_title('UPS Efficiency')

# Bottom-left: cooling subsystem power (chiller dominates; fans constant)
axes[1, 0].plot(time_h, P_chiller, label='Chiller')
axes[1, 0].plot(time_h, np.full(n_steps, P_fans), label='Fans')
axes[1, 0].plot(time_h, P_pumps, label='Pumps')
axes[1, 0].set_ylabel('Power [kW]')
axes[1, 0].set_xlabel('Time [h]')
axes[1, 0].set_title('Cooling power breakdown')
axes[1, 0].legend()

# Bottom-right: PUE — closer to 1.0 is more efficient
axes[1, 1].plot(time_h, PUE)
axes[1, 1].set_ylabel('PUE')
axes[1, 1].set_xlabel('Time [h]')
axes[1, 1].set_title('Power Usage Effectiveness')

fig.tight_layout()
plt.savefig(r'C:\drive\CV_US\Hammerhead\case study\final\plots\task2.pdf', bbox_inches='tight')
plt.show()

# %% Task 3 — Model validation against sensor reference data
#
# Compare the simplified thermal model's predictions (uniform supply temp,
# zone-averaged return temp) to per-rack sensor measurements.

sensor = pd.read_csv(r'C:\drive\CV_US\Hammerhead\case study\instructions\sensor_reference.csv',
                     parse_dates=['timestamp'])

# Pivot reference sensor data to (1440, 200) arrays matching the model shape
ref_inlet = sensor.pivot(index='timestamp', columns='rack_id', values='inlet_temp_c').values
ref_outlet = sensor.pivot(index='timestamp', columns='rack_id', values='outlet_temp_c').values

# Model predictions — broadcast per-zone values to per-rack arrays
zone_of_rack = np.arange(n_racks) // 50          # maps each rack to its zone (0–3)
sim_inlet = np.full_like(ref_outlet, T_rack_supply)  # uniform supply temp for all racks
sim_outlet = T_rack_return[:, zone_of_rack]           # zone return temp assigned to each rack

# --- Error metrics: inlet temperature ---
err_inlet = sim_inlet - ref_inlet
RMSE_inlet = np.sqrt(np.mean(err_inlet ** 2))
MAE_inlet = np.mean(np.abs(err_inlet))
MaxAE_inlet = np.abs(err_inlet).max()

# --- Error metrics: outlet temperature ---
err_outlet = sim_outlet - ref_outlet
RMSE_outlet = np.sqrt(np.mean(err_outlet ** 2))
MAE_outlet = np.mean(np.abs(err_outlet))
MaxAE_outlet = np.abs(err_outlet).max()

# --- Mass flow rates: derive reference from sensor energy balance ---
# Back-calculate air flow from measured power and temperature rise: m_dot = P / (Cp * ΔT)
# Floor ΔT at 0.1 °C to avoid division by near-zero
ref_power = sensor.pivot(index='timestamp', columns='rack_id', values='pdu_power_kw').values
ref_m_flow = ref_power * 1000 / (Cp_air * np.maximum(ref_outlet - ref_inlet, 0.1))  # (1440, 200)
# Simulated flow: total zone flow divided equally among 200 racks (simplified)
sim_m_flow = np.maximum(m_flow_crah.sum(axis = 1) / 200, 1)

# err_m_flow = sim_m_flow - ref_m_flow
# RMSE_m_flow = np.sqrt(np.mean(err_m_flow ** 2))
# MAE_m_flow = np.mean(np.abs(err_m_flow))
# MaxAE_m_flow = np.abs(err_m_flow).max()

print("=== Task 3 — Validation metrics ===")
print(f"Inlet  — RMSE: {RMSE_inlet:.2f} °C  MAE: {MAE_inlet:.2f} °C  MaxAE: {MaxAE_inlet:.2f} °C")
print(f"Outlet — RMSE: {RMSE_outlet:.2f} °C  MAE: {MAE_outlet:.2f} °C  MaxAE: {MaxAE_outlet:.2f} °C")
# print(f"m_flow — RMSE: {RMSE_m_flow:.4f} kg/s  MAE: {MAE_m_flow:.4f} kg/s  MaxAE: {MaxAE_m_flow:.4f} kg/s")

# --- Per-timestep MAE to identify when the model diverges most ---
mae_per_step_inlet = np.mean(np.abs(err_inlet), axis=1)   # (1440,)
mae_per_step_outlet = np.mean(np.abs(err_outlet), axis=1)  # (1440,)

# --- Task 3 plots: error evolution over time ---
fig, axes = plt.subplots(1, 2, figsize=(12, 4), sharex=True)

axes[0].plot(time_h, mae_per_step_inlet)
axes[0].set_ylabel('MAE [°C]')
axes[0].set_xlabel('Time [h]')
axes[0].set_title('Inlet temperature error over time')
axes[0].margins(x=0)

axes[1].plot(time_h, mae_per_step_outlet)
axes[1].set_ylabel('MAE [°C]')
axes[1].set_xlabel('Time [h]')
axes[1].set_title('Outlet temperature error over time')
axes[1].margins(x=0)
fig.suptitle('NovaCool — Task 3: Model vs Reference', fontsize=14)
fig.tight_layout()
plt.savefig(r'C:\drive\CV_US\Hammerhead\case study\final\plots\task3.pdf', bbox_inches='tight')
plt.show()

# --- Diagnostic comparison plots: model vs sensor averages ---

# Average mass flow rate (across all racks at each timestep)
plt.figure()
plt.plot(time_h, ref_m_flow.mean(axis=1), label='Reference')
plt.plot(time_h, sim_m_flow, label = 'Simulation')
plt.margins(x=0)
plt.title('Average mass flow rate')
plt.savefig(r'C:\drive\CV_US\Hammerhead\case-study\final\plots\avgmf.pdf', bbox_inches='tight')
plt.show()

# Average inlet (supply) temperature
plt.figure()
plt.plot(time_h, ref_inlet.mean(axis=1))
plt.plot(time_h, sim_inlet.mean(axis=1))
plt.margins(x=0)
plt.title('Average Inlet temperatures')
plt.savefig(r'C:\drive\CV_US\Hammerhead\case-study\final\plots\avgin.pdf', bbox_inches='tight')
plt.show()

# Average outlet (return) temperature
plt.figure()
plt.plot(time_h, ref_outlet.mean(axis=1))
plt.plot(time_h, sim_outlet.mean(axis=1))
plt.margins(x=0)
plt.title('Average outlet temperatures')
plt.savefig(r'C:\drive\CV_US\Hammerhead\case-study\final\plots\avgout.pdf', bbox_inches='tight')
plt.show()


