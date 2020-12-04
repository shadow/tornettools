import sys
import os
import logging

from itertools import cycle
import matplotlib.pyplot as pyplot

from tornettools.util import load_json_data, find_matching_files_in_dir

from tornettools.plot_common import *
from tornettools.plot_tgen import plot_tgen
from tornettools.plot_oniontrace import plot_oniontrace

def run(args):
    logging.info("Plotting simulation results now")
    set_plot_options()

    logging.info("Plotting tornet comparisons")
    __plot_tornet(args)

    if args.plot_all:
        logging.info("Plotting all individual simulation results is requested")

        logging.info("Attempting to plot individual tgen results")
        plot_tgen(args)

        logging.info("Attempting to plot individual oniontrace results")
        plot_oniontrace(args)

def __plot_tornet(args):
    torperf_dbs = __load_torperf_datasets(args.torperf)

    __plot_rtt(args, torperf_dbs)

def __plot_rtt(args, torperf_dbs):
    # get the tornet rtts
    tornet_dbs = __load_tornet_datasets(args, f"round_trip_time.json")

    # cache the torperf rtts in the 'data' keyword
    for torperf_db in torperf_dbs:
        torperf_db['data'] = [torperf_db['dataset']['circuit_rtt']]

    dbs_to_plot = torperf_dbs + tornet_dbs
    filename = f"{args.prefix}/round_trip_time.pdf"

    __plot_cdf_figure(args, dbs_to_plot, filename,
        yscale="taillog",
        xlabel="Circuit Round Trip Time (s)",
        ylabel="CDF")

def __plot_cdf_figure(args, dbs, filename, xscale=None, yscale=None, xlabel=None, ylabel=None):
    color_cycle = cycle(DEFAULT_COLORS)
    linestyle_cycle = cycle(DEFAULT_LINESTYLES)

    f = pyplot.figure()
    lines, labels = [], []

    for db in dbs:
        if len(db['data']) == 1:
            plot_func, d = draw_cdf, db['data'][0]
        else:
            plot_func, d = draw_cdf_ci, db['data']

        line = plot_func(pyplot, d,
            label=db['label'],
            color=db['color'] or next(color_cycle),
            linestyle=next(linestyle_cycle))

        lines.append(line)
        labels.append(db['label'])

    if xscale is not None:
        pyplot.xscale(xscale)
        if xlabel != None:
            xlabel += __get_scale_suffix(xscale)
    if yscale != None:
        pyplot.yscale(yscale)
        if ylabel != None:
            ylabel += __get_scale_suffix(yscale)
    if xlabel != None:
        pyplot.xlabel(xlabel)
    if ylabel != None:
        pyplot.ylabel(ylabel)

    m = 0.025
    pyplot.margins(m)
    x_visible_max = max([quantile(db['data'][0], 0.99) for db in dbs])
    pyplot.xlim(xmin=-m*x_visible_max, xmax=(m+1)*x_visible_max)

    pyplot.tick_params(axis='both', which='major', labelsize=8)
    pyplot.tick_params(axis='both', which='minor', labelsize=5)
    pyplot.grid(True, axis='both', which='minor', color='0.1', linestyle=':', linewidth='0.5')
    pyplot.grid(True, axis='both', which='major', color='0.1', linestyle=':', linewidth='1.0')

    pyplot.legend(lines, labels, loc='best')
    pyplot.tight_layout(pad=0.3)
    pyplot.savefig(filename)

def __get_scale_suffix(scale):
    if scale == 'taillog':
        return " (tail log scale)"
    elif scale == 'log':
        return " (log scale)"
    else:
        return ""

def __load_tornet_datasets(args, filename):
    tornet_dbs = []

    print(args.labels)
    label_cycle = cycle(args.labels) if args.labels != None else None
    color_cycle = cycle(args.colors) if args.colors != None else None

    if args.tornet_collection_path != None:
        for collection_dir in args.tornet_collection_path:
            tornet_db = {
                'data': [load_json_data(p) for p in find_matching_files_in_dir(collection_dir, filename)],
                'label': next(label_cycle) if label_cycle != None else os.path.basename(collection_dir),
                'color': next(color_cycle) if color_cycle != None else None,
            }
            tornet_dbs.append(tornet_db)

    return tornet_dbs

def __load_torperf_datasets(torperf_argset):
    torperf_dbs = []

    if torperf_argset != None:
        for torperf_args in torperf_argset:
            torperf_db = {
                'dataset': load_json_data(torperf_args[0]) if torperf_args[0] != None else None,
                'label': torperf_args[1] if torperf_args[1] != None else "Public Tor",
                'color': torperf_args[2],
            }
            torperf_dbs.append(torperf_db)

    return torperf_dbs
