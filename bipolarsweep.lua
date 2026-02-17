function BipolarSweep(smu, set_list, reset_list, stime, set_comp, reset_comp, cycles)
    local set_pts = table.getn(set_list)
    local reset_pts = table.getn(reset_list)

    display.clear()
    display.settext("Bipolar Sweep")

    -- Initial Setup
    smu.source.output = smu.OUTPUT_OFF
    smu.source.func = smu.OUTPUT_DCVOLTS
    smu.nvbuffer1.clear()
    smu.nvbuffer1.appendmode = 1
    smu.nvbuffer1.collecttimestamps = 1
    smu.nvbuffer1.collectsourcevalues = 1

    -- Trigger Model pre-configuration
    smu.trigger.arm.stimulus = 0
    smu.trigger.source.stimulus = 0
    smu.trigger.measure.stimulus = 0
    smu.trigger.endpulse.stimulus = 0
    smu.trigger.arm.count = 1
    smu.trigger.source.action = smu.ENABLE
    smu.trigger.endpulse.action = smu.SOURCE_HOLD
    smu.trigger.measure.i(smu.nvbuffer1)
    smu.trigger.measure.action = smu.ENABLE

    if (stime > 0) then
        trigger.timer[1].reset()
        trigger.timer[1].delay = stime
        smu.trigger.measure.stimulus = trigger.timer[1].EVENT_ID
        trigger.timer[1].stimulus = smu.trigger.SOURCE_COMPLETE_EVENT_ID
    end

    smu.source.output = smu.OUTPUT_ON

    -- The Loop
    for i = 1, cycles do
        -- Simplified display update to avoid syntax errors
        display.setcursor(2,1)
        display.settext("Cycle " .. i)

        -- --- PHASE 1: SET ---
        smu.source.limiti = set_comp
        smu.trigger.source.listv(set_list)
        smu.trigger.count = set_pts
        smu.trigger.initiate()
        waitcomplete()

        -- --- PHASE 2: RESET ---
        smu.source.limiti = reset_comp
        smu.trigger.source.listv(reset_list)
        smu.trigger.count = reset_pts
        smu.trigger.initiate()
        waitcomplete()
    end

    smu.source.output = smu.OUTPUT_OFF
    display.clear()
    display.settext("Bipolar Sweep Done")
end
