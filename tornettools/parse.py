import sys
import os
import logging

def run(args):
    logging.info("Parsing simulation output from {}".format(args.tornet_config_path))

    # xzcat shadow.log.xz | pypy ${SCRIPTS}/parse-shadow.py -m 0 -
    # tgentools parse -m 0 -p analysis shadow.data/hosts
    # oniontracetools parse -m 0 -p analysis shadow.data/hosts -e ".*oniontrace\.1001\.log"
