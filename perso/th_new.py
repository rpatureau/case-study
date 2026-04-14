#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Apr 13 21:47:50 2026

@author: remi
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

# %% Load workload trace and pivot to (n_steps, n_racks) array

workload = pd.read_csv(
    r'C:\drive\CV_US\Hammerhead\case study\instructions\workload_trace.csv',
    parse_dates=['timestamp'])
n_racks = workload['rack_id'].nunique()
n_steps = workload['timestamp'].nunique()

# pivot: rows = timesteps (1440), columns = rack_id (200), values = power_kw
P_IT = workload.pivot(index='timestamp', columns='rack_id', values='power_kw').values  # (1440, 200)

# %% Physical constants and facility parameters

Cp_air = 1005.0       # J/(kg·K)

#%% One rack

T_rack_supply = 8.5   # °C
dT_air = 20          # °C
m_flow = P_IT * 1000 / Cp_air / dT_air  # (1440, 200) kg/s per rack

# Sum per CRAH: racks 0-49 → CRAH 0, 50-99 → CRAH 1, etc.
m_flow_crah = m_flow.reshape(n_steps, 4, 50).sum(axis=2)  # (1440, 4) kg/s per CRAH
P_IT_crah = P_IT.reshape(n_steps, 4, 50).sum(axis=2)      # (1440, 4) kW per CRAH
T_rack_return = T_rack_supply + P_IT_crah * 1000 / m_flow_crah / Cp_air

#%% Water loop

Cp_water = 4186.0      # J/(kg·K)
T_water_supply = 7.0     # °C 
T_water_return = 35.0    # °C
eta_water = 0.7

Q = eta_water * m_flow_crah * Cp_air * (T_rack_return - T_water_supply)
m_flow_water = Q / Cp_water / (T_water_return - T_water_supply)

# Totals
Q_water_total = Q.sum(axis=1)          # (1440,) kW — total chiller duty
m_flow_water_total = m_flow_water.sum(axis=1)  # (1440,) kg/s


sns.set_style("whitegrid")

fig, axes = plt.subplots(1, 2, figsize=(11, 4))
axes[0].plot(T_rack_return.mean(axis = 1), label = 'Average cold-aisle temperature')
axes[0].plot([T_rack_supply] * 1440, label = 'Average hot-aisle temperature')
axes[0].set_title('Temperatures (in °C)')
axes[0].margins(x=0)
axes[0].legend(loc = 'lower center', bbox_to_anchor=[0.5, -0.2], ncol = 2)

axes[1].set_title('Total cooling power consumed (in MW)')
axes[1].plot(P_IT_crah.sum(axis = 1) / 1000)
axes[1].margins(x=0)
plt.tight_layout()
plt.savefig(r'C:\drive\CV_US\Hammerhead\case study\final\plots\task1.pdf', bbox_inches='tight')
plt.show()

#%% Task 2 — Power & System Coupling

P_IT_total = P_IT.sum(axis=1)  # (1440,) kW total IT load

# --- UPS efficiency (quadratic, 2N redundant) ---
IT_capacity_kw = 10_000.0  # 10 MW
x_load = (P_IT_total / 2) / (IT_capacity_kw / 2)  # per-UPS load fraction (2N)
eta_ups_peak = 0.965
x_peak = 0.65
k_ups = 0.20
eta_ups = np.clip(eta_ups_peak - k_ups * (x_load - x_peak) ** 2, 0.80, eta_ups_peak)
P_UPS_input = P_IT_total / eta_ups  # kW

# --- CRAH fans (affinity law: P ~ speed^3) ---
fan_speed = 0.85
P_fan_nominal = 55.0  # kW per CRAH at 100% speed
P_fans = 4 * P_fan_nominal * fan_speed ** 3  # kW (constant since fan_speed is fixed)

# --- Chilled-water pumps (affinity law: P ~ flow^3) ---
P_pump_nominal = 18.0  # kW per CRAH at full load
m_flow_water_design = IT_capacity_kw * 1000 / (Cp_water * (T_water_return - T_water_supply))  # kg/s at full capacity
flow_frac = np.clip(m_flow_water_total / m_flow_water_design, 0.0, 1.0)
P_pumps = 4 * P_pump_nominal * flow_frac ** 3  # kW

# --- Chiller (Q / COP) ---
COP = 4.8
P_chiller = Q_water_total / COP  # kW

# --- Other (lights, network, security ~ 1% capacity) ---
P_other = 0.01 * IT_capacity_kw  # kW

# --- PUE ---
P_total = P_UPS_input + P_fans + P_pumps + P_chiller + P_other
PUE = P_total / P_IT_total


time_h = np.arange(n_steps) / 60.0

fig, axes = plt.subplots(2, 2, figsize=(12, 8), sharex=True)

axes[0, 0].plot(time_h, P_IT_total / 1000)
axes[0, 0].set_ylabel('Power [MW]')
axes[0, 0].set_title('IT Load')

axes[0, 1].plot(time_h, eta_ups)
axes[0, 1].set_ylabel('Efficiency')
axes[0, 1].set_title('UPS Efficiency')

axes[1, 0].plot(time_h, P_chiller, label='Chiller')
axes[1, 0].plot(time_h, np.full(n_steps, P_fans), label='Fans')
axes[1, 0].plot(time_h, P_pumps, label='Pumps')
axes[1, 0].set_ylabel('Power [kW]')
axes[1, 0].set_xlabel('Time [h]')
axes[1, 0].set_title('Cooling power breakdown')
axes[1, 0].legend()

axes[1, 1].plot(time_h, PUE)
axes[1, 1].set_ylabel('PUE')
axes[1, 1].set_xlabel('Time [h]')
axes[1, 1].set_title('Power Usage Effectiveness')

fig.tight_layout()
plt.savefig(r'C:\drive\CV_US\Hammerhead\case study\final\plots\task2.pdf', bbox_inches='tight')
plt.show()

#%% Task 3

sensor = pd.read_csv(r'C:\drive\CV_US\Hammerhead\case study\instructions\sensor_reference.csv',
                     parse_dates=['timestamp'])

# Pivot reference data to (1440, 200) arrays
ref_inlet = sensor.pivot(index='timestamp', columns='rack_id', values='inlet_temp_c').values
ref_outlet = sensor.pivot(index='timestamp', columns='rack_id', values='outlet_temp_c').values

# Model predictions — expand per-zone supply to per-rack
zone_of_rack = np.arange(n_racks) // 50
sim_inlet = np.full_like(ref_outlet, T_rack_supply)
sim_outlet = T_rack_return[:, zone_of_rack]  # (1440, 200) — constant 40 °C

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
ref_power = sensor.pivot(index='timestamp', columns='rack_id', values='pdu_power_kw').values
ref_m_flow = ref_power * 1000 / (Cp_air * np.maximum(ref_outlet - ref_inlet, 0.1))  # (1440, 200)
sim_m_flow = np.maximum(m_flow_crah.sum(axis = 1) / 200, 1)  # (1440, 200)

# err_m_flow = sim_m_flow - ref_m_flow
# RMSE_m_flow = np.sqrt(np.mean(err_m_flow ** 2))
# MAE_m_flow = np.mean(np.abs(err_m_flow))
# MaxAE_m_flow = np.abs(err_m_flow).max()

print(f"Inlet  — RMSE: {RMSE_inlet:.2f} °C  MAE: {MAE_inlet:.2f} °C  MaxAE: {MaxAE_inlet:.2f} °C")
print(f"Outlet — RMSE: {RMSE_outlet:.2f} °C  MAE: {MAE_outlet:.2f} °C  MaxAE: {MaxAE_outlet:.2f} °C")
# print(f"m_flow — RMSE: {RMSE_m_flow:.4f} kg/s  MAE: {MAE_m_flow:.4f} kg/s  MaxAE: {MaxAE_m_flow:.4f} kg/s")

# --- Time intervals with worst divergence ---
mae_per_step_inlet = np.mean(np.abs(err_inlet), axis=1)   # (1440,)
mae_per_step_outlet = np.mean(np.abs(err_outlet), axis=1)  # (1440,)

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

plt.figure()
plt.plot(time_h, ref_m_flow.mean(axis=1), label='Reference')
plt.plot(time_h, sim_m_flow, label = 'Simulation')
plt.margins(x=0)
plt.title('Average mass flow rate (kg/s)')
plt.legend(loc = 'lower center', bbox_to_anchor=[0.5, -0.2], ncol = 2)
plt.savefig(r'C:\drive\CV_US\Hammerhead\case-study\final\plots\avgmf.pdf', bbox_inches='tight')
plt.show()


plt.figure()
plt.plot(time_h, ref_inlet.mean(axis=1), label='Reference')
plt.plot(time_h, sim_inlet.mean(axis=1), label = 'Simulation')
plt.margins(x=0)
plt.title('Average Inlet temperatures (°C)')
plt.legend(loc = 'lower center', bbox_to_anchor=[0.5, -0.2], ncol = 2)
plt.savefig(r'C:\drive\CV_US\Hammerhead\case-study\final\plots\avgin.pdf', bbox_inches='tight')
plt.show()

plt.figure()
plt.plot(time_h, ref_outlet.mean(axis=1), label='Reference')
plt.plot(time_h, sim_outlet.mean(axis=1), label = 'Simulation')
plt.margins(x=0)
plt.title('Average outlet temperatures (°C)')
plt.legend(loc = 'lower center', bbox_to_anchor=[0.5, -0.2], ncol = 2)
plt.savefig(r'C:\drive\CV_US\Hammerhead\case-study\final\plots\avgout.pdf', bbox_inches='tight')
plt.show()


