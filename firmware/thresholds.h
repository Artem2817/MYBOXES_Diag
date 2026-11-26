// Generated from config/thresholds.json; edit that file.
#pragma once
namespace cfg {
constexpr unsigned imu_stale_ms = 250U;
constexpr unsigned baro_stale_ms = 500U;
constexpr unsigned observation_ms = 1500U;
constexpr float rest_gyro_deg_s = 5.0f;
constexpr float rest_gravity_tolerance_m_s2 = 1.5f;
constexpr float motion_gyro_deg_s = 30.0f;
constexpr float imu_difference_m_s2 = 3.0f;
constexpr float pressure_min_pa = 10000.0f;
constexpr float pressure_max_pa = 130000.0f;
constexpr float temperature_min_c = -40.0f;
constexpr float temperature_max_c = 85.0f;
constexpr unsigned actuator_lease_ms = 750U;
constexpr unsigned actuator_max_ms = 2000U;
constexpr unsigned test_timeout_ms = 6000U;
}
