import time
import typing
import warnings
from datetime import datetime
from measurement_control.datasets import Dataset
import pandas as pd
from measurement_control.instruments.keithley_2600a import (
    SMU, Range, Mode, Quantity, Autozero, Keithley2600A, Keithley2600AModel
)
from measurement_control import errors, config
from measurement_control.files import File


class Memristor:
    
    def __init__(self, keithley: Keithley2600A):
        self.k = keithley
        
    def bipolar_factory_cycles(
        self,
        set_list: typing.Sequence[float],
        reset_list: typing.Sequence[float],
        settling_time: float,
        set_compliance: float,
        reset_compliance: float,
        cycles: int,
        measure_range: typing.Union[float, Range],
        source_range: typing.Optional[typing.Union[float, Range]] = None,
        nplc: float = 1.0,
        smu: SMU = SMU.SMUA,
        high_voltage_mode: bool = False,
        autozero: Autozero = Autozero.OFF,
        measurement_title: str = "Bipolar Sweep",
        file: typing.Optional[File] = None,
        sample: typing.Optional[typing.Union[str, int, typing.Dict[str, typing.Any]]] = config.sample,
        operator: typing.Optional[typing.Union[str, int, typing.Dict[str, typing.Any]]] = config.operator,
        custom_metadata: typing.Optional[typing.Dict] = None
        ) -> Dataset:
        
        MAX_LIST_SWEEP_POINTS = 69901

        if cycles < 1:
            raise errors.InvalidCommandParameterException("cycles must be >= 1")

        set_points = len(set_list)
        reset_points = len(reset_list)

        total_points = cycles * (set_points + reset_points)

        if total_points > MAX_LIST_SWEEP_POINTS:
            raise errors.InvalidCommandParameterException(
                f"Max number of points ({MAX_LIST_SWEEP_POINTS}) exceeded: {total_points}"
            )
        if sample is None or operator is None:
            warnings.warn(
                "Sample and operator should be defined.",
                FutureWarning
            )
        # Voltage safety check (same as list_sweep)
        if not high_voltage_mode and self.model in {Keithley2600AModel.K2611A, Keithley2600AModel.K2612A, Keithley2600AModel.K2635A, Keithley2600AModel.K2635A}:
            max_low_voltage = Keithley2600A.RANGES[self.model][Quantity.V][-2]
            if abs(min(set_list + reset_list)) > max_low_voltage or max(set_list + reset_list) > max_low_voltage:
                raise errors.InvalidCommandParameterException(f'Voltage in sweep list to high. Should be in the range of '
                                                              f'-{max_low_voltage} to {max_low_voltage} {source.value}.')

        max_sweep = max(
            abs(min(set_list + reset_list)),
            max(set_list + reset_list)
        )

        if source_range is None:
            source_range = max_sweep
        elif not isinstance(source_range, Range) and source_range < max_sweep:
            raise errors.InvalidCommandParameterException(
                f"Value {max_sweep} too big for source range {source_range}"
            )

        # -----------------------
        # Instrument Setup
        # -----------------------
        self.k.clear_error_queue()
        self.k.set_nplc(nplc, smu)
        self.k.set_autozero(autozero, smu)
        self.k.set_range(source_range, Mode.SOURCE, Quantity.V, smu)
        self.k.set_range(measure_range, Mode.MEASURE, Quantity.I, smu)

        # -----------------------
        # Load Lua Script
        # -----------------------
        with open("bipolarsweep.lua", "r", encoding="ascii") as f:
            lua_code = f.read()

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

        self.k.send(
            f"BipolarSweep("
            f"{smu.value}, "
            f"set_list, "
            f"reset_list, "
            f"{settling_time}, "
            f"{set_compliance}, "
            f"{reset_compliance}, "
            f"{set_points}, "
            f"{reset_points}, "
            f"{cycles})"
        )
        self.k.send('set_list = nil')
        self.k.send('reset_list = nil')
        self.k.send("endscript")

        time.sleep(total_points * (settling_time + nplc * 0.02))

        self.k.check_error_queue(force=True)
        
        
        actual_n = int(float(self.k.send_recv(f"print({smu.value}.nvbuffer1.n)")))

        if actual_n == 0:
            raise RuntimeError("Sweep failed — buffer empty.")
        actual_source_range = float(self.k.query(f'{smu.value}.source.rangev'))
        actual_measure_range = float(self.k.query(f'{smu.value}.measure.rangei'))
        # -----------------------
        # Read Buffer Once
        # -----------------------
        readings = [
            float(v) for v in self.k.send_recv(
                f"printbuffer(1, {reset_points}, {smu.value}.nvbuffer1.readings)"
            ).split(", ")
        ]

        timestamps = [
            float(v) for v in self.k.send_recv(
                f"printbuffer(1, {reset_points}, {smu.value}.nvbuffer1.timestamps)"
            ).split(", ")
        ]

        source_values = [
            float(v) for v in self.k.send_recv(
                f"printbuffer(1, {reset_points}, {smu.value}.nvbuffer1.sourcevalues)"
            ).split(", ")
        ]

        self.k.clear_buffer(1, smu)
        self.k.check_error_queue(force=True)

        # -----------------------
        # Build Dataset
        # -----------------------
        df = pd.DataFrame({
            "t": timestamps,
            "v": source_values,
            "i": readings
        })

        # Build phase + cycle columns
        phase_pattern = (
            ["SET"] * set_points +
            ["RESET"] * reset_points
        )

        df["phase"] = phase_pattern * cycles
        df["cycle"] = sum(
            [[c] * (set_points + reset_points) for c in range(1, cycles + 1)],
            []
        )

        metadata = {
            "utc_datetime": trigger_time,
            "instrument_idn": self.k.id_str,
            "measurement_settings": {
                "type": "bipolar_factory_cycles",
                "set_list": list(set_list),
                "reset_list": list(reset_list),
                "cycles": cycles,
                "set_compliance": set_compliance,
                "reset_compliance": reset_compliance,
                "nplc": nplc,
                "settling_time": settling_time,
                'source_range': actual_source_range,
                'measure_range': actual_measure_range,
                'configured_source_range': source_range,
                'configured_measure_range': measure_range,
                "smu": smu.value
            }
        }

        if custom_metadata:
            metadata["custom_metadata"] = custom_metadata

        dataset = Dataset(
            title=measurement_title,
            metadata=metadata,
            data=df
        )

        if file:
            file.write(dataset)
        return dataset