import os
import logging
import datetime
import subprocess

from tornettools.util import which, cmdsplit, open_writeable_file, load_json_data, dump_json_data, aka_int, tgen_stream_seconds_at_bytes

def parse_tgen_logs(args):
    tgentools_exe = which('tgentools')

    if tgentools_exe == None:
        logging.warning("Cannot find tgentools in your PATH. Is your python venv active? Do you have tgentools installed?")
        logging.warning("Unable to parse tgen simulation data.")
        return

    # tgentools supports a list of expressions that are used to search for oniontrace log filenames
    # the first -e expression matches the log file names for Shadow v2.x.x
    # and the second -e expression matches the log file names for Shadow v1.x.x
    #
    # Only parses "exit" perfclients for now.
    # TODO: also "hs" (onion service) perfclients.
    cmd_str = f"{tgentools_exe} parse -m {args.nprocesses} -e 'perfclient[0-9]+(exit)?\.tgen\.[0-9]+.stdout' -e 'stdout.*perfclient[0-9]+\.tgen\.[0-9]+.log' --complete shadow.data/hosts"
    cmd = cmdsplit(cmd_str)

    datestr = datetime.datetime.now().strftime("%Y-%m-%d.%H:%M:%S")

    with open_writeable_file(f"{args.prefix}/tgentools.parse.{datestr}.log") as outf:
        logging.info("Parsing tgen log data with tgentools now...")
        comproc = subprocess.run(cmd, cwd=args.prefix, stdout=outf, stderr=subprocess.STDOUT)
        logging.info(f"tgentools returned code {comproc.returncode}")

    return comproc.returncode == 0

def extract_tgen_plot_data(args):
    json_path = f"{args.prefix}/tgen.analysis.json"

    if not os.path.exists(json_path):
        json_path += ".xz"

    if not os.path.exists(json_path):
        logging.warning(f"Unable to find tgen analysis data at {json_path}.")
        return

    data = load_json_data(json_path)

    # parse performance stats only after the network has reached steady state
    startts, stopts = args.converge_time, -1 if args.run_time < 0 else args.converge_time + args.run_time

    __extract_round_trip_time(args, data, startts, stopts)
    __extract_download_time(args, data, startts, stopts)
    __extract_error_rate(args, data, startts, stopts)
    __extract_client_goodput(args, data, startts, stopts)
    __extract_client_goodput_5MiB(args, data, startts, stopts)

def __extract_round_trip_time(args, data, startts, stopts):
    rtt = __get_round_trip_time(data, startts, stopts)
    outpath = f"{args.prefix}/tornet.plot.data/round_trip_time.json"
    dump_json_data(rtt, outpath, compress=False)

def __extract_download_time(args, data, startts, stopts):
    key = "time_to_first_byte_recv"
    dt = __get_download_time(data, startts, stopts, key)
    outpath = f"{args.prefix}/tornet.plot.data/{key}.json"
    dump_json_data(dt, outpath, compress=False)

    key = "time_to_last_byte_recv"
    dt = __get_download_time(data, startts, stopts, key)
    outpath = f"{args.prefix}/tornet.plot.data/{key}.json"
    dump_json_data(dt, outpath, compress=False)

def __extract_error_rate(args, data, startts, stopts):
    errrate_per_client = __get_error_rate(data, startts, stopts)
    outpath = f"{args.prefix}/tornet.plot.data/error_rate.json"
    dump_json_data(errrate_per_client, outpath, compress=False)

def __extract_client_goodput(args, data, startts, stopts):
    # goodput between 500 kibibytes and 1 mebibyte. Old way of calcuting throughput.
    # https://metrics.torproject.org/reproducible-metrics.html#performance
    client_goodput = __get_client_goodput(
            data, startts, stopts,
            aka_int(512000, 500 * 2**10),
            aka_int(1048576, 2**20))
    outpath = f"{args.prefix}/tornet.plot.data/perfclient_goodput.json"
    dump_json_data(client_goodput, outpath, compress=False)

def __extract_client_goodput_5MiB(args, data, startts, stopts):
    # goodput of the 5th Mebibyte. metrics.torproject uses this as of ~ April 2021.
    # https://gitlab.torproject.org/tpo/network-health/metrics/statistics/-/issues/40005
    # https://gitlab.torproject.org/tpo/network-health/metrics/statistics/-/issues/40020
    # https://metrics.torproject.org/reproducible-metrics.html#performance
    client_goodput = __get_client_goodput(
            data, startts, stopts, 
            aka_int(4194304, 4 * 2**20),
            aka_int(5242880, 5 * 2**20))
    outpath = f"{args.prefix}/tornet.plot.data/perfclient_goodput_5MiB.json"
    dump_json_data(client_goodput, outpath, compress=False)

def __get_download_time(data, startts, stopts, bytekey):
    dt = {'ALL':[]}

    # download times can differ by microseconds in tgen
    resolution = 1.0/1000000.0

    if 'data' in data:
        for name in data['data']:
            if 'perfclient' not in name:
                continue
            db = data['data'][name]
            ss = db['tgen']['stream_summary']
            mybytes, mytime = 0, 0.0
            if bytekey in ss:
                for header in ss[bytekey]:
                    bytes = int(header)
                    for secstr in ss[bytekey][header]:
                        sec = int(secstr)-946684800
                        if sec >= startts and (stopts < 0 or sec < stopts):
                            #mydlcount += len(data['nodes'][name]['lastbyte'][header][secstr])
                            for dl in ss[bytekey][header][secstr]:
                                seconds = float(dl)
                                #item = [seconds, resolution]
                                item = seconds
                                dt['ALL'].append(item)
                                dt.setdefault(header, []).append(item)
    return dt

def __get_round_trip_time(data, startts, stopts):
    rtt = []

    # rtts can differ by microseconds in tgen
    resolution = 1.0/1000000.0

    if 'data' in data:
        for name in data['data']:
            if 'perfclient' not in name:
                continue

            db = data['data'][name]
            ss = db['tgen']['stream_summary']

            if 'round_trip_time' in ss:
                for secstr in ss['round_trip_time']:
                    sec = int(secstr)-946684800
                    if sec >= startts and (stopts < 0 or sec < stopts):
                        for val in ss['round_trip_time'][secstr]:
                            #item = [val, resolution]
                            item = val
                            rtt.append(item)

    return rtt

def __get_error_rate(data, startts, stopts):
    errors_per_client = {'ALL': []}

    if 'data' in data:
        for name in data['data']:
            if 'perfclient' not in name:
                continue
            db = data['data'][name]
            ss = db['tgen']['stream_summary']

            mydlcount = 0
            errtype_counts = {'ALL': 0}

            key = 'time_to_last_byte_recv'
            if key in ss:
                for header in ss[key]:
                    for secstr in ss[key][header]:
                        sec = int(secstr)-946684800
                        if sec >= startts and (stopts < 0 or sec < stopts):
                            mydlcount += len(ss[key][header][secstr])

            key = 'errors'
            if key in ss:
                for errtype in ss[key]:
                    for secstr in ss[key][errtype]:
                        sec = int(secstr)-946684800
                        if sec >= startts and (stopts < 0 or sec < stopts):
                            num_err = len(ss[key][errtype][secstr])
                            errtype_counts.setdefault(errtype, 0)
                            errtype_counts[errtype] += num_err
                            errtype_counts['ALL'] += num_err

            attempted_dl_count = mydlcount+errtype_counts['ALL']

            #logging.info("attempted {} downloads, {} completed, {} failed".format(attempted_dl_count, mydlcount, errtype_counts['ALL']))

            if attempted_dl_count > 0:
                errcount = float(errtype_counts['ALL'])
                dlcount = float(attempted_dl_count)

                error_rate = 100.0*errcount/dlcount
                resolution = 100.0/dlcount
                errors_per_client['ALL'].append([error_rate, resolution])

                for errtype in errtype_counts:
                    errcount = float(errtype_counts[errtype])
                    error_rate = 100.0*errcount/dlcount
                    resolution = 100.0/dlcount
                    errors_per_client.setdefault(errtype, []).append([error_rate, resolution])

    return errors_per_client

def __get_client_goodput(data, startts, stopts, start_bytes, end_bytes):
    goodput = []

    resolution = 0.0 # TODO: goodput would be in bits/second

    # example json format
    #['data']['perfclient1']['tgen']['streams']["blah:blah:localhost:etc"]['elapsed_seconds']['payload_bytes_recv']['512000'] = 3.4546

    if 'data' in data:
        for name in data['data']:
            if 'perfclient' not in name:
                continue
            db = data['data'][name]
            streams = db['tgen']['streams']

            for sid in streams:
                stream = streams[sid]
                start_time = tgen_stream_seconds_at_bytes(stream, start_bytes)
                end_time = tgen_stream_seconds_at_bytes(stream, end_bytes)
                if start_time is not None and end_time is not None and end_time > start_time:
                    bps = (end_bytes - start_bytes)  * 8.0 / (end_time - start_time)
                    # We ultimately want to graph Mbps, but for compatibility
                    # with old data sets, we record Mibi-bps. This is
                    # converted to Mbps in the `plot` step.
                    Mibps = bps / 2**20
                    goodput.append(Mibps)

    return goodput
