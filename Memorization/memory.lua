function OESweep(smu, set_list, reset_list, stime, comp, set_pts, reset_pts, cycles)
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
        digio.writebit(1,1)

        -- --- PHASE 1: SET SWEEP ---
        smu.trigger.source.listv(set_list)
        smu.trigger.count = set_pts
        smu.trigger.initiate()
        waitcomplete()
        digio.writebit(1,0)
        
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