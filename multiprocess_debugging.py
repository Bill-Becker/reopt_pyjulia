import numpy as np
import json
import os
from pathlib import Path

import PySAM.Utilityrate5 as ur
import PySAM.Battery as stbt
import PySAM.Cashloan as loan
import PySAM.Pvwattsv8 as pvwatts
import julia

from functools import partial
from multiprocessing import Process, Queue, Pool

def translated_reopt_post(reopt_post):
    """
    PySAM's REopt post functions use REopt V1, whereas REopt.jl is currently on V3
    This function performs translation until the SAM functions are upgraded
    
    Parameters
    ----------
    reopt_post - a dictionary with the outputs of batt.Reopt_size_standalone_battery_post()

    Returns
    ---------
    v3_format - a dictionary formattted for REoptV3
    """
    scenario = reopt_post["Scenario"]
    site = scenario["Site"]

    v3_format = {}
    v3_format["Site"] = {"latitude" : site["latitude"], "longitude" : site["longitude"]}
    v3_format["Storage"] = site["Storage"]
    v3_format["Storage"]["installed_cost_per_kw"] = site["Storage"]["installed_cost_us_dollars_per_kw"]
    v3_format["Storage"]["installed_cost_per_kwh"] = site["Storage"]["installed_cost_us_dollars_per_kwh"]
    v3_format["Storage"]["replace_cost_per_kwh"] = site["Storage"]["replace_cost_us_dollars_per_kwh"]
    v3_format["Storage"].pop("installed_cost_us_dollars_per_kw", None)
    v3_format["Storage"].pop("installed_cost_us_dollars_per_kwh", None)
    v3_format["Storage"].pop("replace_cost_us_dollars_per_kwh", None)
    v3_format["PV"] = site["PV"]
    v3_format["PV"]["production_factor_series"] = np.array(site["PV"]["prod_factor_series_kw"]).tolist()[0:8760] # TODO: will we need subhourly?
    v3_format["PV"].pop("prod_factor_series_kw", None)
    v3_format["Financial"] = site["Financial"]
    v3_format["Financial"]["analysis_years"] = int(site["Financial"]["analysis_years"])
    v3_format["Financial"]["elec_cost_escalation_rate_fraction"] = site["Financial"]["escalation_pct"]
    v3_format["Financial"]["offtaker_tax_rate_fraction"] = site["Financial"]["offtaker_tax_pct"]
    v3_format["Financial"]["offtaker_discount_rate_fraction"] = site["Financial"]["offtaker_discount_pct"]
    v3_format["Financial"]["owner_tax_rate_fraction"] = site["Financial"]["offtaker_tax_pct"]
    v3_format["Financial"]["owner_discount_rate_fraction"] = site["Financial"]["offtaker_discount_pct"]
    v3_format["Financial"]["microgrid_upgrade_cost_fraction"] = site["Financial"]["microgrid_upgrade_cost_pct"]
    v3_format["Financial"].pop("value_of_lost_load_us_dollars_per_kwh", None)
    v3_format["Financial"].pop("escalation_pct", None)
    v3_format["Financial"].pop("om_cost_escalation_pct", None)
    v3_format["Financial"].pop("offtaker_tax_pct", None)
    v3_format["Financial"].pop("offtaker_discount_pct", None)
    v3_format["Financial"].pop("microgrid_upgrade_cost_pct", None)
    v3_format["ElectricLoad"] = site["LoadProfile"]
    v3_format["ElectricLoad"]["loads_kw"] = np.array(v3_format["ElectricLoad"]["loads_kw"]).tolist()
    v3_format["ElectricLoad"]["critical_loads_kw"] = np.array(v3_format["ElectricLoad"]["critical_loads_kw"]).tolist()
    v3_format["ElectricLoad"]["loads_kw_is_net"] = bool(v3_format["ElectricLoad"]["loads_kw_is_net"] == 1.0 or v3_format["ElectricLoad"]["loads_kw_is_net"])
    v3_format["ElectricTariff"] = site["ElectricTariff"]
    for k, v in v3_format["ElectricTariff"]["urdb_response"].items():
        if type(v) is tuple:
            if type(v[0]) is tuple:
                arr = []
                for i, n in enumerate(v):
                    
                    if type(n[0]) is dict:
                        for m in n:
                            if "max" in m:
                                if m["max"] > 1e15:
                                   m["max"] = 1e15
                            if k == "energyratestructure":
                                if v3_format["ElectricTariff"]["urdb_response"]["dgrules"] == "Net Metering":
                                    m.pop("sell")
                            
                        arr.append(np.array(n, dtype=dict))

                    elif "schedule" in k:
                        arr.append(np.array(n, dtype=int))
                    else:
                        arr.append(np.array(n))
                v3_format["ElectricTariff"]["urdb_response"][k] = np.array(arr)
            else:
                if "flatdemandmonths" in k:
                    v3_format["ElectricTariff"]["urdb_response"][k] = np.array(v, dtype=int)
                else:
                    v3_format["ElectricTariff"]["urdb_response"][k] = np.array(v)

    return v3_format

def run_reopt_for_sizing(data):
    from julia import Main
    weather_file = "USA_CA_San.Diego.Lindbergh.722900_2018.epw"

    pv = pvwatts.default("PVWattsCommercial")
    pv.SolarResource.solar_resource_file = weather_file
    pv.SolarResource.use_wf_albedo = 0
    pv.Lifetime.dc_degradation = [0.005]


    bt = stbt.from_existing(pv, "GenericBatteryCommercial")
    bt.Load.crit_load = [0] * 8760
    fin = ur.from_existing(bt, "GenericBatteryCommercial")
    cl = loan.from_existing(bt, "GenericBatteryCommercial")

    pv.execute()
    post = pv.Reopt_size_battery_post()

    reopt_post = post["reopt_post"]
    site = reopt_post["Scenario"]["Site"]
    site["latitude"] = 32.5
    site["longitude"] = -108

    storage = site["Storage"]
    storage["installed_cost_us_dollars_per_kw"] = 405.56
    storage["installed_cost_us_dollars_per_kwh"] = 225.06

    reopt_pv = {}
    reopt_pv["inv_eff"] = 0.96
    reopt_pv["dc_ac_ratio"] = 1.2
    reopt_pv["losses"] = 0.0
    reopt_pv["prod_factor_series_kw"] = pv.Outputs.gen

    site["PV"] = reopt_pv
    reopt_post["Scenario"]["Site"] = site

    reopt_json = translated_reopt_post(reopt_post)

    Main.data = reopt_json 
    Main.model = Main.eval('Model(HiGHS.Optimizer)')
    Main.s = Main.Scenario(Main.data)
    Main.inputs = Main.REoptInputs(Main.s)
    Main.eval('results=run_reopt(model, inputs)')

    # print(Main.results)

    results = {"PV" : {"size_kw" : float(Main.results["PV"]["size_kw"])}}

    if "ElectricStorage" in Main.results.keys():
        batt_dict = {"size_kw" :  float(Main.results["ElectricStorage"]["size_kw"]), "size_kwh" : float(julia.Main.results["ElectricStorage"]["size_kwh"])}
        results = results | batt_dict

    return results


class JuliaProcess(object):
    def __init__(self):
        self.processes = []
        self.queue = Queue()

    def _wrapper(self, *args):
        julia.Julia(compiled_modules=False)
        from julia import Main
        Main.eval('using Pkg; Pkg.add("JuMP"); Pkg.add("HiGHS"); Pkg.add(url = "https://github.com/NREL/REopt.jl", rev = "handle-urdb-matrix"); Pkg.add("JSON")')
        Main.eval('using JuMP; using HiGHS; using JSON; using REopt')
        print(args)
        ret = run_reopt_for_sizing(args)
        self.queue.put(ret) # this is for save the result of the function

    def run(self, *args):
        print(args)
        p = Process(target=self._wrapper, args=args)
        self.processes.append(p) # this is for save the process job
        p.start()

    def wait(self):
        self.rets = []
    
        for p in self.processes:
            ret = self.queue.get()
            self.rets.append(ret)

        for p in self.processes:
            p.join()

if __name__ == '__main__':
    cores = 4

    if cores == 1:
        results = run_reopt_for_sizing()
        print(results)
    else:

        chunks = list(range(0,8))

        jp = JuliaProcess()
        for chunk in chunks:
            jp.run(chunk)

        jp.wait()
        print(jp.rets)