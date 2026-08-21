pio run
If `pio` is not recognized, PlatformIO's CLI may not be in your PATH. Run this instead:
& "$env:USERPROFILE\.platformio\penv\Scripts\pio.exe" run
Or add it to your PATH for the current session:
$env:PATH += ";$env:USERPROFILE\.platformio\penv\Scripts"
pio run