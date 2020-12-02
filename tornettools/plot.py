import sys
import os
import logging

from tornettools.plot_tgen import plot_tgen
from tornettools.plot_oniontrace import plot_oniontrace

def run(args):
    logging.info("Plotting simulation results now")

    if args.plot_all:
        logging.info("Plotting all individual simulation results is requested")

        logging.info("Attempting to plot individual tgen results")
        plot_tgen(args)

        logging.info("Attempting to plot individual oniontrace results")
        plot_oniontrace(args)

    logging.info("Plotting tornet comparisons")
