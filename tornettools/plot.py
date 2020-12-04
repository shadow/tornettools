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

    logging.info(f"Done plotting! PDF files are saved to {args.prefix}")

def __plot_tornet(args):
    logging.info("Loading TorPerf data")
    torperf_dbs = __load_torperf_datasets(args.torperf)

    args.pdfpages = PdfPages(f"{args.prefix}/tornet.plot.pages.pdf")

    logging.info("Loading tornet circuit build time data")
    tornet_dbs = __load_tornet_datasets(args, "oniontrace_perfclient_cbt.json")
    logging.info("Plotting circuit build times")
    __plot_circuit_build_time(args, torperf_dbs, tornet_dbs)

    logging.info("Loading tornet round trip time data")
    tornet_dbs = __load_tornet_datasets(args, "round_trip_time.json")
    logging.info("Plotting round trip times")
    __plot_round_trip_time(args, torperf_dbs, tornet_dbs)

    logging.info("Loading tornet transfer time data")
    tornet_dbs = __load_tornet_datasets(args, "time_to_last_byte_recv.json")
    logging.info("Plotting transfer times")
    __plot_transfer_time(args, torperf_dbs, tornet_dbs, "51200")
    __plot_transfer_time(args, torperf_dbs, tornet_dbs, "1048576")
    __plot_transfer_time(args, torperf_dbs, tornet_dbs, "5242880")

    logging.info("Loading tornet transfer error rate data")
    tornet_dbs = __load_tornet_datasets(args, "error_rate.json")
    logging.info("Plotting transfer error rates")
    __plot_transfer_error_rates(args, torperf_dbs, tornet_dbs, "ALL")

    args.pdfpages.close()

def __plot_circuit_build_time(args, torperf_dbs, tornet_dbs):
    # cache the corresponding data in the 'data' keyword for __plot_cdf_figure
    for tornet_db in tornet_dbs:
        tornet_db['data'] = tornet_db['dataset']
    for torperf_db in torperf_dbs:
        torperf_db['data'] = [torperf_db['dataset']['circuit_build_times']]

    dbs_to_plot = torperf_dbs + tornet_dbs
    filename = f"{args.prefix}/circuit_build_time.pdf"

    __plot_cdf_figure(args, dbs_to_plot, filename,
        yscale="taillog",
        xlabel="Circuit Build Time (s)")

def __plot_round_trip_time(args, torperf_dbs, tornet_dbs):
    # cache the corresponding data in the 'data' keyword for __plot_cdf_figure
    for tornet_db in tornet_dbs:
        tornet_db['data'] = tornet_db['dataset']
    for torperf_db in torperf_dbs:
        torperf_db['data'] = [torperf_db['dataset']['circuit_rtt']]

    dbs_to_plot = torperf_dbs + tornet_dbs
    filename = f"{args.prefix}/round_trip_time.pdf"

    __plot_cdf_figure(args, dbs_to_plot, filename,
        yscale="taillog",
        xlabel="Circuit Round Trip Time (s)")

def __plot_transfer_time(args, torperf_dbs, tornet_dbs, bytes_key):
    # cache the corresponding data in the 'data' keyword for __plot_cdf_figure
    for tornet_db in tornet_dbs:
        tornet_db['data'] = [tornet_db['dataset'][k][bytes_key] for k in range(len(tornet_db['dataset']))]
    for torperf_db in torperf_dbs:
        torperf_db['data'] = [torperf_db['dataset']['download_times'][bytes_key]]

    dbs_to_plot = torperf_dbs + tornet_dbs
    filename = f"{args.prefix}/transfer_time_{bytes_key}.pdf"

    __plot_cdf_figure(args, dbs_to_plot, filename,
        yscale="taillog",
        xlabel=f"Transfer Time (s): Bytes={bytes_key}")

def __plot_transfer_error_rates(args, torperf_dbs, tornet_dbs, error_key):
    # cache the corresponding data in the 'data' keyword for __plot_cdf_figure
    for tornet_db in tornet_dbs:
        tornet_db['data'] = [tornet_db['dataset'][k][error_key] for k in range(len(tornet_db['dataset']))]
    for torperf_db in torperf_dbs:
        err_rates = __compute_torperf_error_rates(torperf_db['dataset']['daily_counts'])
        torperf_db['data'] = [err_rates]

    dbs_to_plot = torperf_dbs + tornet_dbs
    filename = f"{args.prefix}/transfer_error_rates_{error_key}.pdf"

    __plot_cdf_figure(args, dbs_to_plot, filename,
        xlabel=f"Transfer Error Rate (\%): Type={error_key}")

def __plot_cdf_figure(args, dbs, filename, xscale=None, yscale=None, xlabel=None, ylabel="CDF"):
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
    args.pdfpages.savefig()

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
                'dataset': [load_json_data(p) for p in find_matching_files_in_dir(collection_dir, filename)],
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

def __compute_torperf_error_rates(daily_counts):
    err_rates = []
    for day in daily_counts:
        year = int(day.split('-')[0])
        month = int(day.split('-')[1])

        total = int(daily_counts[day]['requests'])
        if total <= 0:
            continue

        timeouts = int(daily_counts[day]['timeouts'])
        failures = int(daily_counts[day]['failures'])

        # the hong kong onionperf infrastucture is unreliable
        # https://metrics.torproject.org/torperf-failures.html?start=2019-06-01&end=2019-08-31&server=public
        if timeouts > 100 and year == 2019 and month in [6, 7, 8]:
            continue
        if timeouts > 100 and year == 2018 and month in [1, 5, 6, 7, 12]:
            continue

        err_rates.append((timeouts+failures)/float(total)*100.0)
    return err_rates
