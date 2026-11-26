import math
import numpy as np
from mybox_diag.charts import chart_values

def test_chart_series_use_physical_measurements_and_leave_gaps_for_stale_samples():
    values=chart_values(dict(sensor='imu0',fresh=True,accel_m_s2=[0,0,9.80665],gyro_deg_s=[1,2,3],raw=[2000]*7,sample_count=999999,temperature_c=25))
    assert values['imu0.accel_m_s2.2']==9.80665 and len(values)==7
    assert not any('raw' in key or 'sample_count' in key for key in values)
    assert math.isnan(chart_values(dict(sensor='baro0',fresh=False,pressure_pa=101325))['baro0.pressure_pa'])

def test_baro_units_time_window_and_pause_are_readable_on_the_bench():
    from PySide6.QtWidgets import QApplication
    from mybox_diag.charts import ChartsDialog
    app=QApplication.instance() or QApplication([]);clock=[100.0];data={'baro0.pressure_pa':[(100,101325),(101,101330)],'baro0.relative_altitude_m':[(100,0),(101,.5)],'baro0.temperature_c':[(101,24)]}
    dialog=ChartsDialog(data,clock=lambda:clock[0]);dialog.set_board({'barometer_count':1});clock[0]=101;dialog.select_group('baro');dialog.refresh()
    try:
        pressure,height=dialog.pages['baro'];x,y=pressure.curves[0].getData()
        np.testing.assert_allclose(y,[1013.25,1013.3]);np.testing.assert_allclose(x,[0,1])
        assert 'гПа' in pressure.values.text() and '0.50' in height.values.text() and '°C' in dialog.info.text()
        dialog.pause.setChecked(True);before=pressure.curves[0].getData()[1].copy();clock[0]=102;data['baro0.pressure_pa'].append((102,102000));dialog.refresh()
        np.testing.assert_allclose(pressure.curves[0].getData()[1],before)
        dialog.pause.setChecked(False);dialog.refresh();assert pressure.curves[0].getData()[1][-1]==1020
        clock[0]=200;dialog.refresh();assert pressure.curves[0].getData()[0] is None or len(pressure.curves[0].getData()[0])==0
        assert 'Нет свежих' in dialog.info.text()
    finally:dialog.close();app.processEvents()
