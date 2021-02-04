import sys
import os
import logging

from itertools import cycle
import matplotlib.pyplot as pyplot
from matplotlib.ticker import FuncFormatter

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
    args.pdfpages = PdfPages(f"{args.prefix}/tornet.plot.pages.pdf")

    logging.info("Loading tornet resource usage data")
    tornet_dbs = __load_tornet_datasets(args, "resource_usage.json")
    __plot_memory_usage(args, tornet_dbs)
    __plot_run_time(args, tornet_dbs)

    logging.info("Loading Tor metrics data")
    torperf_dbs = __load_torperf_datasets(args.tor_metrics_path)

    logging.info("Loading tornet relay goodput data")
    tornet_dbs = __load_tornet_datasets(args, "relay_goodput.json")
    net_scale = __get_simulated_network_scale(args)
    logging.info("Plotting relay goodput")
    __plot_relay_goodput(args, torperf_dbs, tornet_dbs, net_scale)

    logging.info("Loading tornet circuit build time data")
    tornet_dbs = __load_tornet_datasets(args, "perfclient_circuit_build_time.json")
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

    logging.info("Loading tornet goodput data")
    tornet_dbs = __load_tornet_datasets(args, "perfclient_goodput.json")
    logging.info("Plotting client goodput")
    __plot_client_goodput(args, torperf_dbs, tornet_dbs)

    logging.info("Loading tornet transfer error rate data")
    tornet_dbs = __load_tornet_datasets(args, "error_rate.json")
    logging.info("Plotting transfer error rates")
    __plot_transfer_error_rates(args, torperf_dbs, tornet_dbs, "ALL")

    args.pdfpages.close()

def __plot_memory_usage(args, tornet_dbs):
    for tornet_db in tornet_dbs:
        xy = {}
        for i, d in enumerate(tornet_db['dataset']):
            if 'ram' not in d or 'gib_used_per_minute' not in d['ram']:
                continue
            timed = d['ram']['gib_used_per_minute']
            for sim_minute in timed:
                s = int(sim_minute)*60.0 # to seconds
                xy.setdefault(s, []).append(timed[sim_minute])
        tornet_db['data'] = xy

    dbs_to_plot = tornet_dbs

    __plot_timeseries_figure(args, dbs_to_plot, "ram",
        xtime=True,
        xlabel="Real Time",
        ylabel="RAM Used (GiB)")

def __plot_run_time(args, tornet_dbs):
    for tornet_db in tornet_dbs:
        xy = {}
        for i, d in enumerate(tornet_db['dataset']):
            if 'run_time' not in d or 'real_seconds_per_sim_second' not in d['run_time']:
                continue
            timed = d['run_time']['real_seconds_per_sim_second']
            for sim_secs in timed:
                s = int(round(float(sim_secs)))
                xy.setdefault(s, []).append(timed[sim_secs])
        tornet_db['data'] = xy

    dbs_to_plot = tornet_dbs

    __plot_timeseries_figure(args, dbs_to_plot, "run_time",
        ytime=True, xtime=True,
        xlabel="Simulation Time",
        ylabel="Real Time")

def __plot_relay_goodput(args, torperf_dbs, tornet_dbs, net_scale):
    # cache the corresponding data in the 'data' keyword for __plot_cdf_figure
    for tornet_db in tornet_dbs:
        tornet_db['data'] = []
        for i, d in enumerate(tornet_db['dataset']):
            l = [b/(1024**3)*8 for b in d.values()] # bytes to gbits
            tornet_db['data'].append(l)
    for torperf_db in torperf_dbs:
        gput = torperf_db['dataset']['relay_goodput']
        torperf_db['data'] = [[net_scale*gbits for gbits in gput.values()]]

    dbs_to_plot = torperf_dbs + tornet_dbs

    __plot_cdf_figure(args, dbs_to_plot, 'relay_goodput',
        xlabel="Sum of Relays' Goodput (Gbit/s)")

def __plot_circuit_build_time(args, torperf_dbs, tornet_dbs):
    # cache the corresponding data in the 'data' keyword for __plot_cdf_figure
    for tornet_db in tornet_dbs:
        tornet_db['data'] = tornet_db['dataset']
    for torperf_db in torperf_dbs:
        torperf_db['data'] = [torperf_db['dataset']['circuit_build_times']]

    dbs_to_plot = torperf_dbs + tornet_dbs

    __plot_cdf_figure(args, dbs_to_plot, 'circuit_build_time',
        yscale="taillog",
        xlabel="Circuit Build Time (s)")

def __plot_round_trip_time(args, torperf_dbs, tornet_dbs):
    # cache the corresponding data in the 'data' keyword for __plot_cdf_figure
    for tornet_db in tornet_dbs:
        tornet_db['data'] = tornet_db['dataset']
    for torperf_db in torperf_dbs:
        torperf_db['data'] = [torperf_db['dataset']['circuit_rtt']]

    dbs_to_plot = torperf_dbs + tornet_dbs

    __plot_cdf_figure(args, dbs_to_plot, 'round_trip_time',
        yscale="taillog",
        xlabel="Circuit Round Trip Time (s)")

def __plot_transfer_time(args, torperf_dbs, tornet_dbs, bytes_key):
    # cache the corresponding data in the 'data' keyword for __plot_cdf_figure
    for tornet_db in tornet_dbs:
        tornet_db['data'] = [tornet_db['dataset'][i][bytes_key] for i, _ in enumerate(tornet_db['dataset']) if bytes_key in tornet_db['dataset'][i]]
    for torperf_db in torperf_dbs:
        torperf_db['data'] = [torperf_db['dataset']['download_times'][bytes_key]]

    dbs_to_plot = torperf_dbs + tornet_dbs

    __plot_cdf_figure(args, dbs_to_plot, f"transfer_time_{bytes_key}",
        yscale="taillog",
        xlabel=f"Transfer Time (s): Bytes={bytes_key}")

def __plot_transfer_error_rates(args, torperf_dbs, tornet_dbs, error_key):
    # cache the corresponding data in the 'data' keyword for __plot_cdf_figure
    for tornet_db in tornet_dbs:
        tornet_db['data'] = [tornet_db['dataset'][i][error_key] for i, _ in enumerate(tornet_db['dataset']) if error_key in tornet_db['dataset'][i]]
    for torperf_db in torperf_dbs:
        err_rates = __compute_torperf_error_rates(torperf_db['dataset']['daily_counts'])
        torperf_db['data'] = [err_rates]

    dbs_to_plot = torperf_dbs + tornet_dbs

    __plot_cdf_figure(args, dbs_to_plot, f"transfer_error_rates_{error_key}",
        xlabel=f"Transfer Error Rate (\%): Type={error_key}")

def __plot_client_goodput(args, torperf_dbs, tornet_dbs):
    # Tor computes goodput based on the time between the .5 MiB byte to the 1 MiB
    # byte in order to cut out circuit build and other startup costs.
    # https://metrics.torproject.org/reproducible-metrics.html#performance

    # cache the corresponding data in the 'data' keyword for __plot_cdf_figure
    for tornet_db in tornet_dbs:
        tornet_db['data'] = tornet_db['dataset']
    for torperf_db in torperf_dbs:
        # convert tor's microseconds into seconds
        client_gput = [t/1000000.0 for t in torperf_db['dataset']["client_goodput"]]
        torperf_db['data'] = [client_gput]

    dbs_to_plot = torperf_dbs + tornet_dbs

    __plot_cdf_figure(args, dbs_to_plot, 'client_goodput',
        yscale="taillog",
        xlabel="Client Transfer Goodput (Mbit/s): 0.5 to 1 MiB")

def __plot_cdf_figure(args, dbs, filename, xscale=None, yscale=None, xlabel=None, ylabel="CDF"):
    color_cycle = cycle(DEFAULT_COLORS)
    linestyle_cycle = cycle(DEFAULT_LINESTYLES)

    f = pyplot.figure()
    lines, labels = [], []

    for db in dbs:
        if 'data' not in db or len(db['data']) < 1:
            continue
        elif len(db['data']) == 1:
            plot_func, d = draw_cdf, db['data'][0]
        else:
            plot_func, d = draw_cdf_ci, db['data']

        if len(d) < 1:
            continue

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

    # the plot will exit the visible space at the 99th percentile,
    # so make sure the x-axis is centered correctly
    # (this is usually only a problem if using the 'taillog' yscale)
    x_visible_max = None
    for db in dbs:
        if len(db['data']) >= 1 and len(db['data'][0]) >= 1:
            q = quantile(db['data'][0], 0.99)
            x_visible_max = q if x_visible_max == None else max(x_visible_max, q)
    if x_visible_max != None:
        pyplot.xlim(xmin=-m*x_visible_max, xmax=(m+1)*x_visible_max)

    __plot_finish(args, lines, labels, filename)

def __plot_timeseries_figure(args, dbs, filename, xtime=False, ytime=False, xlabel=None, ylabel=None):
    color_cycle = cycle(DEFAULT_COLORS)
    linestyle_cycle = cycle(DEFAULT_LINESTYLES)

    f = pyplot.figure()
    lines, labels = [], []

    for db in dbs:
        if 'data' not in db or len(db['data']) < 1:
            continue

        x = sorted(db['data'].keys())
        y_buckets = [db['data'][k] for k in x]

        if len(db['dataset']) > 1:
            plot_func = draw_line_ci
        else:
            plot_func = draw_line

        line = plot_func(pyplot, x, y_buckets,
            label=db['label'],
            color=db['color'] or next(color_cycle),
            linestyle=next(linestyle_cycle))

        lines.append(line)
        labels.append(db['label'])

    if xlabel != None:
        pyplot.xlabel(xlabel)
    if ylabel != None:
        pyplot.ylabel(ylabel)

    if xtime:
        f.axes[0].xaxis.set_major_formatter(FuncFormatter(__time_format_func))
        # this locates y-ticks at the hours
        #ax.yaxis.set_major_locator(matplotlib.ticker.MultipleLocator(base=3600))
        # rotate xlabels so they don't overlap
        pyplot.xticks(rotation=30)
    if ytime:
        f.axes[0].yaxis.set_major_formatter(FuncFormatter(__time_format_func))

    __plot_finish(args, lines, labels, filename)

def __plot_finish(args, lines, labels, filename):
    pyplot.tick_params(axis='both', which='major', labelsize=8)
    pyplot.tick_params(axis='both', which='minor', labelsize=5)
    pyplot.grid(True, axis='both', which='minor', color='0.1', linestyle=':', linewidth='0.5')
    pyplot.grid(True, axis='both', which='major', color='0.1', linestyle=':', linewidth='1.0')

    pyplot.legend(lines, labels, loc='best')
    pyplot.tight_layout(pad=0.3)
    pyplot.savefig(f"{args.prefix}/{filename}.{'png' if args.plot_pngs else 'pdf'}")
    args.pdfpages.savefig()

def __get_scale_suffix(scale):
    if scale == 'taillog':
        return " (tail log scale)"
    elif scale == 'log':
        return " (log scale)"
    else:
        return ""

def __time_format_func(x, pos):
    hours = int(x//3600)
    minutes = int((x%3600)//60)
    seconds = int(x%60)
    return "{:d}:{:02d}:{:02d}".format(hours, minutes, seconds)

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

def __get_simulated_network_scale(args):
    sim_info = __load_tornet_datasets(args, "simulation_info.json")

    net_scale = 0.0
    for db in sim_info:
        for i, d in enumerate(db['dataset']):
            if 'net_scale' in d:
                if net_scale == 0.0:
                    net_scale = float(d['net_scale'])
                    logging.info(f"Found simulated network scale {net_scale}")
                else:
                    if float(d['net_scale']) != net_scale:
                        logging.warning("Some of your tornet data is from networks of different scale")
                        logging.critical(f"Found network scales {net_scale} and {float(d['net_scale'])} and they don't match")

    return net_scale

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

        err_rates.append((timeouts+failures)/float(total)*100.0)
    return err_rates
