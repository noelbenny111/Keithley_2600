from pydoc import __version__
import time
import datetime
import typing
import pandas as pd

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
    num_points = len(set_list) + len(reset_list)
    
    # 1. Read external TSP logic
    with open('memristor_logic.tsp', 'r',encoding='ascii') as f:
        tsp_logic = f.read()

    # 2. Basic SMU Setup (using your class helpers)
    self.clear_error_queue()
    self.set_nplc(nplc, smu)
    self.set_range(voltage_range, Mode.SOURCE, Quantity.V, smu)
    self.set_range(current_range, Mode.MEASURE, Quantity.I, smu)

    # 3. Upload and Run Script
    self.send("loadandrunscript")
    self.send(tsp_logic)  # Uploads the functions
    
    # Serialize Python lists to Lua tables
    self.send(f"local sl_set = {self.serialize_sequence(set_list)}")
    self.send(f"local sl_reset = {self.serialize_sequence(reset_list)}")
    
    trigger_time = datetime.datetime.utcnow().isoformat()
    
    # Call the main function with your parameters
    self.send(
        f"BipolarMemristorSweep({smu.value}, sl_set, sl_reset, "
        f"{settling_time}, {set_compliance}, {reset_compliance})"
    )
    
    self.send("sl_set = nil")
    self.send("sl_reset = nil")
    self.send("endscript")

    # 4. Wait for hardware to finish
    # Estimated time = (points * (settling + aperture)) + safety buffer
    time.sleep( num_points * (settling_time + nplc * 0.02))
    self.check_error_queue()
    
    actual_source_range = float(
        self.query(f'{smu.value}.source.rangev')
    )
    actual_measure_range = float(
        self.query(f'{smu.value}.measure.rangei')
    )
    # 5. Retrieve Data from Buffer
    raw_i = self.send_recv(f"printbuffer(1, {num_points}, {smu.value}.nvbuffer1.readings)")
    raw_v = self.send_recv(f"printbuffer(1, {num_points}, {smu.value}.nvbuffer1.sourcevalues)")
    raw_t = self.send_recv(f"printbuffer(1, {num_points}, {smu.value}.nvbuffer1.timestamps)")

    # Parse CSV strings to float lists
    i_list = [float(x) for x in raw_i.split(', ')]
    v_list = [float(x) for x in raw_v.split(', ')]
    t_list = [float(x) for x in raw_t.split(', ')]

    # 6. Package into the standard Dataset format
    df_dict = {
        't': t_list,
        'v': v_list,
        'i': i_list
    }

    metadata = {'utc_datetime': trigger_time,
        'instrument_idn': self.id_str,
        'measurement_control_version': __version__,
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
    }
    dataset = Dataset(
            title=measurement_title,
            metadata=metadata,
            data=pd.DataFrame.from_dict(df_dict)
        )
    return dataset

