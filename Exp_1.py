import numpy as np
import matplotlib.pyplot as plt
import time
from measurement_control.instruments.keithley_2600 import Keithley2600
from measurement_control.communicators import GPIBCommunicator
from measurement_control.enums import SMU, Range
from measurement_control.utils.sweep_lists import create_sweep_list
from memristor_meas import Memristor

# -------------------------------------------------
# 1. Connect to Keithley
# -------------------------------------------------



with Keithley2600(GPIBCommunicator(26, visa_library='@py')) as k2600:
    
    # 2. Pass the active instrument instance to your Memristor class
    mem = Memristor(k2600)

    # 3. Perform the sweep inside the block
    ds = mem.bipolar_memristor_sweep(
        set_list=create_sweep_list((5,), 0.1),
        reset_list=create_sweep_list((-5,), 0.1),
        settling_time=0.001,
        set_compliance=0.0001,
        reset_compliance=0.01,
        voltage_range=5,
        current_range=1
    )

    # The connection is active here
    print("Sweep complete. Data head:")
    print(ds.data.head())


# Optional: save
ds.data.to_csv("bipolar_memristor_sweep.txt", index=False)
