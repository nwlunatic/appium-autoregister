# appium-autoregister
Automatically register connected device or emulator to selenium grid with appium

# run
+ run selenium grid
```bash
java -jar selenium-server-standalone-2.45.0.jar -role hub
```

+ run autoregistrator
```bash
ANDROID_HOME=<path_to_android_sdk> APPIUM_EXECUTABLE=<path_to_appium_executable> python3 autoregister.py
```

+ connect/disconnect your devices and emulators on runtime

+ localhost:4444/grid/console
![Alt text](/docs/grid.png?raw=true "Selenium grid with registred device and x86 emulator")
