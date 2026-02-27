"""
Post‑processing for photodiode characterisation data.
Expects DataFrame columns: v, i, cycle, led_brightness
(optional: t)
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from typing import Optional, Tuple

class PhotodiodeProcessor:
    def __init__(self, data: pd.DataFrame):
        required = {'v', 'i', 'cycle', 'led_brightness'}
        if not required.issubset(data.columns):
            missing = required - set(data.columns)
            raise ValueError(f"Photodiode data missing columns: {missing}")
        self.data = data.copy()

    def extract_current_at_voltage(self, target_voltage: float,
                                    voltage_tolerance: Optional[float] = None,
                                    average_cycles: bool = False) -> pd.DataFrame:
        # (same as before, but without column checks)
        df = self.data.copy()
        if voltage_tolerance is not None:
            mask = (df['v'] - target_voltage).abs() <= voltage_tolerance
            df = df.loc[mask]
            if df.empty:
                raise ValueError(f"No data within ±{voltage_tolerance} V of {target_voltage} V")

        idx = df.groupby(['led_brightness', 'cycle'])['v'].transform(
            lambda x: (x - target_voltage).abs()
        ).idxmin()
        result = df.loc[idx, ['led_brightness', 'cycle', 'v', 'i']].copy()
        result.rename(columns={'v': 'actual_voltage', 'i': 'current'}, inplace=True)
        result['target_voltage'] = target_voltage

        if average_cycles:
            return result.groupby('led_brightness')['current'].mean().reset_index()
        return result.reset_index(drop=True)

    def extract_voltage_at_min_current(self, voltage_range: Optional[Tuple[float, float]] = None,
                                        average_cycles: bool = False) -> pd.DataFrame:
        df = self.data.copy()
        if voltage_range:
            vmin, vmax = voltage_range
            df = df[(df['v'] >= vmin) & (df['v'] <= vmax)]
            if df.empty:
                raise ValueError(f"No data in range {voltage_range}")

        idx = df.groupby(['led_brightness', 'cycle'])['i'].idxmin()
        result = df.loc[idx, ['led_brightness', 'cycle', 'v', 'i']].copy()
        result.rename(columns={'v': 'voltage_at_min_current', 'i': 'min_current'}, inplace=True)

        if average_cycles:
            avg = result.groupby('led_brightness')['voltage_at_min_current'].mean().reset_index()
            avg_min = result.groupby('led_brightness')['min_current'].mean().reset_index()
            return avg.merge(avg_min, on='led_brightness')
        return result.reset_index(drop=True)

    # Plotting methods (same as before)
    def plot_current_vs_brightness(self, target_voltage, voltage_tolerance=None,
                                   average_cycles=True, ax=None, **kwargs):
        df = self.extract_current_at_voltage(target_voltage, voltage_tolerance, average_cycles)
        if ax is None:
            fig, ax = plt.subplots()
        ax.plot(df['led_brightness'], df['current'], 'o-', **kwargs)
        ax.set_xlabel('LED brightness (A)')
        ax.set_ylabel(f'Current at {target_voltage} V (A)')
        ax.grid(True, alpha=0.3)
        return ax

    def plot_voltage_vs_brightness(self, voltage_range=None, average_cycles=True,
                                    ax=None, **kwargs):
        df = self.extract_voltage_at_min_current(voltage_range, average_cycles)
        if ax is None:
            fig, ax = plt.subplots()
        ax.plot(df['led_brightness'], df['voltage_at_min_current'], 's-', **kwargs)
        ax.set_xlabel('LED brightness (A)')
        ax.set_ylabel('Voltage at min current (V)')
        ax.grid(True, alpha=0.3)
        return ax
    
    
    
    
"""
Post‑processing for memristor bipolar compliance sweep data.
Expects DataFrame columns: v, i, cycle, phase, set_compliance
(optional: t)
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from typing import Optional

class MemristorProcessor:
    def __init__(self, data: pd.DataFrame):
        required = {'v', 'i', 'cycle', 'phase', 'set_compliance'}
        if not required.issubset(data.columns):
            missing = required - set(data.columns)
            raise ValueError(f"Memristor data missing columns: {missing}")
        self.data = data.copy()

    def extract_lrs(self, read_voltage: float, average_cycles: bool = False) -> pd.DataFrame:
        df = self.data[self.data['phase'] == 'READ_SET'].copy()
        if df.empty:
            raise ValueError("No READ_SET phase data found.")

        df['current'] = df['i']
        df['resistance'] = abs(read_voltage) / df['current'].abs()
        result = df[['set_compliance', 'cycle', 'current', 'resistance']].reset_index(drop=True)

        if average_cycles:
            return result.groupby('set_compliance')[['current', 'resistance']].mean().reset_index()
        return result

    def extract_hrs(self, read_voltage: float, average_cycles: bool = False) -> pd.DataFrame:
        df = self.data[self.data['phase'] == 'READ_RESET'].copy()
        if df.empty:
            raise ValueError("No READ_RESET phase data found.")

        df['current'] = df['i']
        df['resistance'] = abs(read_voltage) / df['current'].abs()
        result = df[['set_compliance', 'cycle', 'current', 'resistance']].reset_index(drop=True)

        if average_cycles:
            return result.groupby('set_compliance')[['current', 'resistance']].mean().reset_index()
        return result

    def plot_lrs_vs_compliance(self, read_voltage: float, average_cycles: bool = True,
                               ax=None, **kwargs):
        df = self.extract_lrs(read_voltage, average_cycles)
        if ax is None:
            fig, ax = plt.subplots()
        ax.plot(df['set_compliance'], df['resistance'], 'o-', **kwargs)
        ax.set_xlabel('Set Compliance (A)')
        ax.set_ylabel('LRS Resistance (Ω)')
        ax.grid(True, alpha=0.3)
        return ax

    def plot_hrs_vs_compliance(self, read_voltage: float, average_cycles: bool = True,
                               ax=None, **kwargs):
        df = self.extract_hrs(read_voltage, average_cycles)
        if ax is None:
            fig, ax = plt.subplots()
        ax.plot(df['set_compliance'], df['resistance'], 's-', **kwargs)
        ax.set_xlabel('Set Compliance (A)')
        ax.set_ylabel('HRS Resistance (Ω)')
        ax.grid(True, alpha=0.3)
        return ax

    def plot_resistance_vs_cycle(self, target_compliance: float, read_voltage: float,
                                  ax=None, **kwargs):
        # Find nearest compliance
        available = self.data['set_compliance'].unique()
        idx = np.abs(available - target_compliance).argmin()
        nearest = available[idx]
        if nearest != target_compliance:
            print(f"Using nearest compliance: {nearest}")

        lrs = self.extract_lrs(read_voltage, average_cycles=False)
        hrs = self.extract_hrs(read_voltage, average_cycles=False)

        lrs = lrs[lrs['set_compliance'] == nearest].sort_values('cycle')
        hrs = hrs[hrs['set_compliance'] == nearest].sort_values('cycle')

        if ax is None:
            fig, ax = plt.subplots()
        ax.plot(lrs['cycle'], lrs['resistance'], 'o-', label='LRS', **kwargs)
        ax.plot(hrs['cycle'], hrs['resistance'], 's-', label='HRS', **kwargs)
        ax.set_xlabel('Cycle')
        ax.set_ylabel('Resistance (Ω)')
        ax.set_title(f'Set Compliance = {nearest} A')
        ax.legend()
        ax.grid(True, alpha=0.3)
        return ax