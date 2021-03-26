# a relay must have been running longer than this to be considered
RUN_FREQ_THRESH=0.01

BOOTSTRAP_LENGTH_SECONDS=300
SIMULATION_LENGTH_SECONDS=3600

SHADOW_DATA_PATH="shadow.data"
SHADOW_TEMPLATE_PATH="{}.template".format(SHADOW_DATA_PATH)
CONFIG_DIRNAME="conf"
SHADOW_INSTALL_PREFIX="~/.shadow"
SHADOW_HOSTS_PATH="hosts"
SHADOW_CONFIG_FILENAME="shadow.config.xml"

SHADOW_XML_HOST_KEY="host"
SHADOW_XML_PROCESS_KEY="process"

RESOLV_FILENAME="shadowresolv.conf"
BW_AUTHORITY_NAME="bwauthority"

TORRC_COMMON_FILENAME="tor.common.torrc"
TORRC_AUTHORITY_FILENAME="tor.authority.torrc"
TORRC_EXITRELAY_FILENAME="tor.exitrelay.torrc"
TORRC_NONEXITRELAY_FILENAME="tor.nonexitrelay.torrc"
TORRC_MARKOVCLIENT_FILENAME="tor.markovclient.torrc"
TORRC_PERFCLIENT_FILENAME="tor.perfclient.torrc"

TOR_SOCKS_PORT=9050
TOR_CONTROL_PORT=9051
TOR_OR_PORT=9001
TOR_DIR_PORT=8080
TOR_GUARD_MIN_CONSBW=2000

# country codes where we can place directory authority tor hosts
DIRAUTH_COUNTRY_CODES=["US", "DE", "NL", "FR", "SE"]

# this number of data equals 1 MBit
BW_1MBIT_BYTES = int(round(1000*1000/8))
BW_1MBIT_KIB = int(round(BW_1MBIT_BYTES/1024))
# this number of data equals 1 GBit
BW_1GBIT_BYTES = int(round(1000*1000*1000/8))
BW_1GBIT_KIB = int(round(BW_1GBIT_BYTES/1024))
BW_RATE_MIN = 102400

# country codes where we can place onionperf client hosts
ONIONPERF_COUNTRY_CODES = ['HK', 'NL', 'AB', 'US']
TGEN_CLIENT_MIN_COUNT=100
TGEN_SERVER_MIN_COUNT=10
PRIVCOUNT_PERIODS_PER_DAY=144.0
TGEN_SERVER_PORT=80

TGENRC_SERVER_FILENAME="tgen-server.tgenrc.graphml"
TGENRC_PERFCLIENT_FILENAME="tgen-perf.tgenrc.graphml"
TGENRC_MARKOVCLIENT_DIRNAME="tgen-markov"
TGENRC_MARKOVCLIENT_FILENAME_FMT="{}.tgenrc.graphml"
TGENRC_FLOWMODEL_FILENAME_FMT="flowmodel.{}usec.graphml"

TMODEL_STREAMMODEL_FILENAME="tgen.tor-streammodel-ccs2018.graphml"
TMODEL_PACKETMODEL_FILENAME="tgen.tor-packetmodel-ccs2018.graphml"
TMODEL_TOPOLOGY_FILENAME="atlas-lossless.201801.shadow113.graphml.xml"

def get_host_rel_conf_path(rc_filename, rc_subdirname=None):
    if rc_subdirname == None:
        return f"../../../{CONFIG_DIRNAME}/{rc_filename}"
    else:
        return f"../../../{CONFIG_DIRNAME}/{rc_subdirname}/{rc_filename}"
