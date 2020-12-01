import sys
import os
import logging
import datetime

from tornettools.util import which, open_file

def run(args):
    logging.info("Parsing simulation output from {}".format(args.prefix))
    __parse_tgen(args)
    __parse_oniontrace(args)

def __parse_tgen(args):
    tgentools_exe = which('tgentools')

    if tgentools_exe == None:
        logging.warning("Cannot find tgentools in your PATH. Is your python venv active? Do you have tgentools installed?")
        logging.warning("Unable to parse tgen simulation data.")
        return

    cmd_str = f"{tgentools_exe} parse -m {args.nprocesses} -e 'perfclient.*tgen.*\.log' shadow.data/hosts"
    cmd = shlex.split(cmd_str)

    datestr = datetime.now().strftime("%Y-%m-%d.%H:%M:%S")

    with open_file(f"{args.prefix}/tgentools.parse.{datestr}.log", False) as outf:
        comproc = subprocess.run(cmd, cwd=args.prefix, stdout=outf)
    logging.info(f"tgentools returned code {comproc.returncode}")


def __parse_oniontrace(args):
    otracetools_exe = which('oniontracetools')

    if otracetools_exe == None:
        logging.warning("Cannot find oniontracetools in your PATH. Is your python venv active? Do you have oniontracetools installed?")
        logging.warning("Unable to parse oniontrace simulation data.")
        return

    cmd_str = f"{otracetools_exe} parse -m {args.nprocesses} -e 'oniontrace.*\.log' shadow.data/hosts"
    cmd = shlex.split(cmd_str)

    datestr = datetime.now().strftime("%Y-%m-%d.%H:%M:%S")

    with open_file(f"{args.prefix}/oniontracetools.parse.{datestr}.log", False) as outf:
        comproc = subprocess.run(cmd, cwd=args.prefix, stdout=outf)
    logging.info(f"oniontracetools returned code {comproc.returncode}")
