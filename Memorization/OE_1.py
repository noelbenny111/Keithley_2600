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

class OptoMemristor:
    def __init__(self, keithley: Keithley2600A, dc_driver: DC2200):
        self.k = keithley
        self.dc = dc_driver

    def OESweep(
        self,
        set_list: typing.Sequence[float],
        reset_list: typing.Sequence[float],
        led_currents: typing.Sequence[float],
        settling_time: float,
        compliance: float,
        cycles: int,
        measure_range: typing.Union[float, Range],
        source_range: typing.Optional[typing.Union[float, Range]] = None,
        nplc: float = 1.0,
        smu: SMU = SMU.SMUA,
        high_voltage_mode: bool = False,
        autozero: Autozero = Autozero.OFF,
        measurement_title: str = "Opto Bipolar Sweep",
        file: typing.Optional[File] = None,
        sample: typing.Optional[typing.Union[str, int, typing.Dict[str, typing.Any]]] = config.sample,
        operator: typing.Optional[typing.Union[str, int, typing.Dict[str, typing.Any]]] = config.operator,
        custom_metadata: typing.Optional[typing.Dict] = None
    ) -> Dataset:
        """
        Perform bipolar switching cycles under different LED illumination intensities.
        For each LED current, the DC2200 is configured in TTL mode and armed.
        The Keithley's digital I/O line toggles the LED on/off during each cycle.
        """
        MAX_LIST_SWEEP_POINTS = 69901

        if cycles < 1:
            raise errors.InvalidCommandParameterException("cycles must be >= 1")

        set_points = len(set_list)
        reset_points = len(reset_list)
        total_points = cycles * (set_points + reset_points)

        if total_points > MAX_LIST_SWEEP_POINTS:
            raise errors.InvalidCommandParameterException(
                f"Max points ({MAX_LIST_SWEEP_POINTS}) exceeded: {total_points}"
            )

        # Voltage safety check
        if not high_voltage_mode and self.k.model in {
            Keithley2600AModel.K2611A, Keithley2600AModel.K2612A,
            Keithley2600AModel.K2635A, Keithley2600AModel.K2636A
        }:
            max_low_voltage = Keithley2600A.RANGES[self.k.model][Quantity.V][-2]
            combined = list(set_list) + list(reset_list)
            if abs(min(combined)) > max_low_voltage or max(combined) > max_low_voltage:
                raise errors.InvalidCommandParameterException(
                    f'Voltage out of range ±{max_low_voltage} V.'
                )

        max_sweep = max(abs(min(combined)), max(combined))
        if source_range is None:
            source_range = max_sweep

        # Pre-load the Lua script (common for all LED currents)
        with open("memory.lua", "r", encoding="ascii") as f:
            lua_code = f.read()

        all_dataframes = []

        for led_i in led_currents:
            print(f"--- Running {cycles} cycles at LED Current: {led_i} A ---")
            # 1. Update point calculation to include the 2 READ pulses
            points_per_cycle = set_points + 1 + reset_points + 1
            total_points = cycles * points_per_cycle
            
            # Configure DC2200 for this current
            self.dc.configure_ttl(led_i)          # enable TTL mode (active high)
            self.dc.switch_on()                 # arm (LED will light when TTL high)
            time.sleep(0.1)                     # short stabilisation

            # Keithley setup (repeated for each LED current to ensure clean state)
            self.k.clear_error_queue()
            self.k.set_nplc(nplc, smu)
            self.k.set_autozero(autozero, smu)
            self.k.set_range(source_range, Mode.SOURCE, Quantity.V, smu)
            self.k.set_range(measure_range, Mode.MEASURE, Quantity.I, smu)

            # Load script and send lists
            self.k.send("loadandrunscript")
            self.k.send(lua_code)

            for cmd in self.k._split_table_definition_command(
                f"local set_list = {self.k.serialize_sequence(set_list)}"
            ):
                self.k.send(cmd)
            for cmd in self.k._split_table_definition_command(
                f"local reset_list = {self.k.serialize_sequence(reset_list)}"
            ):
                self.k.send(cmd)

            trigger_time = datetime.utcnow().isoformat()

            # Call the Lua function (OESweep toggles digio bit)
            self.k.send(
                f"OESweep({smu.value}, set_list, reset_list, "
                f"{settling_time}, {compliance},"
                f"{set_points}, {reset_points}, {cycles})"
            )
            self.k.send('set_list = nil')
            self.k.send('reset_list = nil')
            self.k.send("endscript")

            # Wait for measurement to complete (estimate)
            time.sleep(total_points * (settling_time + nplc * 0.02) + 1.0)

            self.k.check_error_queue(force=True)
            #self.dc.switch_off()   

        #    # Retrieve data
        #     actual_n = int(float(self.k.send_recv(f"print({smu.value}.nvbuffer1.n)")))
            
        #     # Check for matches (This warning should now disappear)
        #     if actual_n != total_points:
        #         warnings.warn(f"Expected {total_points} points but got {actual_n}.")
        #         total_points = actual_n  # Adjust to actual points to avoid parsing errors
            actual_source_range = float(self.k.query(f'{smu.value}.source.rangev'))
            actual_measure_range = float(self.k.query(f'{smu.value}.measure.rangei'))
            readings = [
                float(v) for v in self.k.send_recv(
                    f"printbuffer(1, {total_points}, {smu.value}.nvbuffer1.readings)"
                ).split(", ")
            ]
            timestamps = [
                float(v) for v in self.k.send_recv(
                    f"printbuffer(1, {total_points}, {smu.value}.nvbuffer1.timestamps)"
                ).split(", ")
            ]
            source_values = [
                float(v) for v in self.k.send_recv(
                    f"printbuffer(1, {total_points}, {smu.value}.nvbuffer1.sourcevalues)"
                ).split(", ")
            ]

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
                "t": timestamps,
                "v": source_values,
                "i": readings
            })

            # 3. Apply the pattern and cycle numbers correctly
            df["phase"] = phase_pattern * cycles
            df["cycle"] = sum(
                [[c] * points_per_cycle for c in range(1, cycles + 1)],
                []
            )
            df["led_current_A"] = led_i

            all_dataframes.append(df)

        # Combine all data
        master_df = pd.concat(all_dataframes, ignore_index=True)

        metadata = {
            "utc_datetime": trigger_time,   # time of last measurement
            "instrument_idn": self.k.id_str,
            "measurement_settings": {
                "type": "opto_bipolar_sweep",
                "set_list": list(set_list),
                "reset_list": list(reset_list),
                "cycles": cycles,
                "compliance": compliance,
                "nplc": nplc,
                "settling_time": settling_time,
                'source_range': actual_source_range,
                'measure_range': actual_measure_range,
                'configured_source_range': source_range,
                'configured_measure_range': measure_range,
                "led_currents_tested": list(led_currents),
                "smu": smu.value
            }
        }
        if custom_metadata:
            metadata["custom_metadata"] = custom_metadata

        dataset = Dataset(title=measurement_title, metadata=metadata, data=master_df)
        if file:
            file.write(dataset)
        return dataset