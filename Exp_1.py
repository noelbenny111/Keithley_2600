import numpy as np
import matplotlib.pyplot as plt
import time
from measurement_control.instruments.keithley_2600 import Keithley2600
from measurement_control.communicators import GPIBCommunicator
from measurement_control.enums import SMU, Range
from measurement_control.utils.sweep_lists import create_sweep_list
from measurements.memristor import MemristorMeasurements

# -------------------------------------------------
# 1. Connect to Keithley
# -------------------------------------------------
k = GPIBCommunicator(26, visa_library='@py')


# -------------------------------------------------
# 2. Create memristor measurement interface
# -------------------------------------------------
mem = MemristorMeasurements(k)


ds = mem.bipolar_memristor_sweep(
    set_list=create_sweep_list((5,), 0.1),
    reset_list=create_sweep_list((-5,), 0.1),
    settling_time=0.01,
    set_compliance=0.0001,
    reset_compliance=0.01,
    voltage_range=5,
    current_range=Range.AUTO
)


print(ds.metadata)
print(ds.data.head())


# Optional: save
ds.data.to_csv("bipolar_memristor_sweep.txt", index=False)


k.close()