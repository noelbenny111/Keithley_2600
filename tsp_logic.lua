function RunSweepPhase(smu, vlist,stime)
    --Always reset trigger model
    smu.trigger.arm.stimulus =0 -- Set the trigger model to immediate (0) for continuous sweeping
    smu.trigger.source.stimulus = 0 -- Set the trigger source to immediate (0) for continuous sweeping
    smu.trigger.measure.stimulus = 0 -- Set the trigger measure stimulus to immediate (0) for continuous sweeping
    smu.trigger.endpulse.stimulus = 0 -- Set the trigger end pulse stimulus to immediate (0) for continuous sweeping
    smu.trigger.arm.count = 1 -- Set the arm count to 1 for each point in the sweep


    smu.source.levelv = vlist[1]  -- Preload the first voltage level

    --configure source
    smu.trigger.source.listv(vlist)
    smu.trigger.source.action = smu.ENABLE  -- Enable the source trigger to step through the voltage list
    smu.trigger.endpulse.action = smu.SOURCE_HOLD  -- Hold the last source level after the sweep is complete

    --configure measure action

    smu.trigger.measure.i(smu.nvbuffer1)  -- Configure the measure trigger to measure current and store in buffer 1
    smu.trigger.measure.action = smu.ENABLE  -- Enable the measure trigger

    --configure the delay

    if (stime>0) then
        trigger.timer[1].reset()  -- Reset timer 1
        trigger.timer[1].delay = stime  -- Set the delay for each point in the sweep
        smu.trigger.measure.stimulus = trigger.timer[1].EVENT_ID
        trigger.timer[1].stimulus = smu.trigger.SOURCE_COMPLETE_EVENT_ID
    end
    --Cofigure sweep count
    smu.trigger.count = #vlist  -- Set the trigger count to the number of voltage levels in the list

    --Run the sweep and then turn the output off .
    smu.source.output =smu.OUTPUT_ON
    smu.trigger.initiate()  -- Start the sweep
    waitcomplete()
end

function BipolarMemristorSweep(smu, set_list, reset_list, stime, set_compliance, reset_compliance)
     -- This function performs a bipolar memristor sweep using the Keithley 2600A SMU.
     -- smu: The Keithley 2600A SMU instrument object.
     -- set_list: A list of current levels for the SET operation (positive).
     -- reset_list: A list of current levels for the RESET operation (negative).
     -- stime: The time to hold each current level in seconds.
    -- Configure the SMU for a bipolar memristor sweep.
     display.clear()  -- Clear the display

     --update dispaly with test information
     display.settext("SET / RESET Sweep")  -- Line 1 (20 characters max)

     --configure source and measure settings
     smu.source.output = smu.OUTPUT_OFF  -- Ensure output is off before configuring
     smu.source.func = smu.OUTPUT_DCVOLTS  -- Set the source function to DC voltage
     smu.source.levelv = 0  -- Start with 0V

     --setup a buffer to store the result in and start testing
     smu.nvbuffer1.clear()  -- Clear buffer 1 for voltage measurements
     smu.nvbuffer1.appendmode = 1  -- Set buffer 1 to append mode
     smu.nvbuffer1.collecttimestamps = 1  -- Collect timestamps for each measurement
     smu.nvbuffer1.collectsourcevalues = 1  -- Collect source values for each measurement

        -- Perform the SET sweep (positive current levels)
    
    smu.source.limiti = set_compliance 
    RunSweepPhase(smu,set_list,stime)
    display.clear()
    display.settext("SET Sweep Complete")  -- Update display to indicate SET sweep completion
    

    -- Perform the RESET sweep (negative current levels)
    smu.source.limiti = reset_compliance 
    RunSweepPhase(smu,reset_list,stime)
    display.clear()
    display.settext("RESET Sweep Complete")  -- Update display to indicate RESET sweep completion

    -- After the sweep, turn off the output and display results
    smu.source.output = smu.OUTPUT_OFF  -- Turn off the output after the sweep
    display.settext("Sweep Complete")  -- Update display to indicate completion
end







