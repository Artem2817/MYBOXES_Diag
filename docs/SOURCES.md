# Sources and licences

Primary local sources:

- `ardupilot_hwdef/MyboxH743_mini/hwdef.dat`, `...mini_v2/hwdef.dat`, `...mini_v2_vib/hwdef.dat`: authoritative build profiles and pin assignments. Their SHA256 is retained in profiles and manifests. No `include` directives occur in these three current application HWDEFs; bootloader definitions were also inspected for offset/safe startup.
- `diagnostics/mini_v2_current_2026-11-05/FINAL-SCHEMATIC-AUDIT.ru.md` and current Altium/IOC: previous schematic/PCB evidence and electrical limitations. A HWDEF alone is not an electrical schematic.
- ArduPilot platform commit `046cafbceec1a30a202b2eefe64554e5ea54cf01`, `AP_HAL_ChibiOS/{SPIDevice,I2CDevice,AnalogIn,RCOutput,CANFDIface}.cpp`, `AP_HAL/{Device,UARTDriver,RCInput}.h`.
- ArduPilot `AP_InertialSensor_Invensensev3.cpp`, `AP_Baro_MS5611.cpp`, `AP_Baro_SPL06.cpp`: identity/configuration, endianness, scale and compensation formula reference. This diagnostic application uses HAL devices directly so failure of one sensor does not enter the autopilot frontend's no-sensor panic.

Primary public references:

- [TDK ICM-42688-P DS-000347](https://invensense.tdk.com/wp-content/uploads/2020/04/ds-000347_icm-42688-p-datasheet.pdf).
- [TDK ICM-42670-P DS-000451](https://product.tdk.com/system/files/dam/doc/product/sensor/mortion-inertial/imu/data_sheet/ds-000451-icm-42670-p.pdf).
- [TDK ICM-45686 DS-000577](https://invensense.tdk.com/wp-content/uploads/documentation/DS-000577_ICM-45686.pdf).
- [TDK ICM-45686 official driver and register map](https://github.com/tdk-invn-oss/motion.mcu.icm45686.driver/tree/main/icm45686/imu). In particular indirect addressing/ready, SREG endianness, DRDY and ODR/full-scale enumerations were checked. Accessed 2026-11-20; driver is a reference, not dynamically downloaded at firmware runtime.
- [SPA06-003 datasheet](https://cdn-shop.adafruit.com/product-files/6420/spa06-003.PDF) and the existing patched SPL06 driver, including c31/c40.
- [Current MYBOXES_INAV wiring, DShot and ESC telemetry documentation](https://github.com/Artem2817/MYBOXES_INAV/blob/main/README.ru.md): INAV r10+ DShot150/300/600, per-output limits and UART telemetry. Diagnostic PWM does not claim DShot validation.
- [Current site source](https://github.com/Artem2817/MYBOXES_Ardupilot/tree/main/site/firmware-download), existing build script and workflow. Their catalog routing is preserved.

Code in this kit is GPL-3.0-or-later and links ArduPilot/ChibiOS under their applicable licences. Original source headers and licensing of the platform remain in the pinned checkout. Desktop dependencies retain their own licences; Qt/PySide6 is distributed through the official Essentials wheel. Dependency notices are retained in the Windows distribution. The implementation and accompanying documentation were AI-assisted.
