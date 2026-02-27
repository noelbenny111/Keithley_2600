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


function CustomSweep_ttl(smu, vlist, stime, points)
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
    digio.writebit(1, 1)
    smu.trigger.initiate()
    waitcomplete()
    digio.writebit(1, 0)
    smu.source.output = smu.OUTPUT_OFF
    display.clear()
end