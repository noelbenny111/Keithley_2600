function Custom(smu, ilist,stime,points)
    display.clear()  -- Clear the display

    smu.source.output = smu.OUTPUT_OFF
    smu.source.func = smu.OUTPUT_DCAMPS -- Ensure the output is off before configuring
    smu.source.leveli = ilist[1]  -- Set the current level to the first value in ilist


    --setup a buffer to store the results in and start testing
    smu.nvbuffer1.clear()  -- Clear the buffer for voltage measurements
    smu.nvbuffer1.appendmode = 1  -- Enable append mode for the buffer
    smu.nvbuffer1.collecttimestamps = 1  -- Enable timestamp collection
    smu.nvbuffer1.collectsourcevalues = 1  -- Enable source value collection


    --Reset tri