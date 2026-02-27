import time
import typing
import warnings
from datetime import datetime
import pandas as pd
import numpy as np

from measurement_control.instruments.keithley_2600a import SMU, Range, Mode, Quantity, Autozero, Keithley2600A, Keithley2600AModel
from measurement_control.instruments.thorlabs_dc2200 import DC2200
from measurement_control.datasets import Dataset
from measurement_control import errors, config
from measurement_control.files import File
from measurment_control import __version__


CUSTOM_SCRIPT_VERSION = __version__
CUSTOM_SCRIPT = "all_functions.lua"
class OptoMemristor:
    def __init__(self, keithley: Keithley2600A, dc_driver: DC2200, force_code_reload: bool = False):
        self.k = keithley
        self.dc = dc_driver
        if force_code_reload or self.k.query('GetMeasurementControlScriptID == nil') == 'true' or self.k.query('GetMeasurementControlScriptID()') != CUSTOM_SCRIPT_VERSION:
            inp_file = all_functions.lua
            with inp_file.open("rt") as f:
                custom_script_code = f.read()
            if type(self.communicator) is USBCommunicator:
                # USB communication does not transfer the complete file in one send command
                # Sending line by line seems to be fast enough
                self.send("""loadandrunscript MeasurementControl
                    function GetMeasurementControlScriptID()
                        return \"""" + CUSTOM_SCRIPT_VERSION + """\"
                    end""")
                for line in custom_script_code.split('\n'):
                    self.send(line)
                self.send("endscript")
            else:
                self.send("""loadandrunscript MeasurementControl
                    function GetMeasurementControlScriptID()
                        return \"""" + CUSTOM_SCRIPT_VERSION + """\"
                    end
                    """ + custom_script_code + """
                    endscript
                    """)
            self.check_error_queue(force=True)

    def IV_vs_Light_Cycled_cc(
        self,
        v_list: typing.Sequence[float],
        led_brightness_level: typing.Sequence[float],
        settling_time: float,
        compliance: float,
        cycles: int,
        measure_range: typing.Union[float, Range],
        source_range: typing.Optional[typing.Union[float, Range]] = None,
        max_brightness_limit: float = 0.7,
        nplc: float = 1.0,
        smu: SMU = SMU.SMUA,
        high_voltage_mode: bool = False,
        autozero: Autozero = Autozero.OFF,
        measurement_title: str = "IV vs Light (Cycled)",
        file: typing.Optional[File] = None,
        sample: typing.Optional[typing.Union[str, int, typing.Dict[str, typing.Any]]] = config.sample,
        operator: typing.Optional[typing.Union[str, int, typing.Dict[str, typing.Any]]] = config.operator,
        custom_metadata: typing.Optional[typing.Dict] = None
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
            
            dataset = opto_memristor.IV_vs_Light_Cycled_cc(
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

        self.dc.set_user_current_limit(max_brightness_limit)
        all_dataframes = []
        for c in range(1, cycles+1):
             print(f"--- Starting cycle {c} of {cycles} ---")
             for led_i in led_brightness_level:
                print(f"Testing LED current: {led_i} A")
                # 1. Update point calculation to include the 2 READ pulses
                
                total_points = num_points
                
                # Configure DC2200 for this current
                self.dc.configure_constant_brightness(led_i)
                self.dc.switch_on()
                time.sleep(0.1)

                # Keithley setup (repeated for each LED current to ensure clean state)
                self.k.clear_error_queue()
                self.k.set_compliance(compliance, Quantity.I, smu)
                self.k.set_nplc(nplc, smu)
                self.k.set_autozero(autozero, smu)
                self.k.set_range(source_range, Mode.SOURCE, Quantity.V, smu)
                self.k.set_range(measure_range, Mode.MEASURE, Quantity.I, smu)

                # Load script and send lists
                self.k.send("loadandrunscript")

                for cmd in self.k._split_table_definition_command(
                    f"local v_list = {self.k.serialize_sequence(v_list)}"):
                    self.k.send(cmd)

                trigger_time = datetime.utcnow().isoformat()

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
        
        metadata = {
                    "utc_datetime": trigger_time,   # time of last measurement
                    "instrument_idn": self.k.id_str,
                    "measurement_settings": {
                        "type": "photodiode_IV_vs_light_cycled",
                        "v_list": list(v_list),
                        "cycles": cycles,
                        "compliance": compliance,
                        "nplc": nplc,
                        "settling_time": settling_time,
                        'source_range': actual_source_range,
                        'measure_range': actual_measure_range,
                        'configured_source_range': source_range,
                        'configured_measure_range': measure_range,
                        "led_brightness_levels": list(led_brightness_level),
                        "smu": smu.value
                        }
                    }
        if custom_metadata:
            metadata["custom_metadata"] = custom_metadata

        dataset = Dataset(title=measurement_title, metadata=metadata, data=master_df)
        if file:
            file.write(dataset)
        return dataset
    
    def IV_vs_Light_Cycled_ttl(
        self,
        v_list: typing.Sequence[float],
        led_current_list: typing.Sequence[float],
        settling_time: float,
        compliance: float,
        cycles: int,
        measure_range: typing.Union[float, Range],
        source_range: typing.Optional[typing.Union[float, Range]] = None,
        nplc: float = 1.0,
        digital_io_bit: int = 1,
        led_current_limit: float = 0.7,
        smu: SMU = SMU.SMUA,
        high_voltage_mode: bool = False,
        autozero: Autozero = Autozero.OFF,
        measurement_title: str = "IV vs Light (Cycled)",
        file: typing.Optional[File] = None,
        sample: typing.Optional[typing.Union[str, int, typing.Dict[str, typing.Any]]] = config.sample,
        operator: typing.Optional[typing.Union[str, int, typing.Dict[str, typing.Any]]] = config.operator,
        custom_metadata: typing.Optional[typing.Dict] = None
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
            
            dataset = opto_memristor.IV_vs_Light_Cycled_cc(
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
        
        
        time.sleep(0.1)
        for c in range(1, cycles+1):
             print(f"--- Starting cycle {c} of {cycles} ---")
             for led_i in led_current_list:
                print(f"Testing LED current: {led_i} A")
                # 1. Update point calculation to include the 2 READ pulses
                self.dc.configure_ttl(led_i)
                self.dc.switch_on()
                total_points = num_points
                
                # Configure DC2200 for this current
                

                # Keithley setup (repeated for each LED current to ensure clean state)
                self.k.clear_error_queue()
                self.k.set_compliance(compliance, Quantity.I, smu)
                self.k.set_nplc(nplc, smu)
                self.k.set_autozero(autozero, smu)
                self.k.set_range(source_range, Mode.SOURCE, Quantity.V, smu)
                self.k.set_range(measure_range, Mode.MEASURE, Quantity.I, smu)

                # Load script and send lists
                self.k.send("loadandrunscript")

                for cmd in self.k._split_table_definition_command(
                    f"local v_list = {self.k.serialize_sequence(v_list)}"):
                    self.k.send(cmd)

                trigger_time = datetime.utcnow().isoformat()

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
        
        metadata = {
                    "utc_datetime": trigger_time,   # time of last measurement
                    "instrument_idn": self.k.id_str,
                    "measurement_settings": {
                        "type": "photodiode_IV_vs_light_cycled",
                        "v_list": list(v_list),
                        "cycles": cycles,
                        "compliance": compliance,
                        "nplc": nplc,
                        "settling_time": settling_time,
                        'source_range': actual_source_range,
                        'measure_range': actual_measure_range,
                        'configured_source_range': source_range,
                        'configured_measure_range': measure_range,
                        "led_brightness_levels": list(led_brightness_level),
                        "smu": smu.value
                        }
                    }
        if custom_metadata:
            metadata["custom_metadata"] = custom_metadata

        dataset = Dataset(title=measurement_title, metadata=metadata, data=master_df)
        if file:
            file.write(dataset)
        return dataset
    
    
    def bipolar_set_compliance_sweep_dual_buffer(
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
                
                dataset = opto_memristor.bipolar_set_compliance_sweep_dual_buffer(
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
            # # --- Retrieve data from both buffers ---
            # n1 = int(float(self.k.send_recv(f"print({smu.value}.nvbuffer1.n)")))
            # n2 = int(float(self.k.send_recv(f"print({smu.value}.nvbuffer2.n)")))

            # if n1 == 0 and n2 == 0:
            #     raise RuntimeError("No data collected")

            # if n1 != total_pts_buffer1:
            #     warnings.warn(f"Buffer1: expected {total_pts_buffer1} points, got {n1}")
            # if n2 != total_pts_buffer2:
            #     warnings.warn(f"Buffer2: expected {total_pts_buffer2} points, got {n2}")


            # Helper to fetch buffer data
            
            
            def get_buffer_data(buf_num, count):
                readings   = [float(v) for v in self.k.send_recv(f"printbuffer(1, {count}, {smu.value}.nvbuffer{buf_num}.readings)").split(", ")]
                timestamps = [float(v) for v in self.k.send_recv(f"printbuffer(1, {count}, {smu.value}.nvbuffer{buf_num}.timestamps)").split(", ")]
                sourcevals = [float(v) for v in self.k.send_recv(f"printbuffer(1, {count}, {smu.value}.nvbuffer{buf_num}.sourcevalues)").split(", ")]
                return readings, timestamps, sourcevals
            

            # Buffer 1: SET + READ_SET
            r1, t1, v1 = get_buffer_data(1, total_pts_buffer1)
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
            r2, t2, v2 = get_buffer_data(2, total_pts_buffer2)
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
            }
        }
        if custom_metadata:
            metadata["custom_metadata"] = custom_metadata

        dataset = Dataset(title=measurement_title, metadata=metadata, data=master_df)
        if file:
            file.write(dataset)
        return dataset