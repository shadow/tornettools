import sys
import os
import json
import lzma
import logging

from tornettools.util import dump_json_data, open_readable_file, aka_int, tgen_stream_seconds_at_bytes

# This code parses onionperf metrics data.
# The output is in a format that the `plot` command can use to compare
# shadow results to Tor metrics results.
# see https://metrics.torproject.org/reproducible-metrics.html#performance

def run(args):
    db = {"circuit_rtt": [], "client_goodput": [], "client_goodput_5MiB": [],
        "circuit_build_times": [], "download_times": {}, "daily_counts": {},
        "relay_goodput": {}}

    if args.bandwidth_data_path != None:
        logging.info(f"Parsing bandwidth data stored in '{args.bandwidth_data_path}'")
        db['relay_goodput'] = __parse_bandwidth_data(args.bandwidth_data_path)
        logging.info("Finished parsing bandwidth data")

    if args.onionperf_data_path != None:
        logging.info(f"Extracting onionperf data stored in '{args.onionperf_data_path}'")
        __extract_onionperf_data(args, db)
        logging.info("Finished extracting onionperf data")

    # format we want for filename: tor_metrics_2020-01-01--2020-01-31.json
    days = []
    days.extend(db['daily_counts'].keys())
    days.extend(db['relay_goodput'].keys())
    days.sort()

    out_path = f"{args.prefix}/tor_metrics_{days[0]}--{days[-1]}.json"
    logging.info(f"Saving parsed Tor metrics data to {out_path}")
    dump_json_data(db, out_path, compress=False)

def __parse_bandwidth_data(bw_data_path):
    bw = {}
    with open_readable_file(bw_data_path) as inf:
        for line in inf:
            if '20' == line[0:2]:
                parts = line.strip().split(',')
                day, relay_bw_hist = parts[0], parts[2]
                if len(relay_bw_hist) > 0:
                    bw[day] = float(relay_bw_hist)
    return bw

def __extract_onionperf_data(args, db):
    # parse the files
    for root, dirs, files in os.walk(args.onionperf_data_path):
        for file in files:
            if 'onionperf' not in file:
                continue

            fullpath = os.path.join(root, file)

            parts = os.path.basename(fullpath).split('.')
            day = parts[0]

            logging.info("Processing onionperf file: '{}'".format(fullpath))

            with open_readable_file(fullpath) as fin:
                data = json.load(fin)
                __handle_json_data(db, data, day)

    logging.info(f"We processed {len(db['circuit_rtt'])} downloads")

def __handle_json_data(db, data, day):
    if 'data' in data:
        for name in data['data']:
            if 'tgen' in data['data'][name]:
                if 'streams' in data['data'][name]['tgen']:
                    for stream_id in data['data'][name]['tgen']['streams']:
                        stream = data['data'][name]['tgen']['streams'][stream_id]
                        __handle_stream(db, stream, day)
            if 'tor' in data['data'][name]:
                if 'circuits' in data['data'][name]['tor']:
                    for circ_id in data['data'][name]['tor']['circuits']:
                        circuit = data['data'][name]['tor']['circuits'][circ_id]
                        __handle_circuit(db, circuit)

def __handle_circuit(db, circuit):
    if 'buildtime_seconds' in circuit:
        cbt = float(circuit['buildtime_seconds'])
        db['circuit_build_times'].append(cbt)

def __handle_stream(db, stream, day):
    # filter out onion service circuit downloads for now
    if 'transport_info' in stream:
        if 'remote' in stream['transport_info']:
            if 'onion' in stream['transport_info']['remote']:
                return

    transfer_size_actual = int(stream['byte_info']['payload-bytes-recv'])
    transfer_size_target = int(stream['stream_info']['recvsize'])
    timeout_limit = __get_timeout_limit(transfer_size_target)

    cmd = int(stream['time_info']['usecs-to-command'])
    rsp = int(stream['time_info']['usecs-to-response'])
    lb = int(stream['time_info']['usecs-to-last-byte-recv'])

    ttlb = (lb - cmd) / 1000000.0 # usecs to seconds

    # count number of attemps and timeouts/failures
    db["daily_counts"].setdefault(day, {"requests": 0, "timeouts": 0, "failures": 0})
    db["daily_counts"][day]["requests"] += 1
    if stream['is_error']:
        se = stream['stream_info']['error']
        if se.upper() == "TIMEOUT" or se.upper() == "STALLOUT":
            db["daily_counts"][day]["timeouts"] += 1
        else:
            db["daily_counts"][day]["failures"] += 1
        return
    if lb > 0 and cmd > 0 and ttlb > timeout_limit:
        db["daily_counts"][day]["timeouts"] += 1
        return
    if transfer_size_actual < transfer_size_target:
        db["daily_counts"][day]["failures"] += 1
        return

    # download was successful
    assert stream['is_success']

    # circuit rtt
    if rsp > 0 and cmd > 0:
        rtt = (rsp - cmd) / 1000000.0 # usecs to seconds
        db['circuit_rtt'].append(rtt)

    # download times, client download 'goodput' and client download 'goodput' for
    # the last MiB of 5MiB downloads.
    # Tor computs goodput based on the time between the .5 MiB byte to the 1 MiB byte.
    # Ie to cut out circuit build and other startup costs.
    # https://metrics.torproject.org/reproducible-metrics.html#performance
    #
    # For 5 MiB downloads we extract the time (in seconds) elapsed between
    # receiving the 4MiB byte and 5MiB byte, which is a total amount of 1 MiB  or
    # 8 Mib.

    if 'elapsed_seconds' in stream and 'payload_bytes_recv' in stream['elapsed_seconds']:
        # download times
        for (transfer_size, time_to_size) in stream['elapsed_seconds']['payload_bytes_recv'].items():
            if time_to_size > 0 and cmd > 0:
                transfer_time_secs = time_to_size - (cmd / 1e6) # usecs to seconds
                __store_transfer_time(db, transfer_size, transfer_time_secs)

        # goodput between 500 kibibytes and 1 mebibyte. Old way of calcuting throughput.
        # https://metrics.torproject.org/reproducible-metrics.html#performance
        goodput = __goodput_bps(
                stream, aka_int(512000, 500 * 2**10), aka_int(1048576, 2**20))
        if goodput is not None:
            db['client_goodput'].append(goodput)

        # goodput of the 5th Mebibyte. metrics.torproject uses this as of ~ April 2021.
        # https://gitlab.torproject.org/tpo/network-health/metrics/statistics/-/issues/40005
        # https://gitlab.torproject.org/tpo/network-health/metrics/statistics/-/issues/40020
        # https://metrics.torproject.org/reproducible-metrics.html#performance
        goodput = __goodput_bps(
                stream, aka_int(4194304, 4 * 2**20), aka_int(5242880, 5 * 2**20))
        if goodput is not None:
            db['client_goodput_5MiB'].append(goodput)

    elif lb > 0 and cmd > 0:
        __store_transfer_time(db, transfer_size_target, ttlb)

def __goodput_bps(stream, start_bytes, end_bytes):
    start_time = tgen_stream_seconds_at_bytes(stream, start_bytes)
    if start_time is None:
        return None
    end_time = tgen_stream_seconds_at_bytes(stream, end_bytes)
    if end_time is None or end_time <= start_time:
        return None
    return (end_bytes - start_bytes) * 8.0 / (end_time - start_time)

def __store_transfer_time(db, transfer_size, transfer_time):
    db['download_times'].setdefault('ALL', [])
    db['download_times']['ALL'].append(transfer_time)
    db['download_times'].setdefault(str(transfer_size), [])
    db['download_times'][str(transfer_size)].append(transfer_time)

def __get_timeout_limit(num_bytes):
    # we compute timeouts based on our tgen configured timeout times
    # so that we can keep shadow and tor metrics consistent
    # timeouts are in seconds
    if num_bytes == 51200:
        return 15.0
    elif num_bytes == 1048576:
        return 60.0
    elif num_bytes == 5242880:
        return 120.0
    else:
        return 3600.0
