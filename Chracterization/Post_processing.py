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
        
        '''Extracts current at a specific voltage (or closest within tolerance) for each LED brightness and cycle.
        If average_cycles is True, returns average current per LED brightness across all cycles.
        
        Parameters
        ----------
        target_voltage : float
        voltage_tolerance : float, optional Tolerance for voltage matching.
        average_cycles : bool, optional Whether to average current across cycles.

        Returns
        -------
        pd.DataFrame
            Extracted current data.

        '''
        # (same as before, but without column checks)
        df = self.data.copy()
        if voltage_tolerance is not None:
            mask = (df['v'] - target_voltage).abs() <= voltage_tolerance
            df = df.loc[mask]
            if df.empty:
                raise ValueError(f"No data within ±{voltage_tolerance} V of {target_voltage} V")

        df['_diff'] = (df['v'] - target_voltage).abs()
        idx = df.groupby(['led_brightness', 'cycle'])['_diff'].idxmin()
        result = df.loc[idx, ['led_brightness', 'cycle', 'v', 'i']].copy()
        df.drop(columns='_diff', inplace=True)

        result.rename(columns={'v': 'actual_voltage', 'i': 'current'}, inplace=True)
        result['target_voltage'] = target_voltage

        if average_cycles:
            return result.groupby('led_brightness')['current'].mean().reset_index()
        return result.reset_index(drop=True)

    def extract_voltage_at_min_current(self, voltage_range: Optional[Tuple[float, float]] = None,
                                        average_cycles: bool = False) -> pd.DataFrame:
        
        """Extracts voltage at minimum current for each LED brightness and cycle, optionally within a voltage range.
        If average_cycles is True, returns average voltage and current per LED brightness across all cycles.
        Parameters
        ----------
        voltage_range : tuple of (float, float), optional Voltage range to consider for min current
        average_cycles : bool, optional Whether to average results across cycles
        Returns
        -------
        pd.DataFrame
            Extracted voltage at min current data.
        """
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
                                   average_cycles=False, ax=None, log_scale=False, **kwargs):
        """Plots current at a specific voltage vs LED brightness.
        If voltage_tolerance is set, it finds the closest voltage to target_voltage within that tolerance.
        
        """
        df = self.extract_current_at_voltage(target_voltage, voltage_tolerance, average_cycles)
        if ax is None:
            fig, ax = plt.subplots()
        ax.plot(df['led_brightness'], df['current'], 'o-', **kwargs)
        ax.set_xlabel('LED brightness (A)')
        ax.set_ylabel(f'Current at {target_voltage} V (A)')
        if log_scale:
            ax.set_yscale('log')
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

class MemristorProcessor:
    def __init__(self, data: pd.DataFrame):
        required = {'v', 'i', 'cycle', 'phase', 'set_compliance'}
        if not required.issubset(data.columns):
            missing = required - set(data.columns)
            raise ValueError(f"Memristor data missing columns: {missing}")
        self.data = data.copy()

    def extract_lrs(self, read_voltage: float= -0.2, average_cycles: bool = False) -> pd.DataFrame:
        """Extracts LRS data from the DataFrame, calculating resistance at a specified read voltage.
        If average_cycles is True, returns average current and resistance per set_compliance across all cycles
        Parameters
        ----------
        read_voltage : float
            Voltage at which to calculate resistance (V)
        average_cycles : bool, optional
            Whether to average results across cycles

        Returns
        -------
        pd.DataFrame
            Extracted LRS data.

        """
        df = self.data[self.data['phase'] == 'READ_SET'].copy()
        if df.empty:
            raise ValueError("No READ_SET phase data found.")

        df['current'] = df['i']
        eps = 1e-12
        df['resistance'] = abs(read_voltage) / df['current'].abs().clip(lower=eps)
        result = df[['set_compliance', 'cycle', 'current', 'resistance']].reset_index(drop=True)

        if average_cycles:
            return result.groupby('set_compliance')[['current', 'resistance']].mean().reset_index()
        return result

    def extract_hrs(self, read_voltage: float =-0.2, average_cycles: bool = False) -> pd.DataFrame:
        """Extracts HRS data from the DataFrame, calculating resistance at a specified read voltage.
        If average_cycles is True, returns average current and resistance per set_compliance across all cycles
        Parameters
        ----------
        read_voltage : float
            Voltage at which to calculate resistance (V)
        average_cycles : bool, optional
            Whether to average results across cycles
        Returns
        -------
        pd.DataFrame
            Extracted HRS data.    
            
            
        """    
        df = self.data[self.data['phase'] == 'READ_RESET'].copy()
        if df.empty:
            raise ValueError("No READ_RESET phase data found.")

        df['current'] = df['i']
        eps = 1e-12
        df['resistance'] = abs(read_voltage) / df['current'].abs().clip(lower=eps)
        result = df[['set_compliance', 'cycle', 'current', 'resistance']].reset_index(drop=True)

        if average_cycles:
            return result.groupby('set_compliance')[['current', 'resistance']].mean().reset_index()
        return result

    def plot_lrs_vs_compliance(self, read_voltage: float = -0.2, plot_type: str = 'box', ax=None, **kwargs):
        """
        Plots LRS vs Compliance. 
        plot_type options: 'scatter', 'errorbar', 'box'
        
        parameters
        ----------
        read_voltage : float
            Voltage at which to calculate resistance (V)
        plot_type : str
            Type of plot to create: 'scatter', 'errorbar', or 'box'
        ax : matplotlib.axes.Axes, optional
            Axes to plot on. If None, a new figure and axes are created.
        **kwargs
            Additional keyword arguments passed to the plotting function (e.g., color, alpha).
        Returns
        -------
        matplotlib.axes.Axes
            The axes object containing the plot.
        """
        # Always extract raw data for statistical plotting
        df = self.extract_lrs(read_voltage, average_cycles=False)
        
        if ax is None:
            fig, ax = plt.subplots(figsize=(6, 4))
            
        x_mA = df['set_compliance'] * 1000  # Convert to mA
        y_res = df['resistance']

        if plot_type == 'scatter':
            # Alpha adds slight transparency so overlapping points create a "density" effect
            ax.scatter(x_mA, y_res, marker='o', alpha=0.6, **kwargs)
            
        elif plot_type == 'errorbar':
            # Calculate mean and standard deviation
            stats = df.groupby('set_compliance')['resistance'].agg(['mean', 'std']).reset_index()
            ax.errorbar(stats['set_compliance'] * 1000, stats['mean'], yerr=stats['std'], 
                        fmt='o', capsize=5, capthick=1.5, elinewidth=1.5, **kwargs)
            
        elif plot_type == 'box':
            # Create a list of arrays for each compliance group
            groups = df.groupby('set_compliance')
            data_to_plot = [group['resistance'].values for _, group in groups]
            labels_mA = [f"{comp * 1000:.2f}" for comp, _ in groups]
            
            # Matplotlib boxplot
            ax.boxplot(data_to_plot, tick_labels=labels_mA, patch_artist=True, 
                       boxprops=dict(facecolor='lightblue', color='blue', alpha=0.7),
                       medianprops=dict(color='red', linewidth=1.5), **kwargs)

        ax.set_xlabel('Set Compliance (mA)')
        ax.set_ylabel('LRS Resistance (Ω)')
        ax.grid(True, alpha=0.3)
        return ax


    def plot_hrs_vs_compliance(self, read_voltage: float = -0.2, plot_type: str = 'errorbar', ax=None, **kwargs):
        """
        Plots HRS vs Compliance. 
        plot_type options: 'scatter', 'errorbar', 'box'
        
        parameters
        ----------
        read_voltage : float
            Voltage at which to calculate resistance (V)
        plot_type : str
            Type of plot to create: 'scatter', 'errorbar', or 'box'
        ax : matplotlib.axes.Axes, optional
            Axes to plot on. If None, a new figure and axes are created.
        **kwargs
            Additional keyword arguments passed to the plotting function (e.g., color, alpha).
        Returns
        -------
        matplotlib.axes.Axes
            The axes object containing the plot.
        """
        df = self.extract_hrs(read_voltage, average_cycles=False)
        
        if ax is None:
            fig, ax = plt.subplots(figsize=(6, 4))
            
        x_mA = df['set_compliance'] * 1000
        y_res_Mohm = df['resistance']

        if plot_type == 'scatter':
            ax.scatter(x_mA, y_res_Mohm, marker='s', alpha=0.6, color='tab:orange', **kwargs)
            
        elif plot_type == 'errorbar':
            stats = df.groupby('set_compliance')['resistance'].agg(['mean', 'std']).reset_index()
            ax.errorbar(stats['set_compliance'] * 1000, stats['mean'] , yerr=stats['std'], 
                        fmt='s', color='tab:orange', capsize=5, capthick=1.5, elinewidth=1.5, **kwargs)
            
        elif plot_type == 'box':
            groups = df.groupby('set_compliance')
            data_to_plot = [(group['resistance'].values ) for _, group in groups]
            labels_mA = [f"{comp * 1000:.2f}" for comp, _ in groups]
            
            ax.boxplot(data_to_plot, tick_labels=labels_mA, patch_artist=True,
                       boxprops=dict(facecolor='moccasin', color='darkorange', alpha=0.7),
                       medianprops=dict(color='red', linewidth=1.5), **kwargs)

        ax.set_xlabel('Set Compliance (mA)')
        ax.set_ylabel('HRS Resistance (Ω)')
        ax.grid(True, alpha=0.3)
        return ax

    def plot_resistance_vs_cycle(self, target_compliance: Optional[float]= None, read_voltage: float= -0.2,
                                  ax=None, **kwargs):
        
        """Plots resistance vs cycle for a specific set compliance. If target_compliance is None, uses the first available compliance.
            Parameters
            ----------
            target_compliance : float, optional
                Target set compliance value. The nearest available compliance is used. If None, uses the first available compliance.
            read_voltage : float
                Voltage at which to calculate resistance (V)
            ax : matplotlib.axes.Axes, optional
                Axes to plot on. If None, a new figure and axes are created.
            **kwargs
                Additional keyword arguments passed to the plotting function (e.g., color, alpha).
            Returns
            -------
            matplotlib.axes.Axes
                The axes object containing the plot.
                
        """
        # Find nearest compliance
        available = self.data['set_compliance'].unique()
        available.sort()
        
        # Default to the first compliance if none provided
        if target_compliance is None:
            nearest = available[0]
            print(f"No compliance specified. Using first available: {nearest}")
        else:
            idx = np.abs(available - target_compliance).argmin()
            nearest = available[idx]
            if nearest != target_compliance:
                print(f"Compliance {target_compliance} not found. Using nearest: {nearest}")
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


    def plot_iv_curve(self, compliance: float, ax=None,
                      set_color='tab:blue', reset_color='tab:orange',
                      alpha=0.7, linewidth=1.5, **kwargs):
        """
        Plot the I‑V curve (SET and RESET) for all cycles at a given compliance.
        Absolute current is shown on a logarithmic y‑axis.
    
        Parameters
        ----------
        compliance : float
            Target set compliance value. The nearest available compliance is used.
        ax : matplotlib.axes.Axes, optional
            Axes to plot on. If None, a new figure and axes are created.
        set_color : str, optional
            Color for SET traces.
        reset_color : str, optional
            Color for RESET traces.
        alpha : float, optional
            Transparency of the traces (0 = transparent, 1 = opaque).
        linewidth : float, optional
            Width of the plotted lines.
        **kwargs
            Additional keyword arguments passed to both `plot` calls
            (e.g., linestyle, marker).
    
        Returns
        -------
        matplotlib.axes.Axes
            The axes object containing the plot.
        """
        # Find the nearest available compliance
        available = self.data['set_compliance'].dropna().unique()
        if len(available) == 0:
            raise ValueError("No compliance data available.")
        idx = np.abs(available - compliance).argmin()
        nearest = available[idx]
        if nearest != compliance:
            print(f"Compliance {compliance} not found. Using nearest: {nearest}")
    
        # Filter data for this compliance, keep only SET and RESET phases
        mask = (self.data['set_compliance'] == nearest) & \
               (self.data['phase'].isin(['SET', 'RESET']))
        df = self.data.loc[mask].copy()
        if df.empty:
            raise ValueError(f"No SET/RESET data for compliance {nearest}")
    
        # Compute absolute current for log scale
        df['abs_i'] = df['i'].abs()
    
        # Create axes if needed
        if ax is None:
            fig, ax = plt.subplots(figsize=(7, 5))
    
        # Plot each cycle separately
        cycles = sorted(df['cycle'].unique())
        for i, cycle in enumerate(cycles):
            df_cycle = df[df['cycle'] == cycle]
            set_data = df_cycle[df_cycle['phase'] == 'SET']
            reset_data = df_cycle[df_cycle['phase'] == 'RESET']
    
            # Only add labels for the first cycle to keep legend clean
            set_label = 'SET' if i == 0 else None
            reset_label = 'RESET' if i == 0 else None
    
            # Plot SET
            ax.plot(set_data['v'], set_data['abs_i'],
                    color=set_color, label=set_label,
                    linewidth=linewidth, alpha=alpha, **kwargs)
            # Plot RESET
            ax.plot(reset_data['v'], reset_data['abs_i'],
                    color=reset_color, label=reset_label,
                    linewidth=linewidth, alpha=alpha, **kwargs)
    
        # Axes styling
        ax.set_yscale('log')
        ax.set_xlabel('Voltage (V)')
        ax.set_ylabel('|Current| (A)')
        ax.set_title(f'Memristor I‑V Curve (SET Compliance = {nearest} A)')
        ax.grid(True, which='both', linestyle='--', alpha=0.3)
        ax.legend()
    
        return ax
    
    
    def plot_all_compliances(self, compliances=None, **kwargs):
        """
        Plot I-V curves for all (or selected) compliances, one figure per compliance.
        
        Parameters
        ----------
        compliances : list of float, optional
            List of compliance values to plot. If None, plot all unique compliances.
        **kwargs
            Additional arguments passed to self.plot_iv_curve()
            (e.g., set_color, reset_color, alpha, linewidth).
        """
        if compliances is None:
            # Use self.data instead of processor.data
            compliances = sorted(self.data['set_compliance'].dropna().unique())
    
        for comp in compliances:
            # Use self.plot_iv_curve instead of processor.plot_iv_curve
            self.plot_iv_curve(compliance=comp, **kwargs)
            plt.show()  # show each figure