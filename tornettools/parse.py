import logging

from tornettools.parse_oniontrace import *
from tornettools.parse_tgen import *
from tornettools.parse_rusage import *

def run(args):
    logging.info("Parsing simulation output from {}".format(args.prefix))

    logging.info("Parsing tgen logs.")
    if parse_tgen_logs(args):
        logging.info("Extracting tgen plot data.")
        extract_tgen_plot_data(args)
    else:
        logging.warning("Parsing tgen logs failed, so we cannot extract tgen plot data.")

    logging.info("Parsing oniontrace logs.")
    if parse_oniontrace_logs(args):
        logging.info("Extracting oniontrace plot data.")
        extract_oniontrace_plot_data(args)
    else:
        logging.warning("Parsing oniontrace logs failed, so we cannot extract oniontrace plot data.")

    logging.info("Parsing resource usage logs.")
    if parse_resource_usage_logs(args):
        logging.info("Extracting resource usage plot data.")
        extract_resource_usage_plot_data(args)
    else:
        logging.warning("Parsing resource usage logs failed, so we cannot extract resource usage plot data.")

    logging.info("Done parsing!")
