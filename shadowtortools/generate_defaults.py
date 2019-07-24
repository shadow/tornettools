# the fraction of consensuses a relay needs a position flag to be counted for that position
POS_FLAG_THRESH=0.90
# a relay must have been running longer than this to be considered
RUN_FREQ_THRESH=0.01

SHADOW_DATA_PATH="shadow.data"
SHADOW_TEMPLATE_PATH="{}.template".format(SHADOW_DATA_PATH)
CONFIG_DIRPATH="conf"
SHADOW_INSTALL_PREFIX="~/.shadow"
SHADOW_HOSTS_PATH="hosts"
SHADOW_CONFIG_FILENAME="shadow.config.xml"

RESOLV_FILENAME="shadowresolv.conf"
BW_AUTHORITY_NAME="bwauthority"

TORRC_COMMON_FILENAME="tor.common.torrc"
TORRC_AUTHORITY_FILENAME="tor.authority.torrc"
TORRC_EXITRELAY_FILENAME="tor.exitrelay.torrc"
TORRC_NONEXITRELAY_FILENAME="tor.nonexitrelay.torrc"
TORRC_MARKOVCLIENT_FILENAME="tor.markovclient.torrc"
TORRC_PERFCLIENT_FILENAME="tor.perfclient.torrc"

DIRAUTH_GEOCODES=["US", "DE", "NL", "FR", "SE"]
DEFAULT_TOR_ARGS = "--Address {0} --Nickname {0} --DataDirectory "+SHADOW_DATA_PATH+"/"+SHADOW_HOSTS_PATH+"/{0} --GeoIPFile "+SHADOW_INSTALL_PREFIX+"/share/geoip --defaults-torrc "+CONFIG_DIRPATH+"/"+TORRC_COMMON_FILENAME+" -f {1}"

# this number of data equals 1 GBit
BW_1GBIT_BYTES = int(round(1000*1000*1000/8))
BW_1GBIT_KIB = int(round(BW_1GBIT_BYTES/1024))
BW_RATE_MIN = 102400
