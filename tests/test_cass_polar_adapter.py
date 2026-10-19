import tempfile
import unittest
from pathlib import Path
import numpy as np
import pandas as pd
from cass_polar.polar_adapter import hrv_window, convert

class PolarAdapterTest(unittest.TestCase):
    def test_constant_rr(self):
        rr=pd.DataFrame({"time_s":np.arange(1,21,dtype=float),"rr_ms":[1000.]*20})
        rmssd,n,hr=hrv_window(rr,0,21)
        self.assertEqual(rmssd,0.)
        self.assertEqual(n,20)
        self.assertEqual(hr,60.)
    def test_invalid_intervals_do_not_bridge(self):
        rr=pd.DataFrame({"time_s":np.arange(1,11,dtype=float),"rr_ms":[1000,1000,1000,1000,1000,5000,1000,1000,1000,1000]})
        rmssd,n,hr=hrv_window(rr,0,11)
        self.assertEqual(n,9)
        self.assertEqual(rmssd,0.)
    def test_conversion(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            pd.DataFrame({"timestamp":[100,101]}).to_csv(p/"eeg.csv",index=False)
            pd.DataFrame({"timestamp":100+np.arange(1,81),"rr_ms":np.tile([900.,1000.],40)}).to_csv(p/"rr.csv",index=False)
            pd.DataFrame({"window_mid":[10.,20.,30.,40.],"phase":["PRE","PRE","POST","POST"],"cortical_state":[1.,-1.,1.,-1.],"ppg2_prv_rmssd":[123.]*4}).to_csv(p/"state.csv",index=False)
            info=convert(p/"state.csv",p/"rr.csv",p/"eeg.csv",p/"out.csv")
            out=pd.read_csv(p/"out.csv")
            self.assertEqual(info["autonomic_scalar"],"polar_rr_rmssd")
            self.assertNotIn("ppg2_prv_rmssd",out)
            self.assertTrue(out.autonomic_valid.all())
            self.assertTrue((p/"out.provenance.json").exists())
if __name__=="__main__":
    unittest.main()
