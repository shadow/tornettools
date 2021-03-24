import os
import logging
import datetime
import subprocess

from tornettools.util import which, cmdsplit, open_writeable_file, load_json_data, dump_json_data

def parse_tgen_logs(args):
    tgentools_exe = which('tgentools')

    if tgentools_exe == None:
        logging.warning("Cannot find tgentools in your PATH. Is your python venv active? Do you have tgentools installed?")
        logging.warning("Unable to parse tgen simulation data.")
        return

    cmd_str = f"{tgentools_exe} parse -m {args.nprocesses} -e 'perfclient[0-9]+\.tgen\.[0-9]+.stdout' --complete shadow.data/hosts"
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
    client_goodput = __get_client_goodput(data, startts, stopts)
    outpath = f"{args.prefix}/tornet.plot.data/perfclient_goodput.json"
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

def __get_client_goodput(data, startts, stopts):
    # Tor computs gput based on the time between the .5 MiB byte to the 1 MiB byte.
    # Ie to cut out circuit build and other startup costs.
    # https://metrics.torproject.org/reproducible-metrics.html#performance

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
                if "elapsed_seconds" in stream and \
                    "payload_bytes_recv" in stream['elapsed_seconds']:
                    bytes_db = stream['elapsed_seconds']['payload_bytes_recv']
                    if '512000' in bytes_db and '1048576' in bytes_db:
                        seconds = float(bytes_db['1048576']) - float(bytes_db['512000'])
                        bytes = 1048576 - 512000
                        mbit = bytes/1048576.0*8.0
                        mbit_per_second = mbit/seconds
                        goodput.append(mbit_per_second)

    return goodput
