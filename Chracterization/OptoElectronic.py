import time
from typing import Optional, Union, Sequence, Dict, Any 
import warnings
from datetime import datetime
from matplotlib.pyplot import plot
import pandas as pd
import numpy as np
import typing

from measurement_control.instruments.keithley_2600a import SMU, Range, Mode, Quantity, Autozero, Keithley2600A, Keithley2600AModel
from measurement_control.instruments.thorlabs_dc2200 import DC2200
from measurement_control.datasets import Dataset
from measurement_control import errors, config
from measurement_control.files import File,TextFile
from measurement_control import __version__
from measurement_control.utils import create_sweep_list
from measurement_control.plots import plot

CUSTOM_SCRIPT_VERSION = __version__
CUSTOM_SCRIPT = "all_functions.lua"
class Characterization:
    def __init__(self, keithley: Keithley2600A, dc_driver: Optional[DC2200] = None, force_code_reload: bool = False):
        
        """
        Initialize the Characterization class.

        :param keithley: A connected Keithley2600A instance.
        :param dc_driver: Optional DC2200 instance for LED control. If not provided,
                          methods that require the LED will raise an error.
        :param force_code_reload: Whether to force reload of the Lua script.
        """
        self.k = keithley
        self.dc = dc_driver
        if force_code_reload or self.k.query('GetMeasurementControlScriptID == nil') == 'true' or self.k.query('GetMeasurementControlScriptID()') != CUSTOM_SCRIPT_VERSION:
            with open(CUSTOM_SCRIPT, "r") as f:
                custom_script_code = f.read()
            self.k.send("""loadandrunscript MeasurementControl
                function GetMeasurementControlScriptID()
                    return \"""" + CUSTOM_SCRIPT_VERSION + """\"
                end
                """ + custom_script_code + """
                endscript
                """)
            self.k.check_error_queue(force=True)
    # ----------------------------------------------------------------------
    # Utilities
    # ----------------------------------------------------------------------
    def _check_dc(self):
        """Raise an error if no DC2200 is connected."""
        if self.dc is None:
            raise RuntimeError("This measurement requires a DC2200 driver, but none was provided.")            
         
    def get_buffer_data(self, buf_num, count, smu: SMU):
        """
        Utility function to retrieve data from the Keithley's buffer after a measurement.
        :param buf_num: Buffer number to read from (1-4).
        :param count: Number of points to read from the buffer.
        :param smu: Which SMU's buffer to read (SMUA or SMUB).
        :return: Tuple of (readings, timestamps, source_values) as lists of floats.
        """
        readings   = [float(v) for v in self.k.send_recv(f"printbuffer(1, {count}, {smu.value}.nvbuffer{buf_num}.readings)").split(", ")]
        timestamps = [float(v) for v in self.k.send_recv(f"printbuffer(1, {count}, {smu.value}.nvbuffer{buf_num}.timestamps)").split(", ")]
        sourcevals = [float(v) for v in self.k.send_recv(f"printbuffer(1, {count}, {smu.value}.nvbuffer{buf_num}.sourcevalues)").split(", ")]
        
        return readings, timestamps, sourcevals
       
    # ----------------------------------------------------------------------
    # Photodiode methods (require DC2200)
    # ----------------------------------------------------------------------
    
    def IV_vs_Light_Cycled_cc(
        self,
        v_list: Sequence[float],
        led_brightness_level: Sequence[float],
        settling_time: float,
        compliance: float,
        cycles: int,
        measure_range: Union[float, Range],
        source_range: Optional[Union[float, Range]] = None,
        max_brightness_limit: float = 0.7,
        nplc: float = 1.0,
        smu: SMU = SMU.SMUA,
        high_voltage_mode: bool = False,
        autozero: Autozero = Autozero.OFF,
        measurement_title: str = "IV vs Light (Cycled)",
        file: Optional[File] = None,
        sample: Optional[Union[str, int, Dict[str, Any]]] = config.sample,
        operator: Optional[Union[str, int, Dict[str, Any]]] = config.operator,
        custom_metadata: Optional[Dict] = None
    ) -> Dataset:
        """
        Perform a photodiode IV sweep at different LED brightness levels, repeated for a specified number of cycles.
         - v_list: List of voltage points to sweep through.
            - led_brightness_level: List of LED brightness levels (in A) to test.
            - settling_time: Time to wait after setting each voltage point before measuring (in seconds).
            - compliance: Current compliance limit for the SMU (in A).
            - cycles: Number of times to repeat the entire sweep sequence.
            - measure_range: Current measurement range for the SMU (can be a float or a Range object).
            - source_range: Voltage source range for the SMU (optional, can be a float
                or a Range object). If not provided, it will be set automatically based on the max voltage in v_list.
            - nplc: Number of power line cycles for each measurement (default is 1.0).
            - smu: Which SMU to use for the measurement (default is SMUA).
            - high_voltage_mode: If True, allows voltages up to the max range of the instrument. If False, limits to lower voltage range for certain models.
            - autozero: Autozero setting for the SMU (default is OFF).
            - measurement_title: Title for the dataset (default is "IV vs Light (Cycled)").
            - file: Optional File object to write the dataset to. If None, the dataset is not written to disk.
            - sample: Sample information to include in metadata (can be a string, int, or dict, default is config.sample).
            - operator: Operator information to include in metadata (can be a string, int, or dict, default is config.operator).
            - custom_metadata: Additional custom metadata to include in the dataset (optional)
            Returns: Dataset containing the measurement results and metadata.
            
            
            
            example usage:
            this call runs a voltage sweep from -2V to 2V in 0.01V steps, at 3
            different LED brightness levels (0.01A, 0.05A, 0.1A), with a
            settling time of 0.5s, current compliance of 100mA, repeated for 3
            cycles, and saves the results to 'list_sweep.txt':
            
            dataset = characterization.IV_vs_Light_Cycled_cc(
                v_list=create_sweep_list(-2, 2, 0.01),  # Sweep from -2V to 2V in 0.01V steps
                led_brightness_level=[0.01, 0.05, 0.1],  # Test at 3 different LED currents
                settling_time=0.5,  # Wait 0.5 seconds after setting voltage before measuring
                compliance=0.1,  # Set current compliance to 100mA
                cycles=3,  # Repeat the entire sweep sequence 3 times
                measure_range=0.1,  # Set current measurement range to 100mA
                source_range=2.0,
                max_brightness_limit=0.7,
                nplc=1.0,  # Use 1 power line cycle for measurements
                file=TextFile('list_sweep.txt')
            )             
                
        """
        self._check_dc()
        MAX_LIST_SWEEP_POINTS = 69901

        if cycles < 1:
            raise errors.InvalidCommandParameterException("cycles must be >= 1")
        
        if not high_voltage_mode and self.k.model in {Keithley2600AModel.K2611A, Keithley2600AModel.K2612A, Keithley2600AModel.K2635A, Keithley2600AModel.K2635A}:
            max_low_voltage = Keithley2600A.RANGES[self.k.model][Quantity.V][-2]
            if abs(min(v_list)) > max_low_voltage or max(v_list) > max_low_voltage:
                raise errors.InvalidCommandParameterException(f'Voltage in sweep list to high. Should be in the range of '
                                                              f'-{max_low_voltage} to {max_low_voltage} v')
        source_level_min, source_level_max = Keithley2600A.SOURCE_LEVEL_LIMITS[self.k.model][Quantity.V]
        if any(val > source_level_max or val < source_level_min for val in v_list):
            raise errors.InvalidCommandParameterException(f'Invalid sweep list level in {v_list}. Should be in the '
                                                          f'range of {source_level_min} to {source_level_max} v')
        num_points = len(v_list)
        if num_points > MAX_LIST_SWEEP_POINTS:
            raise errors.InvalidCommandParameterException(f'Max number of points ({MAX_LIST_SWEEP_POINTS}) exceeded: {num_points}')
        max_v_list = max((abs(min(v_list)), max(v_list)))
        if source_range is None:
            source_range = max_v_list
        elif not isinstance(source_range, Range) and source_range < max_v_list:
            raise errors.InvalidCommandParameterException(f'Value {max_v_list} to big for source range {source_range}')
        
        
        self.dc.switch_off()   # Ensure LED is off before starting
        self.dc.set_user_current_limit(max_brightness_limit)
        all_dataframes = []
        trigger_time = datetime.utcnow().isoformat()
        self.k.set_compliance(compliance, Quantity.I, smu)
        self.k.set_nplc(nplc, smu)
        self.k.set_autozero(autozero, smu)
        self.k.set_range(source_range, Mode.SOURCE, Quantity.V, smu)
        self.k.set_range(measure_range, Mode.MEASURE, Quantity.I, smu)
        for c in range(1, cycles+1):
             print(f"--- Starting cycle {c} of {cycles} ---")
             self.k.clear_error_queue()
             for led_i in led_brightness_level:
                print(f"Testing LED current: {led_i} A")
                # 1. Update point calculation to include the 2 READ pulses
                
                total_points = num_points
                
                # Configure DC2200 for this current
                self.dc.configure_constant_brightness(led_i)
                self.dc.switch_on()
                time.sleep(0.1)

                # Keithley setup (repeated for each LED current to ensure clean state)
                

                # Load script and send lists
                self.k.send("loadandrunscript")

                for cmd in self.k._split_table_definition_command(
                    f"local v_list = {self.k.serialize_sequence(v_list)}"):
                    self.k.send(cmd)
                # Call the Lua function CustomSweep (does not toggle digio bit)
                self.k.send(
                    f"CustomSweep({smu.value}, "
                    f"v_list, {settling_time}, {num_points})"
                )
                    
                self.k.send('v_list = nil')
                self.k.send("endscript")

                # Wait for measurement to complete (estimate)
                time.sleep(total_points * (settling_time + nplc * 0.02))

                self.k.check_error_queue(force=True)
                self.dc.switch_off()   
                
                actual_source_range = float(self.k.query(f'{smu.value}.source.rangev'))
                actual_measure_range = float(self.k.query(f'{smu.value}.measure.rangei'))
                readings = [float(v) for v in self.k.send_recv(f"printbuffer(1, {total_points}, {smu.value}.nvbuffer1.readings)").split(", ")]
                timestamps = [float(v) for v in self.k.send_recv(f"printbuffer(1, {total_points}, {smu.value}.nvbuffer1.timestamps)").split(", ")]
                source_values = [float(v) for v in self.k.send_recv(f"printbuffer(1, {total_points}, {smu.value}.nvbuffer1.sourcevalues)").split(", ")]
                self.k.clear_buffer(1, smu)
                self.k.check_error_queue(force=True)

                df = pd.DataFrame({
                        "t": timestamps,
                        "v": source_values,
                        "i": readings,
                        "cycle": c,
                        "led_brightness": led_i
                    })
                
                all_dataframes.append(df)

        # Combine all data
        master_df = pd.concat(all_dataframes, ignore_index=True)
        column_descriptions = {
            "t": "Timestamp of each measurement point (s)",
            "v": "Voltage applied by SMU (V)",
            "i": "Current measured by SMU (A)",
            "cycle": "Cycle number of the measurement (1 to cycles)",
            "led_brightness": "LED brightness level (A) set on DC2200"
        }
        metadata = {
                    "utc_datetime": trigger_time,   # time of last measurement
                    "instrument_idn": self.k.id_str,
                    "measurement_settings": {
                        "type": "photodiode_IV_vs_light_cycled",
                        "v_list": [float(v) for v in v_list],
                        "cycles": cycles,
                        "compliance": compliance,
                        "nplc": nplc,
                        "settling_time": settling_time,
                        'source_range': actual_source_range,
                        'measure_range': actual_measure_range,
                        'configured_source_range': source_range,
                        'configured_measure_range': measure_range,
                        "led_brightness_level": [float(v) for v in led_brightness_level],
                        "smu": smu.value
                        },'column_descriptions': column_descriptions
                    }
        if custom_metadata:
            metadata["custom_metadata"] = custom_metadata

        dataset = Dataset(title=measurement_title, metadata=metadata, data=master_df)
        if file:
            file.write(dataset)
        return dataset
    
    def IV_vs_Light_Cycled_ttl(
        self,
        v_list: Sequence[float],
        led_current_list: Sequence[float],
        settling_time: float,
        compliance: float,
        cycles: int,
        measure_range: Union[float, Range],
        source_range: Optional[Union[float, Range]] = None,
        nplc: float = 1.0,
        digital_io_bit: int = 1,
        led_current_limit: float = 0.7,
        smu: SMU = SMU.SMUA,
        high_voltage_mode: bool = False,
        autozero: Autozero = Autozero.OFF,
        measurement_title: str = "IV vs Light (Cycled)",
        file: Optional[File] = None,
        sample: Optional[Union[str, int, Dict[str, Any]]] = config.sample,
        operator: Optional[Union[str, int, Dict[str, Any]]] = config.operator,
        custom_metadata: Optional[Dict] = None
    ) -> Dataset:
        """
        Perform a photodiode IV sweep at different LED current levels, repeated for a specified number of cycles.
         - v_list: List of voltage points to sweep through.
            - led_current_list: List of LED current levels (in A) to test.
            - settling_time: Time to wait after setting each voltage point before measuring (in seconds).
            - compliance: Current compliance limit for the SMU (in A).
            - cycles: Number of times to repeat the entire sweep sequence.
            - measure_range: Current measurement range for the SMU (can be a float or a Range object).
            - source_range: Voltage source range for the SMU (optional, can be a float
                or a Range object). If not provided, it will be set automatically based on the max voltage in v_list.
            - nplc: Number of power line cycles for each measurement (default is 1.0).
            - digital_io_bit: Digital I/O bit number to toggle for LED control (default is 1).
            - smu: Which SMU to use for the measurement (default is SMUA).
            - high_voltage_mode: If True, allows voltages up to the max range of the instrument. If False, limits to lower voltage range for certain models.
            - autozero: Autozero setting for the SMU (default is OFF).
            - measurement_title: Title for the dataset (default is "IV vs Light (Cycled)").
            - file: Optional File object to write the dataset to. If None, the dataset is not written to disk.
            - sample: Sample information to include in metadata (can be a string, int, or dict, default is config.sample).
            - operator: Operator information to include in metadata (can be a string, int, or dict, default is config.operator).
            - custom_metadata: Additional custom metadata to include in the dataset (optional)
            Returns: Dataset containing the measurement results and metadata.
            
            
            
            example usage:
            this call runs a voltage sweep from -2V to 2V in 0.01V steps, at 3
            different LED brightness levels (0.01A, 0.05A, 0.1A), with a
            settling time of 0.5s, current compliance of 100mA, repeated for 3
            cycles, and saves the results to 'list_sweep.txt':
            
            dataset = characterization.IV_vs_Light_Cycled_cc(
                v_list=create_sweep_list(-2, 2, 0.01),  # Sweep from -2V to 2V in 0.01V steps
                led_current_list=[0.01, 0.05, 0.1],  # Test at 3 different LED currents
                settling_time=0.5,  # Wait 0.5 seconds after setting voltage before measuring
                compliance=0.1,  # Set current compliance to 100mA
                cycles=3,  # Repeat the entire sweep sequence 3 times
                measure_range=0.1,  # Set current measurement range to 100mA
                source_range=2.0,  # Set voltage source range to 2V
                nplc=1.0,# Use 1 power line cycle for measurements
                digital_io_bit=1,  # Use digital I/O bit 1 to control LED
                file=TextFile('list_sweep.txt')
            )             
                
        """
        self._check_dc()
        MAX_LIST_SWEEP_POINTS = 69901

        if cycles < 1:
            raise errors.InvalidCommandParameterException("cycles must be >= 1")
        
        if not high_voltage_mode and self.k.model in {Keithley2600AModel.K2611A, Keithley2600AModel.K2612A, Keithley2600AModel.K2635A, Keithley2600AModel.K2635A}:
            max_low_voltage = Keithley2600A.RANGES[self.k.model][Quantity.V][-2]
            if abs(min(v_list)) > max_low_voltage or max(v_list) > max_low_voltage:
                raise errors.InvalidCommandParameterException(f'Voltage in sweep list to high. Should be in the range of '
                                                              f'-{max_low_voltage} to {max_low_voltage} v')
        source_level_min, source_level_max = Keithley2600A.SOURCE_LEVEL_LIMITS[self.k.model][Quantity.V]
        if any(val > source_level_max or val < source_level_min for val in v_list):
            raise errors.InvalidCommandParameterException(f'Invalid sweep list level in {v_list}. Should be in the '
                                                          f'range of {source_level_min} to {source_level_max} v')
        num_points = len(v_list)
        if num_points > MAX_LIST_SWEEP_POINTS:
            raise errors.InvalidCommandParameterException(f'Max number of points ({MAX_LIST_SWEEP_POINTS}) exceeded: {num_points}')
        max_v_list = max((abs(min(v_list)), max(v_list)))
        if source_range is None:
            source_range = max_v_list
        elif not isinstance(source_range, Range) and source_range < max_v_list:
            raise errors.InvalidCommandParameterException(f'Value {max_v_list} to big for source range {source_range}')

        all_dataframes = []
        
        trigger_time = datetime.utcnow().isoformat()
        self.k.clear_error_queue()
        self.k.set_compliance(compliance, Quantity.I, smu)
        self.k.set_nplc(nplc, smu)
        self.k.set_autozero(autozero, smu)
        self.k.set_range(source_range, Mode.SOURCE, Quantity.V, smu)
        self.k.set_range(measure_range, Mode.MEASURE, Quantity.I, smu)
        for c in range(1, cycles+1):
             print(f"--- Starting cycle {c} of {cycles} ---")
             
             for led_i in led_current_list:
                print(f"Testing LED current: {led_i} A")
                # 1. Update point calculation to include the 2 READ pulses
                self.dc.configure_ttl(led_i)
                self.dc.switch_on()
                total_points = num_points

                # Load script and send lists
                self.k.send("loadandrunscript")

                for cmd in self.k._split_table_definition_command(
                    f"local v_list = {self.k.serialize_sequence(v_list)}"):
                    self.k.send(cmd)

                

                # Call the Lua function (OESweep toggles digio bit)
                self.k.send(
                    f"CustomSweep_ttl({smu.value}, "
                    f"v_list, {settling_time}, {num_points}, {digital_io_bit})"
                )
                    
                self.k.send('v_list = nil')
                self.k.send("endscript")

                # Wait for measurement to complete (estimate)
                time.sleep(total_points * (settling_time + nplc * 0.02))

                self.k.check_error_queue(force=True)
                self.dc.switch_off()   

                actual_source_range = float(self.k.query(f'{smu.value}.source.rangev'))
                actual_measure_range = float(self.k.query(f'{smu.value}.measure.rangei'))
                readings = [float(v) for v in self.k.send_recv(f"printbuffer(1, {total_points}, {smu.value}.nvbuffer1.readings)").split(", ")]
                timestamps = [float(v) for v in self.k.send_recv(f"printbuffer(1, {total_points}, {smu.value}.nvbuffer1.timestamps)").split(", ")]
                source_values = [float(v) for v in self.k.send_recv(f"printbuffer(1, {total_points}, {smu.value}.nvbuffer1.sourcevalues)").split(", ")]

                self.k.clear_buffer(1, smu)
                self.k.check_error_queue(force=True)

                df = pd.DataFrame({
                        "t": timestamps,
                        "v": source_values,
                        "i": readings,
                        "cycle": c,
                        "led_brightness": led_i
                    })
                all_dataframes.append(df)

        # Combine all data
        master_df = pd.concat(all_dataframes, ignore_index=True)
        column_descriptions = {
            "t": "Timestamp of each measurement point (s)",
            "v": "Voltage applied by SMU (V)",
            "i": "Current measured by SMU (A)",
            "cycle": "Cycle number of the measurement (1 to cycles)",
            "led_brightness": "LED brightness level (A) set on DC2200"
        }
        metadata = {
                    "utc_datetime": trigger_time,   # time of last measurement
                    "instrument_idn": self.k.id_str,
                    "measurement_settings": {
                        "type": "photodiode_IV_vs_light_cycled",
                        "v_list": [float(v) for v in v_list],
                        "cycles": cycles,
                        "compliance": compliance,
                        "nplc": nplc,
                        "settling_time": settling_time,
                        'source_range': actual_source_range,
                        'measure_range': actual_measure_range,
                        'configured_source_range': source_range,
                        'configured_measure_range': measure_range,
                        "led_brightness_levels": [float(v) for v in led_current_list],
                        "smu": smu.value
                        }
                    }
        if custom_metadata:
            metadata["custom_metadata"] = custom_metadata

        dataset = Dataset(title=measurement_title, metadata=metadata, data=master_df)
        if file:
            file.write(dataset)
        return dataset
    
    # ----------------------------------------------------------------------
    # Memristor methods (no DC required)
    # ---------------------------------------------------------------------- 
    def formingsweep(
        self,
        v_set: float,
        v_reset: float,
        step_size: float,
        set_compliance: float,
        reset_compliance: float,
        measure_range: typing.Union[float, Range] = 3e-3,
        source_range: typing.Optional[typing.Union[float, Range]] = None,
        settling_time: float=0.002,
        nplc: float = 0.1,
        smu: SMU = SMU.SMUA,
        autozero: Autozero = Autozero.OFF,
        measurement_title: str = "Forming Sweep",
        save: bool = False,
        file: str = "forming_data.txt",
        display: bool = False,
        
        **kwargs
    ) -> Dataset:
        """_summary_

        Args:
            v_set (float): _description_
            v_reset (float): _description_
            step_size (float): _description_
            set_compliance (float): _description_
            reset_compliance (float): _description_
            measure_range (typing.Union[float, Range], optional): _description_. Defaults to 3e-3.
            source_range (typing.Optional[typing.Union[float, Range]], optional): _description_. Defaults to None.
            settling_time (float, optional): _description_. Defaults to 0.002.
            nplc (float, optional): _description_. Defaults to 0.1.
            smu (SMU, optional): _description_. Defaults to SMU.SMUA.
            autozero (Autozero, optional): _description_. Defaults to Autozero.OFF.
            measurement_title (str, optional): _description_. Defaults to "Forming Sweep".
            save (bool, optional): _description_. Defaults to False.
            file (str, optional): _description_. Defaults to "forming_data.txt".
            display (bool, optional): _description_. Defaults to False.

        Returns:
            Dataset: _description_
            example usage:
            dataset = characterization.formingsweep(
                v_set=1.0,
                v_reset=-1.0,
                step_size=0.1,
                set_compliance=0.1,
                reset_compliance=0.1
            )
        """
        MAX_LIST_SWEEP_POINTS = 69901
        # 1. Create safe triangular sweeps (returning to 0V)
        set_list = create_sweep_list([v_set], step_size)
        reset_list = create_sweep_list([v_reset], step_size)

        # 2. Determine file saving
        file_obj = TextFile(file) if save else None
        
        set_points = len(set_list)
        reset_points = len(reset_list)
        combined = list(set_list) + list(reset_list)
        max_sweep = max(abs(v) for v in combined)
        if source_range is None:
            source_range = max_sweep
        total_points = set_points + 1 + reset_points + 1 # +1 for the read after set and +1 for the read after reset
        
        if total_points > MAX_LIST_SWEEP_POINTS:
            raise errors.InvalidCommandParameterException(f'Max number of points ({MAX_LIST_SWEEP_POINTS}) exceeded: {total_points}')
        # Keithley setup (repeated for each LED current to ensure clean state)
        self.k.clear_error_queue()
        self.k.set_nplc(nplc, smu)
        self.k.set_autozero(autozero, smu)
        self.k.set_range(source_range, Mode.SOURCE, Quantity.V, smu)
        self.k.set_range(measure_range, Mode.MEASURE, Quantity.I, smu)

        # Load script and send lists
        self.k.send("loadandrunscript")

        for cmd in self.k._split_table_definition_command(
            f"local set_list = {self.k.serialize_sequence(set_list)}"
        ):
            self.k.send(cmd)
        for cmd in self.k._split_table_definition_command(
            f"local reset_list = {self.k.serialize_sequence(reset_list)}"
        ):
            self.k.send(cmd)
        self.k.send(
            f"FormingSweep({smu.value}, set_list, reset_list, "
            f"{settling_time}, {set_compliance}, {reset_compliance},"
            f"{set_points}, {reset_points})"
        )
        self.k.send('set_list = nil')
        self.k.send('reset_list = nil')
        self.k.send("endscript")
        trigger_time = datetime.utcnow().isoformat()
        # Wait for measurement to complete (estimate)
        time.sleep(total_points * (settling_time + nplc * 0.02))

        self.k.check_error_queue(force=True)
       
        actual_source_range = float(self.k.query(f'{smu.value}.source.rangev'))
        actual_measure_range = float(self.k.query(f'{smu.value}.measure.rangei'))
        r1, t1, v1 = self.get_buffer_data(1, total_points, smu)

        self.k.clear_buffer(1, smu)
        self.k.check_error_queue(force=True)

        # 2. Build the correct phase pattern for the DataFrame
        phase_pattern = (
            ["SET"] * set_points + 
            ["READ_SET"] + 
            ["RESET"] * reset_points + 
            ["READ_RESET"]
        )

        df = pd.DataFrame({
            "t": t1,
            "v": v1,
            "i": r1
        })
        
        # 3. Apply the pattern and cycle numbers correctly
        df["phase"] = phase_pattern 
        column_descriptions = {
            't': {
                'name': 'Time',
                'channel': smu.value,
                'unit': 'seconds, s'
            },
            'v': {
                'name': 'Voltage',
                'channel': smu.value,
                'unit': 'Volt, V'
            },
            'i': {
                'name': 'Current',
                'channel': smu.value,
                'unit': 'Ampere, A'
            },
            'phase': {
                'name': 'Phase',
                'description': 'SET sweep, the read after SET, the RESET sweep, or the read after RESET'
            },
            
        }

        metadata = {
            "utc_datetime": trigger_time,   # time of last measurement
            "instrument_idn": self.k.id_str,
            "measurement_settings": {
                "type": "formingsweep",
                "set_list": [float(elem) for elem in set_list],
                "reset_list": [float(elem) for elem in reset_list],
                "compliance": set_compliance,
                "nplc": nplc,
                "settling_time": settling_time,
                'source_range': actual_source_range,
                'measure_range': actual_measure_range,
                'configured_source_range': source_range,
                'configured_measure_range': measure_range,
                "smu": smu.value
            },"column_descriptions": column_descriptions
        }

        dataset = Dataset(title=measurement_title, metadata=metadata, data=df)
        if file:
            file.write(dataset)
             
        if display:
            df = dataset.data
            plot(
                x_values=df['v'],
                y_values=df['i'],
                title=measurement_title,
                x_label="Voltage (V)",
                y_label="Current (A)",
                y_scale="log" if (df['i'] > 0).all() else "linear",
                display=True
            )
        return dataset
  
    def bipolar_sweep(
        self,
        set_list: typing.Sequence[float],
        reset_list: typing.Sequence[float],
        set_compliance_list: typing.Sequence[float],
        reset_compliance: float,
        settling_time: float,
        cycles: int,
        measure_range: typing.Union[float, Range],
        read_voltage: float = -0.2,
        source_range: typing.Optional[typing.Union[float, Range]] = None,
        nplc: float = 1.0,
        smu: SMU = SMU.SMUA,
        high_voltage_mode: bool = False,
        autozero: Autozero = Autozero.OFF,
        measurement_title: str = "Bipolar Set Compliance Sweep (Dual Buffer)",
        file: typing.Optional[File] = None,
        sample: typing.Optional[typing.Union[str, int, typing.Dict[str, typing.Any]]] = config.sample,
        operator: typing.Optional[typing.Union[str, int, typing.Dict[str, typing.Any]]] = config.operator,
        custom_metadata: typing.Optional[typing.Dict] = None
        ) -> Dataset:
        """
        Perform a bipolar sweep with separate SET and RESET voltage lists, sweeping through multiple SET compliance levels, and using dual buffers to capture data after both SET and RESET phases.
         - set_list: List of voltage points for the SET sweep.
            - reset_list: List of voltage points for the RESET sweep.
            - set_compliance_list: List of current compliance levels to test for the SET phase.
            - reset_compliance: Current compliance level for the RESET phase (applied to all cycles).
            - settling_time: Time to wait after setting each voltage point before measuring (in seconds).
            - cycles: Number of times to repeat the entire SET+RESET sequence for each SET compliance
            - measure_range: Current measurement range for the SMU (can be a float or a Range object).
            - read_voltage: Voltage level to set for the read pulse after each SET and RESET phase (default is -0.2V).
            - source_range: Voltage source range for the SMU (optional, can be a float or a Range object). If not provided, it will be set automatically based on the max voltage in set_list and reset_list.
            - nplc: Number of power line cycles for each measurement (default is 1.0).
            - smu: Which SMU to use for the measurement (default is SMUA).
            - high_voltage_mode: If True, allows voltages up to the max range of the instrument. If False, limits to lower voltage range for certain models.
            - autozero: Autozero setting for the SMU (default is OFF).
            - measurement_title: Title for the dataset (default is "Bipolar Set Compliance Sweep (Dual Buffer)").
            - file: Optional File object to write the dataset to. If None, the dataset is not written to disk.
            - sample: Sample information to include in metadata (can be a string, int, or dict, default is config.sample).
            - operator: Operator information to include in metadata (can be a string, int, or dict, default is config.operator).
            - custom_metadata: Additional custom metadata to include in the dataset (optional)
            Returns: Dataset containing the measurement results and metadata.
            
                example usage:
                
                dataset = characterization.bipolar_sweep(
                    set_list=create_sweep_list(0, 2, 0.1),  # SET sweep from 0V to 2V in 0.1V steps
                    reset_list=create_sweep_list(0, -2, -0.1),  # RESET sweep from 0V to -2V in -0.1V steps
                    set_compliance_list=[0.01, 0.05, 0.1],  # Test SET compliance levels of 10mA, 50mA, and 100mA
                    reset_compliance=0.01,  # Set RESET compliance to 10mA
                    settling_time=0.5,  # Wait 0.5 seconds after setting voltage before measuring
                    cycles=3,  # Repeat the entire SET+RESET sequence 3 times for each
                    measure_range=0.1,  # Set current measurement range to 100mA
                    read_voltage=-0.2,  # Set read pulse voltage to -0.2V
                    source_range=2.0,  # Set voltage source range to 2V
                    nplc=1.0,  # Use 1 power line cycle for measurements
                    smu=SMU.SMUA,  # Use SMUA for the measurement
                    high_voltage_mode=False,  # Limit voltage range for certain models
                    autozero=Autozero.OFF,  # Disable autozero
                    measurement_title="Bipolar Set Compliance Sweep (Dual Buffer)",  # Title for the dataset
                    file=TextFile('bipolar_sweep.txt')  # Save results to 'bipolar_sweep.txt'
                )
        """
        MAX_LIST_SWEEP_POINTS = 69901

        if cycles < 1:
            raise errors.InvalidCommandParameterException("cycles must be >= 1")
        if not set_compliance_list:
            raise ValueError("set_compliance_list cannot be empty")

        set_pts = len(set_list)
        reset_pts = len(reset_list)
        total_pts = (set_pts + reset_pts + 2) * cycles 
        # Points per cycle per buffer
         # RESET sweep + read after RESET

        total_pts_buffer1 = cycles * (len(set_list) + 1)   # SET sweep + read after SET
        total_pts_buffer2 = cycles * (len(reset_list) + 1) # RESET sweep + read after RESET

        if total_pts_buffer1 > MAX_LIST_SWEEP_POINTS or total_pts_buffer2 > MAX_LIST_SWEEP_POINTS:
            raise errors.InvalidCommandParameterException(
                f"Point count exceeds buffer limit: buffer1={total_pts_buffer1}, "
                f"buffer2={total_pts_buffer2} (max {MAX_LIST_SWEEP_POINTS})"
            )

        # Voltage safety checks (same as before)
        combined = list(set_list) + list(reset_list) + [read_voltage]
        if not high_voltage_mode and self.k.model in {
            Keithley2600AModel.K2611A, Keithley2600AModel.K2612A,
            Keithley2600AModel.K2635A, Keithley2600AModel.K2636A
        }:
            max_low_voltage = Keithley2600A.RANGES[self.k.model][Quantity.V][-2]
            if abs(min(combined)) > max_low_voltage or max(combined) > max_low_voltage:
                raise errors.InvalidCommandParameterException(
                    f'Voltage out of range ±{max_low_voltage} V'
                )

        max_v = max(abs(min(combined)), max(combined))
        if source_range is None:
            source_range = max_v
        elif not isinstance(source_range, Range) and source_range < max_v:
            raise errors.InvalidCommandParameterException(
                f"Source range {source_range} too small for max voltage {max_v}"
            )

        # --- Keithley general setup (once) ---
        self.k.clear_error_queue()
        self.k.set_nplc(nplc, smu)
        self.k.set_autozero(autozero, smu)
        self.k.set_range(source_range, Mode.SOURCE, Quantity.V, smu)
        self.k.set_range(measure_range, Mode.MEASURE, Quantity.I, smu)

        all_dfs = []
        start_time = datetime.utcnow().isoformat()

        for set_comp in set_compliance_list:
            print(f"--- Testing set compliance = {set_comp} A ---")
            
            self.k.send("loadandrunscript")
            # Send the lists as local variables
            for cmd in self.k._split_table_definition_command(
                f"local set_list = {self.k.serialize_sequence(set_list)}"
            ):
                self.k.send(cmd)
            for cmd in self.k._split_table_definition_command(
                f"local reset_list = {self.k.serialize_sequence(reset_list)}"
            ):
                self.k.send(cmd)

            # Call the Lua function
            self.k.send(
                f"BipolarSweepDualBuffer({smu.value}, set_list, reset_list, "
                f"{settling_time}, {set_comp}, {reset_compliance}, "
                f"{set_pts}, {reset_pts}, {cycles}, {read_voltage})"
            )
            self.k.send("set_list = nil")
            self.k.send("reset_list = nil")
            self.k.send("endscript")

            # Estimate total time and wait
            # Rough estimate: each point ~ settling_time + nplc*0.02, plus read pulses are instantaneous
            time.sleep(total_pts * (settling_time + nplc * 0.02))

            self.k.check_error_queue()

            # Buffer 1: SET + READ_SET
            r1, t1, v1 = self.get_buffer_data(1, total_pts_buffer1, smu)
            df1 = pd.DataFrame({
                "t": t1,
                "v": v1,
                "i": r1,
            })
            # Label phases for buffer1: first set_pts are SET, then one READ_SET per cycle
            # Create phase pattern for one cycle: [SET]*set_pts + ["READ_SET"]
            phase_pattern1 = ["SET"] * set_pts + ["READ_SET"]
            phases1 = phase_pattern1 * cycles
            df1["phase"] = phases1[:total_pts_buffer1]
            df1["cycle"] = np.repeat(np.arange(1, cycles + 1), set_pts + 1)[:total_pts_buffer1]

            # Buffer 2: RESET + READ_RESET
            r2, t2, v2 = self.get_buffer_data(2, total_pts_buffer2, smu)
            df2 = pd.DataFrame({
                "t": t2,
                "v": v2,
                "i": r2,
            })
            phase_pattern2 = ["RESET"] * reset_pts + ["READ_RESET"]
            phases2 = phase_pattern2 * cycles
            df2["phase"] = phases2[:total_pts_buffer2]
            df2["cycle"] = np.repeat(np.arange(1, cycles + 1), reset_pts + 1)[:total_pts_buffer2]

            # Combine the two buffers for this set compliance
            df_comp = pd.concat([df1, df2], ignore_index=True, sort=False)
            df_comp["set_compliance"] = set_comp

            all_dfs.append(df_comp)

            # Clear buffers for next iteration
            self.k.clear_buffer(1, smu)
            self.k.clear_buffer(2, smu)
            self.k.check_error_queue(force=True)

        # --- Combine all set compliance data ---
        master_df = pd.concat(all_dfs, ignore_index=True)
        column_descriptions = {
            "t": "Timestamp of each measurement point (s)",
            "v": "Voltage applied by SMU (V)",
            "i": "Current measured by SMU (A)",
            "phase": "Phase of the sweep (SET, READ_SET, RESET, READ_RESET)",
            "cycle": "Cycle number of the measurement (1 to cycles)",
            "set_compliance": "Current compliance level for the SET phase (A)"
        }
        # Sort by set_compliance, cycle, and timestamp (optional)
        master_df.sort_values(["set_compliance", "cycle", "t"], inplace=True)
        master_df.reset_index(drop=True, inplace=True)
        # Metadata
        actual_source_range = float(self.k.query(f'{smu.value}.source.rangev'))
        actual_measure_range = float(self.k.query(f'{smu.value}.measure.rangei'))

        metadata = {
            "utc_datetime": start_time,
            "instrument_idn": self.k.id_str,
            "measurement_settings": {
                "type": "bipolar_set_compliance_sweep_dual_buffer",
                "set_list": list(set_list),
                "reset_list": list(reset_list),
                "set_compliance_list": list(set_compliance_list),
                "reset_compliance": reset_compliance,
                "cycles": cycles,
                "settling_time": settling_time,
                "read_voltage": read_voltage,
                "nplc": nplc,
                "source_range": actual_source_range,
                "measure_range": actual_measure_range,
                "configured_source_range": source_range,
                "configured_measure_range": measure_range,
                "smu": smu.value
            },'column_descriptions': column_descriptions
        }
        if custom_metadata:
            metadata["custom_metadata"] = custom_metadata

        dataset = Dataset(title=measurement_title, metadata=metadata, data=master_df)
        if file:
            file.write(dataset)
        return dataset
    
    
    

    