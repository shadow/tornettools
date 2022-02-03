# a relay must have been running longer than this to be considered
RUN_FREQ_THRESH=0.01

# the bootstrap length should be greater than 60 seconds
BOOTSTRAP_LENGTH_SECONDS=300
SIMULATION_LENGTH_SECONDS=3600

SHADOW_DATA_PATH="shadow.data"
SHADOW_TEMPLATE_PATH="{}.template".format(SHADOW_DATA_PATH)
CONFIG_DIRNAME="conf"
SHADOW_INSTALL_PREFIX="~/.local"
SHADOW_HOSTS_PATH="hosts"
SHADOW_CONFIG_FILENAME="shadow.config.yaml"

RESOLV_FILENAME="shadowresolv.conf"
BW_AUTHORITY_NAME="bwauthority"

TORRC_HOST_FILENAME="torrc"
TORRC_DEFAULTS_HOST_FILENAME="torrc-defaults"

TORRC_COMMON_FILENAME="tor.common.torrc"
TORRC_RELAY_FILENAME="tor.relay.torrc"
TORRC_RELAY_AUTHORITY_FILENAME="tor.relay.authority.torrc"
TORRC_RELAY_EXITONLY_FILENAME="tor.relay.exitonly.torrc"
TORRC_RELAY_EXITGUARD_FILENAME="tor.relay.exitguard.torrc"
TORRC_RELAY_GUARDONLY_FILENAME="tor.relay.guardonly.torrc"
TORRC_RELAY_OTHER_FILENAME="tor.relay.other.torrc"
TORRC_CLIENT_FILENAME="tor.client.torrc"
TORRC_CLIENT_MARKOV_FILENAME="tor.client.markov.torrc"
TORRC_CLIENT_PERF_FILENAME="tor.client.perf.torrc"
TORRC_ONIONSERVICE_FILENAME="tor.onionservice.torrc"

TOR_SOCKS_PORT=9050
TOR_CONTROL_PORT=9051
TOR_OR_PORT=9001
TOR_DIR_PORT=8080
TOR_GUARD_MIN_CONSBW=2000
TOR_ONIONSERVICE_DIR="hs"

# country codes where we can place directory authority tor hosts
DIRAUTH_COUNTRY_CODES=["US", "DE", "NL", "FR", "SE"]

# this number of data equals 1 MBit
BW_1MBIT_BYTES = int(round(1000*1000/8))
BW_1MBIT_KIB = int(round(BW_1MBIT_BYTES/1024))
BW_1MBIT_KBIT = 1000
# this number of data equals 1 GBit
BW_1GBIT_BYTES = int(round(1000*1000*1000/8))
BW_1GBIT_KIB = int(round(BW_1GBIT_BYTES/1024))
BW_1GBIT_KBIT = 1000*1000
BW_RATE_MIN = 102400

# country codes where we can place onionperf client hosts
ONIONPERF_COUNTRY_CODES = ['HK', 'NL', 'AB', 'US']
# Minimum tgen count for each tgen type (exit or onion)
TGEN_CLIENT_MIN_COUNT=100
TGEN_SERVER_MIN_COUNT=10
PRIVCOUNT_PERIODS_PER_DAY=144.0
TGEN_SERVER_PORT=80
TGEN_ONIONSERVICE_PORT=8080

TGENRC_SERVER_FILENAME="tgen-server.tgenrc.graphml"
TGENRC_PERFCLIENT_EXIT_FILENAME="tgen-perf-exit.tgenrc.graphml"
TGENRC_PERFCLIENT_HS_FILENAME="tgen-perf-hs.tgenrc.graphml"
TGENRC_MARKOVCLIENT_FILENAME="tgenrc.graphml"
TGENRC_FLOWMODEL_FILENAME_FMT="tgen.tor-flowmodel-{}usec.graphml"

TMODEL_STREAMMODEL_FILENAME="tgen.tor-streammodel-ccs2018.graphml"
TMODEL_PACKETMODEL_FILENAME="tgen.tor-packetmodel-ccs2018.graphml"
TMODEL_TOPOLOGY_FILENAME="atlas_v201801.shadow_v2.gml"

def get_host_rel_conf_path(rc_filename, rc_subdirname=None):
    if rc_subdirname == None:
        return f"../../../{CONFIG_DIRNAME}/{rc_filename}"
    else:
        return f"../../../{CONFIG_DIRNAME}/{rc_subdirname}/{rc_filename}"
