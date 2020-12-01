import sys
import os
import logging

def run(args):
    logging.info("Ran plot")

    # python ${SCRIPTS}/plot-shadow.py -d . test
    # tgentools plot -e "perfclient" -p "perf" -b -d /storage/rjansen/model/201901/tor/torperf.analysis.json.xz "Tor" -d tgen.analysis.json.xz "ShadowTor"
    # tgentools plot -e "client" -p "clients" -d tgen.analysis.json.xz "ShadowTor"
    # tgentools plot -e "server" -p "servers" -d tgen.analysis.json.xz "ShadowTor"
    #
    # oniontracetools plot -e "relay|4uthority" -p "relays" -d oniontrace.analysis.json.xz "ShadowTor"
    # oniontracetools plot -e "client" -p "clients" -d oniontrace.analysis.json.xz "ShadowTor"
