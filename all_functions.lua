function CustomSweep(smu, vlist, stime, points)
    -- Temporary variables used by this function.
    local l_j

    display.clear()

    -- Update display with test info.
    display.settext("Sweep V List I")  -- Line 1 (20 characters max)

    -- Configure source and measure settings.
    smu.source.output = smu.OUTPUT_OFF
    smu.source.func = smu.OUTPUT_DCVOLTS
    smu.source.levelv = vlist[1]

    -- Setup a buffer to store the result(s) in and start testing.
    smu.nvbuffer1.clear()
    smu.nvbuffer1.appendmode = 1
    smu.nvbuffer1.collecttimestamps = 1
    smu.nvbuffer1.collectsourcevalues = 1

    -- Reset trigger model
    smu.trigger.arm.stimulus = 0
    smu.trigger.source.stimulus = 0
    smu.trigger.measure.stimulus = 0
    smu.trigger.endpulse.stimulus = 0
    smu.trigger.arm.count = 1
    -- Configure the source action
    smu.trigger.source.listv(vlist)
    smu.trigger.source.action = smu.ENABLE
    smu.trigger.endpulse.action = smu.SOURCE_HOLD
    -- Configure the measure action
    smu.trigger.measure.i(smu.nvbuffer1)
    smu.trigger.measure.action = smu.ENABLE
    -- Configure the delay
    if (stime > 0) then
        trigger.timer[1].reset()
        trigger.timer[1].delay = stime
        smu.trigger.measure.stimulus = trigger.timer[1].EVENT_ID
        trigger.timer[1].stimulus = smu.trigger.SOURCE_COMPLETE_EVENT_ID
    end
    -- Configure the sweep count
    smu.trigger.count = points

    -- Run the sweep and then turn the output off.
    smu.source.output = smu.OUTPUT_ON
    smu.trigger.initiate()
    waitcomplete()
    smu.source.output = smu.OUTPUT_OFF
    display.clear()
end


function CustomSweep_ttl(smu, vlist, stime, points, digital_io_bit)
    -- Temporary variables used by this function.
    local l_j

    display.clear()

    -- Update display with test info.
    display.settext("Sweep V List I + TTL")  -- Line 1 (20 characters max)

    -- Configure source and measure settings.
    smu.source.output = smu.OUTPUT_OFF
    smu.source.func = smu.OUTPUT_DCVOLTS
    smu.source.levelv = vlist[1]

    -- Setup a buffer to store the result(s) in and start testing.
    smu.nvbuffer1.clear()
    smu.nvbuffer1.appendmode = 1
    smu.nvbuffer1.collecttimestamps = 1
    smu.nvbuffer1.collectsourcevalues = 1

    -- Reset trigger model
    smu.trigger.arm.stimulus = 0
    smu.trigger.source.stimulus = 0
    smu.trigger.measure.stimulus = 0
    smu.trigger.endpulse.stimulus = 0
    smu.trigger.arm.count = 1
    -- Configure the source action
    smu.trigger.source.listv(vlist)
    smu.trigger.source.action = smu.ENABLE
    smu.trigger.endpulse.action = smu.SOURCE_HOLD
    -- Configure the measure action
    smu.trigger.measure.i(smu.nvbuffer1)
    smu.trigger.measure.action = smu.ENABLE
    -- Configure the delay
    if (stime > 0) then
        trigger.timer[1].reset()
        trigger.timer[1].delay = stime
        smu.trigger.measure.stimulus = trigger.timer[1].EVENT_ID
        trigger.timer[1].stimulus = smu.trigger.SOURCE_COMPLETE_EVENT_ID
    end
    -- Configure the sweep count
    smu.trigger.count = points

    -- Run the sweep and then turn the output off.
    smu.source.output = smu.OUTPUT_ON
    digio.writebit(digital_io_bit, 1)
    smu.trigger.initiate()
    waitcomplete()

    digio.writebit(digital_io_bit, 0)
    smu.source.output = smu.OUTPUT_OFF
    display.clear()
end


function OESweep(smu, set_list, reset_list, stime, comp, set_pts, reset_pts, cycles,digio_io_bit)
    display.clear()
    display.settext("OESweep + Read")

    -- Initial Setup
    smu.source.output = smu.OUTPUT_OFF
    smu.source.func = smu.OUTPUT_DCVOLTS
    smu.nvbuffer1.clear()
    smu.nvbuffer1.appendmode = 1
    smu.nvbuffer1.collecttimestamps = 1
    smu.nvbuffer1.collectsourcevalues = 1

    -- Trigger Model Configuration
    smu.trigger.arm.stimulus = 0
    smu.trigger.source.stimulus = 0
    smu.trigger.measure.stimulus = 0
    smu.trigger.endpulse.stimulus = 0
    smu.trigger.arm.count = 1
    smu.trigger.source.action = smu.ENABLE
    smu.trigger.endpulse.action = smu.SOURCE_HOLD
    smu.trigger.measure.i(smu.nvbuffer1)
    smu.trigger.measure.action = smu.ENABLE
    smu.source.limiti = comp

    if (stime > 0) then
        trigger.timer[1].reset()
        trigger.timer[1].delay = stime
        smu.trigger.measure.stimulus = trigger.timer[1].EVENT_ID
        trigger.timer[1].stimulus = smu.trigger.SOURCE_COMPLETE_EVENT_ID
    end

    smu.source.output = smu.OUTPUT_ON

    for i = 1, cycles do
        display.setcursor(2,1)
        display.settext("Cycle " .. i)
        
        -- Turn LED ON via DigIO
        digio.writebit(digio_io_bit,1)

        -- --- PHASE 1: SET SWEEP ---
        smu.trigger.source.listv(set_list)
        smu.trigger.count = set_pts
        smu.trigger.initiate()
        waitcomplete()
        digio.writebit(digio_io_bit,0)
        
        -- --- PHASE 2: READ AFTER SET ---
        smu.source.levelv = -0.2
        smu.measure.i(smu.nvbuffer1) -- Capture single point at 0.2V
        
        -- --- PHASE 3: RESET SWEEP ---
        smu.trigger.source.listv(reset_list)
        smu.trigger.count = reset_pts
        smu.trigger.initiate()
        waitcomplete()

        -- --- PHASE 4: READ AFTER RESET ---
        smu.source.levelv = -0.2
        smu.measure.i(smu.nvbuffer1) -- Capture single point at 0.2V
        
        -- Turn LED OFF
        
    end

    smu.source.output = smu.OUTPUT_OFF
    display.clear()
    display.settext("Sweep Done")
end




function BipolarSweepDualBuffer(smu, set_list, reset_list, stime, set_comp, reset_comp,
                                 set_pts, reset_pts, cycles, read_voltage)
    display.clear()
    display.settext("Dual‑Buffer Sweep")

    -- Turn output off initially
    smu.source.output = smu.OUTPUT_OFF
    smu.source.func = smu.OUTPUT_DCVOLTS

    -- Clear and configure both buffers
    smu.nvbuffer1.clear()
    smu.nvbuffer2.clear()
    smu.nvbuffer1.appendmode = 1
    smu.nvbuffer2.appendmode = 1
    smu.nvbuffer1.collecttimestamps = 1
    smu.nvbuffer1.collectsourcevalues = 1
    smu.nvbuffer2.collecttimestamps = 1
    smu.nvbuffer2.collectsourcevalues = 1

    -- Shared trigger model settings
    smu.trigger.arm.stimulus = 0
    smu.trigger.source.stimulus = 0
    smu.trigger.measure.stimulus = 0
    smu.trigger.endpulse.stimulus = 0
    smu.trigger.arm.count = 1
    smu.trigger.source.action = smu.ENABLE
    smu.trigger.endpulse.action = smu.SOURCE_HOLD

    -- Configure timer for settling time (if any)
    if stime > 0 then
        trigger.timer[1].reset()
        trigger.timer[1].delay = stime
        smu.trigger.measure.stimulus = trigger.timer[1].EVENT_ID
        trigger.timer[1].stimulus = smu.trigger.SOURCE_COMPLETE_EVENT_ID
    else
        smu.trigger.measure.stimulus = smu.trigger.SOURCE_COMPLETE_EVENT_ID
    end

    -- Turn output on for the whole measurement
    smu.source.output = smu.OUTPUT_ON

    for i = 1, cycles do
        display.setcursor(2,1)
        display.settext("Cycle " .. i)

        -- --- PHASE 1: SET SWEEP (store in buffer1) ---
        smu.source.limiti = set_comp
        smu.trigger.source.listv(set_list)
        smu.trigger.count = set_pts
        smu.trigger.measure.i(smu.nvbuffer1)
        smu.trigger.initiate()
        waitcomplete()

        -- --- PHASE 2: READ AFTER SET (store in buffer1) ---
        smu.source.levelv = read_voltage
        smu.measure.i(smu.nvbuffer1)   -- single point, appended to buffer1

        -- --- PHASE 3: RESET SWEEP (store in buffer2) ---
        smu.source.limiti = reset_comp
        smu.trigger.source.listv(reset_list)
        smu.trigger.count = reset_pts
        smu.trigger.measure.i(smu.nvbuffer2)
        smu.trigger.initiate()
        waitcomplete()

        -- --- PHASE 4: READ AFTER RESET (store in buffer2) ---
        smu.source.levelv = read_voltage
        smu.measure.i(smu.nvbuffer2)   -- single point, appended to buffer2
    end

    smu.source.output = smu.OUTPUT_OFF
    display.clear()
    display.settext("Dual‑Buffer Done")
end




function FormingSweep(smu, set_list, reset_list, stime, set_comp, reset_comp,
                                 set_pts, reset_pts)
    display.clear()
    display.settext("Forming Sweep")

    -- Turn output off initially
    smu.source.output = smu.OUTPUT_OFF
    smu.source.func = smu.OUTPUT_DCVOLTS
    

    -- Initial Setup
    smu.nvbuffer1.clear()
    smu.nvbuffer1.appendmode = 1
    smu.nvbuffer1.collecttimestamps = 1
    smu.nvbuffer1.collectsourcevalues = 1

    -- Trigger Model Configuration
    smu.trigger.arm.stimulus = 0
    smu.trigger.source.stimulus = 0
    smu.trigger.measure.stimulus = 0
    smu.trigger.endpulse.stimulus = 0
    smu.trigger.arm.count = 1
    smu.trigger.source.action = smu.ENABLE
    smu.trigger.endpulse.action = smu.SOURCE_HOLD

    -- Configure the measure action
    smu.trigger.measure.i(smu.nvbuffer1)
    smu.trigger.measure.action = smu.ENABLE

    -- Configure timer for settling time (if any)
    if stime > 0 then
        trigger.timer[1].reset()
        trigger.timer[1].delay = stime
        smu.trigger.measure.stimulus = trigger.timer[1].EVENT_ID
        trigger.timer[1].stimulus = smu.trigger.SOURCE_COMPLETE_EVENT_ID
    end

    -- Turn output on for the whole measurement
    smu.source.output = smu.OUTPUT_ON

    -- --- PHASE 1: SET SWEEP (store in buffer1) ---
    smu.source.limiti = set_comp
    smu.trigger.source.listv(set_list)
    smu.trigger.count = set_pts
    smu.trigger.initiate()
    waitcomplete()

    -- --- PHASE 2: READ AFTER SET (store in buffer1) ---
    smu.source.levelv = -0.2
    smu.measure.i(smu.nvbuffer1)   -- single point, appended to buffer1

    smu.source.limiti = reset_comp
    smu.trigger.source.listv(reset_list)
    smu.trigger.count = reset_pts
    smu.trigger.initiate()
    waitcomplete()

    -- --- PHASE 4: READ AFTER RESET (store in buffer1) ---
    smu.source.levelv = -0.2
    smu.measure.i(smu.nvbuffer1)   -- single point, appended to buffer1

    smu.source.output = smu.OUTPUT_OFF
    display.clear()
    display.settext("Forming Sweep Done")
end