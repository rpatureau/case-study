#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gym-style RL environment for NovaCool — simplified standalone version.

Observation: [T_cold_aisle, T_hot_aisle_mean, T_hot_aisle_peak, IT_load_MW, sin(tod), cos(tod)]
Action:      [CRAH_supply_setpoint, fan_speed]
Reward:      IT throughput - thermal violation penalty - energy cost

@author: remi
"""

import numpy as np


class DataCenterEnv:
    """Minimal Gym-compatible environment for NovaCool."""

    def __init__(
        self,
        P_IT: np.ndarray,          # (n_steps, n_racks) workload in kW
        Cp_air: float = 1005.0,
        T_water_supply: float = 7.0,
        eta_water: float = 0.7,
        dT_air_design: float = 20.0,
        T_rack_supply_init: float = 8.5,
        n_crahs: int = 4,
        dt: float = 60.0,
        T_safety_limit: float = 40.0,
    ):
        self.P_IT = P_IT
        self.n_steps, self.n_racks = P_IT.shape
        self.Cp_air = Cp_air
        self.T_water_supply = T_water_supply
        self.eta_water = eta_water
        self.dT_air_design = dT_air_design
        self.T_rack_supply_init = T_rack_supply_init
        self.n_crahs = n_crahs
        self.racks_per_zone = self.n_racks // n_crahs
        self.dt = dt
        self.T_safety_limit = T_safety_limit

        # Rack thermal mass
        self.Cap_rack = 700.0 * 500.0  # m_rack * Cp_rack = 350 000 J/K

        self.reset()

    def reset(self) -> np.ndarray:
        """Reset environment; return initial observation."""
        self.t = 0
        self.T_rack = np.full(self.n_racks, self.T_rack_supply_init + 12.0)
        self.T_supply = self.T_rack_supply_init
        return self._observe()

    def step(self, action: np.ndarray) -> tuple:
        """Advance one time step.

        action: [supply_setpoint_c, fan_speed_frac]
        returns: (observation, reward, done, info)
        """
        supply_setpoint = np.clip(action[0], self.T_water_supply + 1.0, 24.0)
        fan_speed = np.clip(action[1], 0.1, 1.0)

        P_w = self.P_IT[self.t, :] * 1000.0  # kW -> W

        # Airflow per rack (sized from design dT, scaled by fan speed)
        m_dot_base = self.P_IT[self.t, :] * 1000 / (self.Cp_air * self.dT_air_design)
        m_dot_rack = np.maximum(m_dot_base * fan_speed, 0.01)

        # Rack ODE: Cap * dT/dt = P_IT - m_dot * Cp * (T_rack - T_supply)
        cooling_w = m_dot_rack * self.Cp_air * (self.T_rack - self.T_supply)
        dT_dt = (P_w - cooling_w) / self.Cap_rack
        self.T_rack = self.T_rack + self.dt * dT_dt

        # CRAH: T_supply = T_return - eta * (T_return - T_water)
        T_return = self.T_rack.reshape(self.n_crahs, self.racks_per_zone).mean(axis=1).mean()
        self.T_supply = T_return - self.eta_water * (T_return - self.T_water_supply)
        self.T_supply = max(self.T_supply, self.T_water_supply + 1.0)

        # Metrics
        IT_load_kw = self.P_IT[self.t, :].sum()
        T_peak = self.T_rack.max()
        T_hot_mean = self.T_rack.mean()
        violation = max(0.0, T_peak - self.T_safety_limit)

        # Reward: throughput - violation penalty - energy proxy
        cooling_kw = m_dot_rack.sum() * self.Cp_air * max(T_return - self.T_supply, 0) / 1000
        reward = (
            IT_load_kw / 1000.0                  # MW served (maximize)
            - 5.0 * violation ** 2               # hard safety penalty
            - 0.15 * (IT_load_kw + cooling_kw) / 1000.0  # energy cost
        )

        self.t += 1
        done = self.t >= self.n_steps or T_peak > 45.0

        info = {
            'IT_load_MW': IT_load_kw / 1000.0,
            'T_peak': T_peak,
            'T_hot_mean': T_hot_mean,
            'T_supply': self.T_supply,
            'cooling_kW': cooling_kw,
            'violation': violation > 0,
        }

        return self._observe(), reward, done, info

    def _observe(self) -> np.ndarray:
        """Build flat observation vector."""
        theta = 2 * np.pi * (self.t / self.n_steps)
        return np.array([
            self.T_supply,
            self.T_rack.mean(),
            self.T_rack.max(),
            self.P_IT[min(self.t, self.n_steps - 1), :].sum() / 1000.0,
            np.sin(theta),
            np.cos(theta),
        ], dtype=np.float32)
