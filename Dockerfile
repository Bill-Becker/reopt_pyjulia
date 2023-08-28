FROM python:3.9.17

WORKDIR /app
# Mounting local directory into container is done in docker-compose.yml
# COPY . .   ?
COPY . /app

RUN pip install julia jill numpy --no-cache-dir  
# Leaving out ipython for PyJulia REopt debugging
# julia is pyjulia, our python-julia interface
# jill is a python package for easy Julia installation
# IPython is helpful for magic (both %time and %julia)
# Include these in your requirements.txt if you have that instead

RUN jill install 1.8.5 -confirm

# PyJulia setup (installs PyCall & other necessities)
RUN python -c "import julia; julia.install()"

# Helpful Development Packages
RUN julia -e 'using Pkg; Pkg.add(["Revise", "BenchmarkTools", "JSON", "JuMP"])'
# Feature branch of REopt.jl
RUN julia -e 'using Pkg; Pkg.add(url = "https://github.com/NREL/REopt.jl", rev = "handle-urdb-matrix")'

# Requirements for main dgen code
RUN pip install colorama colorlog requests matplotlib numpy openpyxl pandas==1.1.5 pyarrow psutil psycopg2==2.8.6 scipy sqlalchemy==1.4.39 nrel-pysam

# Starts bash terminal?
CMD ["bash"]