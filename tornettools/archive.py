import sys
import os
import logging

def run(args):
    logging.info("Ran archive")

    # tar cf - hosts | xz -T 0 > hosts.tar.xz
    # rm -rf hosts
    # mv ../shadow.log* .
    #
    # cd ..
    #
    # xz shadow.config.xml
    # tar caf conf.tar.xz conf
    # rm -rf conf
    #
    # tar caf shadow.data.template.tar.xz shadow.data.template
    # rm -rf shadow.data.template
    #
    # xz -T 0 -e -9 free.log
    # xz -T 0 -e -9 dstat.log
    # mv free.log.xz dstat.log.xz shadow.data/.
