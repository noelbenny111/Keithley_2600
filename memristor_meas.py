import time
import typing
from datetime import datetime
from enum import Enum
from measurement_control.datasets import Dataset
import pandas as pd
from enum import Enum
from measurement_control.instruments.keithley_2600 import SMU, Range , Mode , Quantity

class Memristor:
    
    def __init__(self, keithley: Keithley2600):
        self.k = keithley
        
        
        
    def bipolar_memristor_sweep(
        self,
        set_list: typing.Sequence[float],
        reset_list: typing.Sequence[float],
        set_compliance: float,
        reset_compliance: float,
        settling_time: float,
        current_range: typing.Union[float, Range],
        smu: SMU = SMU.SMUA,
        nplc: float = 1.0,
        voltage_range: typing.Union[float, Range] = None,
        measurement_title: str = 'Bipolar Memristor Sweep'
    ) -> Dataset:
        
        """
        Performs a bipolar sweep (SET then RESET) with independent compliance for each.
        Returns a MeasurementControl Dataset.
        """
        
        k=self.k
        
        num_points = len(set_list) + len(reset_list)
        
        # 1. Read external TSP logic
        with open('memristor_logic.tsp', 'r',encoding='ascii') as f:
            tsp_logic = f.read()

        # 2. Basic SMU Setup (using your class helpers)
        
        k.clear_error_queue()
        k.set_nplc(nplc, smu)
        if voltage_range is not None:
            k.set_range(voltage_range, Mode.SOURCE, Quantity.V, smu)
        k.set_range(current_range, Mode.MEASURE, Quantity.I, smu)
        
        
        # 3. Upload and Run Script
        k.send("loadandrunscript")
        k.send(tsp_logic)  # Uploads the functions
        
        
        # Serialize Python lists to Lua tables
        k.send(f"local sl_set = {k.serialize_sequence(set_list)}")
        k.send(f"local sl_reset = {k.serialize_sequence(reset_list)}")
        
        trigger_time = datetime.utcnow().isoformat()
        
        # Call the main function with your parameters
        k.send(
            f"BipolarMemristorSweep({smu.value}, sl_set, sl_reset, "
            f"{settling_time}, {set_compliance}, {reset_compliance})"
        )
        
        k.send("sl_set = nil")
        k.send("sl_reset = nil")
        k.send("endscript")

        # 4. Wait for hardware to finish
        # Estimated time = (points * (settling + aperture)) + safety buffer
        time.sleep( num_points * (settling_time + nplc * 0.02))
        k.check_error_queue()
        
        actual_source_range = float(
            k.query(f'{smu.value}.source.rangev')
        )
        actual_measure_range = float(
            k.query(f'{smu.value}.measure.rangei')
        )
        
        # 5. Retrieve Data from Buffer
        raw_i = [float(value) for value in k.send_recv(f'printbuffer(1, {num_points}, {smu.value}.nvbuffer1.readings)').split(', ')]
        raw_v = [float(value) for value in k.send_recv(f"printbuffer(1, {num_points}, {smu.value}.nvbuffer1.sourcevalues)").split(', ')]
        raw_t = [float(value) for value in k.send_recv(f"printbuffer(1, {num_points}, {smu.value}.nvbuffer1.timestamps)").split(', ')]
        k.clear_buffer(1, smu)
        k.check_error_queue()
        
        df_dict: typing.Dict[str, typing.List[float]] = {
            't': raw_t,
            'v': raw_v,
            'i': raw_i,
        }


        metadata = {'utc_datetime': trigger_time,
            'instrument_idn': k.id_str,
            # 'measurement_control_version': __version__,
            'measurement_settings': {
                'type': 'bipolar_memristor_sweep',
                'set_list': [float(x) for x in set_list],
                'reset_list': [float(x) for x in reset_list],
                'set_compliance': set_compliance,
                'reset_compliance': reset_compliance,
                'nplc': nplc,
                'settling_time': settling_time,
                'source_quantity': 'V',
                'measure_quantity': 'I',
                'voltage_range': actual_source_range,
                'current_range': actual_measure_range,
                'configured_voltage_range': voltage_range,
                'configured_current_range': current_range,
                'smu': smu.value
        },
                
        }
        
        dataset = Dataset(
                title=measurement_title,
                metadata=metadata,
                data=pd.DataFrame.from_dict(df_dict)
            )
        return dataset