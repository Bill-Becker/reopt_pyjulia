from julia import Main
# For some reason, I need to do 'using REopt' right after 'from julia import Main' otherwise
#    I get an open SSL error
# This adds the latest version of the feature branch of REopt.jl, but could be done in docker build if it was stable
Main.eval('using Pkg; Pkg.add(url = "https://github.com/NREL/REopt.jl", rev = "handle-urdb-matrix")')
Main.eval('using REopt')
import json
import numpy as np

def urdb_type_conversion(urdb_response):
    for k, v in urdb_response.items():
        if type(v) is tuple:
            if type(v[0]) is tuple:
                arr = []
                for i, n in enumerate(v):        
                    if type(n[0]) is dict:
                        for m in n:
                            if "max" in m:
                                if m["max"] > 1e15:
                                    m["max"] = 1e15
                        arr.append(np.array(n, dtype=dict))
                        #if "flatdemandstructure" in k:
                            # Append extra element to trick REopt
                        #    arr.append(np.array(n, dtype=dict).tolist())
                    elif "schedule" in k:
                        arr.append(np.array(n, dtype=int))
                    else:
                        arr.append(np.array(n))
                urdb_response[k] = np.array(arr)
            else:
                if "flatdemandmonths" in k:
                    urdb_response[k] = np.array(v, dtype=int)
                else:
                    urdb_response[k] = np.array(v)
    
    return urdb_response

with open("urdb_response.json", "r") as read_file:
    print("Converting JSON encoded data into Python dictionary")
    urdb_response = json.load(read_file)

urdb_response = urdb_type_conversion(urdb_response)

Main.eval('using JSON')

Main.urdb_response = urdb_response 

# Create a URDBRate struct with this external/outer constructor
# This may error or be wrong without the matrix -> array conversions
Main.eval('urdb_rate = REopt.URDBrate(urdb_response, 2017)')

# How to actually check that e.g. demandweekdayschedule is converted properly from matrix to array?
# demandweekdayschedule is not a field of URDBRate struct
Main.eval('println(urdb_rate.demandweekdayschedule[2][16])')