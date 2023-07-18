from julia import Main

weather_file = file_dir + "/USA_CA_San.Diego.Lindbergh.722900_2018.epw"

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
"""
outfile = open("reopt_data.json", "w")
json.dump(reopt_json, outfile, indent=4)
outfile.close()
"""

Main.eval('using Pkg; Pkg.add("JuMP"); Pkg.add("HiGHS"); Pkg.add("REopt"); Pkg.add("JSON")')
Main.eval('using JuMP; using HiGHS; using JSON; using REopt')
Main.data = reopt_json 
print("Python: list of list of dicts: ", reopt_json["ElectricTariff"]["urdb_response"]["flatdemandstructure"])
Main.model = Main.eval('Model(HiGHS.Optimizer)')
Main.tarriff = Main.eval('data["ElectricTariff"]')
Main.urdb = Main.eval('tarriff["urdb_response"]')
Main.flat_demand = Main.eval('urdb["flatdemandstructure"]')

#Main.eval('print(urdb)')
print("Julia: list of dicts")
Main.eval('print(flat_demand)')
Main.eval('\n')

# Function from urdb.jl here for debugging. Only difference is added print statements
Main.eval('\
function parse_urdb_demand_tiers(A::Array; bigM=1.0e8) \n\
    if length(A) == 0 \n\
        return [] \n\
    end \n\
    len_tiers = Int[length(r) for r in A] \n\
    print(A) \n\
    n_tiers = maximum(len_tiers) \n\
    period_with_max_tiers = findall(len_tiers .== maximum(len_tiers))[1] \n\
\
    # set up tiers and validate that the highest tier has the same value across periods \n\
    demand_tiers = Dict() \n\
    demand_maxes = Float64[] \n\
    for period in range(1, stop=length(A)) \n\
        demand_max = Float64[] \n\
        for tier in A[period] \n\
            append!(demand_max, get(tier, "max", bigM)) \n\
        end \n\
        demand_tiers[period] = demand_max \n\
        append!(demand_maxes, demand_max[end])  # TODO should this be maximum(demand_max)? \n\
    end \n\
\
    # test if the highest tier is the same across all periods \n\
    if length(Set(demand_maxes)) > 1 \n\
        @warn "Highest demand tiers do not match across periods: using max tier from largest set of tiers." \n\
    end \n\
    return demand_tiers[period_with_max_tiers] \n\
end\
')
Main.tiers = Main.parse_urdb_demand_tiers(Main.flat_demand)
print(Main.tiers)
"""
# Next steps. Need to convert more of this to the format above (pull assignments out of eval statements) 
Main.s = Main.Scenario(Main.data)
Main.eval('inputs = REoptInputs(s)')
Main.eval('results=run_reopt(model, inputs)')
Main.results
"""