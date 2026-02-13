import time
import numpy as np
import matplotlib.pyplot as plt
from measurement_control.instruments.keithley_2600 import Keithley2600
from measurement_control.communicators import GPIBCommunicator
from measurement_control.enums import SMU

# -------------------------------
# Configuration
# -------------------------------
GPIB_ADDRESS = 26
TSP_FILE = "custom_code.lua"
SMU_CHANNEL = SMU.SMUA

vlist = np.linspace(0, 5, 1001)  # Try large list to test splitting
settling_time = 0.001
points = len(vlist)

# -------------------------------
# Connect
# -------------------------------
with Keithley2600(GPIBCommunicator(GPIB_ADDRESS, visa_library='@py')) as keithley:

    print("Connected:", keithley.id_str)
    keithley.clear_error_queue()

    # -------------------------------
    # Load TSP Function
    # -------------------------------
    with open(TSP_FILE, "r", encoding="ascii") as f:
        tsp_code = f.read()

    keithley.send("loadandrunscript")
    keithley.send(tsp_code)
    keithley.send("endscript")
    keithley.check_error_queue()

    # -------------------------------
    # Send Voltage List Safely
    # -------------------------------
    print("Sending voltage list safely...")

    for chunk in keithley._split_table_definition_command(f"local vlist = {keithley.serialize_sequence(vlist)}"):
        keithley.send(chunk)

    keithley.check_error_queue()

    # -------------------------------
    # Run Sweep
    # -------------------------------
    print("Running sweep...")

    keithley.send(
        f"CustomSweepVListMeasureI({SMU_CHANNEL.value}, vlist, {settling_time}, {points})"
    )

    time.sleep(points * (settling_time + 0.02) + 1)
    keithley.check_error_queue()

    # -------------------------------
    # Read Buffer Safely
    # -------------------------------
    actual_points = int(
        keithley.query(f"print({SMU_CHANNEL.value}.nvbuffer1.n)")
    )

    raw_i = keithley.send_recv(
        f"printbuffer(1, {actual_points}, {SMU_CHANNEL.value}.nvbuffer1.readings)"
    )
    raw_v = keithley.send_recv(
        f"printbuffer(1, {actual_points}, {SMU_CHANNEL.value}.nvbuffer1.sourcevalues)"
    )

    currents = np.array([float(x) for x in raw_i.replace(" ", "").split(",")])
    voltages = np.array([float(x) for x in raw_v.replace(" ", "").split(",")])

    # -------------------------------
    # Plot
    # -------------------------------
    plt.figure(figsize=(8, 5))
    plt.plot(voltages, currents)
    plt.xlabel("Voltage (V)")
    plt.ylabel("Current (A)")
    plt.title("CustomSweepVListMeasureI Test")
    plt.grid(True)
    plt.show()

    print("Sweep complete.")
