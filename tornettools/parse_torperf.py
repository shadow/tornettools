import sys
import os
import json
import lzma
import logging

from tornettools.util import dump_json_data

# This code parses torperf metrics data.
# The output is in a format that the `plot` command can use to compare
# shadow results to Tor metrics results.
# see https://metrics.torproject.org/reproducible-metrics.html#performance

def run(args):
    db = {"circuit_rtt": [], "client_goodput": [], "circuit_build_times": [],
        "download_times": {}, "daily_counts": {}, "relay_goodput": {}}

    if args.torperf_data_path != None:
        logging.info(f"Parsing torperf data stored in '{args.torperf_data_path}'")
        __parse_torperf_data(args, db)
        logging.info("Finished parsing torperf data")

    if args.bandwidth_data_path != None:
        logging.info(f"Parsing bandwidth data stored in '{args.bandwidth_data_path}'")
        __parse_bandwidth_data(args, db)
        logging.info("Finished parsing bandwidth data")

    # format we want for filename: tor_metrics_2020-01-01--2020-01-31.json
    days = []
    days.extend(db['daily_counts'].keys())
    days.extend(db['relay_goodput'].keys())
    days.sort()

    out_path = f"{args.prefix}/tor_metrics_{days[0]}--{days[-1]}.json"
    logging.info(f"Saving parsed Tor metrics data to {out_path}")
    dump_json_data(db, out_path, compress=False)

def __parse_bandwidth_data(args, db):
    with open(args.bandwidth_data_path, 'r') as inf:
        for line in inf:
            if '20' == line[0:2]:
                parts = line.strip().split(',')
                day, relay_bw_hist = parts[0], parts[2]
                if len(relay_bw_hist) > 0:
                    db["relay_goodput"][day] = float(relay_bw_hist)

def __parse_torperf_data(args, db):
    # parse the files
    for root, dirs, files in os.walk(args.torperf_data_path):
        for file in files:
            fullpath = os.path.join(root, file)

            # 51200, 1048576, 5242880
            name_parts = os.path.basename(fullpath).split('-')
            num_bytes = int(name_parts[2])
            day = f"{'-'.join(name_parts[3:]).split('.')[0]}"

            db["download_times"].setdefault(num_bytes, [])
            db["daily_counts"].setdefault(day, {"requests": 0, "timeouts": 0, "failures": 0})

            logging.info("Processing TorPerf file: '{}'".format(fullpath))

            with open(fullpath, 'r') as f:
                for line in f:
                    if '=' not in line:
                        continue
                    __handle_line(db, line, num_bytes, day)

    logging.info(f"We processed {len(db['circuit_rtt'])} downloads")

def __handle_line(db, line, num_bytes, day):
    d = __parse_line(line)

    # skip onion downloads
    if 'ENDPOINTREMOTE' in d and '.onion' in d['ENDPOINTREMOTE']:
        return

    start = float(d["START"])
    complete = float(d["DATACOMPLETE"])

    if int(d["DIDTIMEOUT"]) == 1 or complete <= start:
        db["daily_counts"][day]["requests"] += 1
        db["daily_counts"][day]["timeouts"] += 1
        return

    # we compute timeouts based on our tgen configured timeout times
    dl_50k_timeout_secs = 15.0
    dl_1m_timeout_secs = 60.0
    dl_5m_timeout_secs = 120.0

    if num_bytes == 51200:
        dl_50k = complete-start
        __count_dl(db, d, day, num_bytes, dl_50k, dl_50k_timeout_secs)
    elif num_bytes == 1048576:
        #dl_50k = float(d["PARTIAL51200"])
        #__count_dl(db, d, day, 51200, dl_50k, dl_50k_timeout_secs)
        dl_1m = complete-start
        __count_dl(db, d, day, num_bytes, dl_1m, dl_1m_timeout_secs)
    elif num_bytes == 5242880:
        #dl_50k = float(d["PARTIAL51200"])
        #__count_dl(db, d, day, 51200, dl_50k, dl_50k_timeout_secs)
        #dl_1m = float(d["PARTIAL1048576"])
        #__count_dl(db, d, day, 1048576, dl_1m, dl_1m_timeout_secs)
        dl_5m = complete-start
        __count_dl(db, d, day, num_bytes, dl_5m, dl_5m_timeout_secs)


def __count_dl(db, d, day, num_bytes, dl_time, timeout_limit):
    # circuit build times for all downloads even if they failed
    if 'BUILDTIMES' in d:
        cbt = d["BUILDTIMES"].split(',')
        cbt_hop1 = float(cbt[0])
        cbt_hop2 = float(cbt[1]) - cbt_hop1
        cbt_hop3 = float(cbt[2]) - cbt_hop1 - cbt_hop2
        cbt_total = float(cbt[2])
        if cbt_total > 0:
            db["circuit_build_times"].append(cbt_total)

    # counts
    db["daily_counts"][day]["requests"] += 1

    if dl_time > timeout_limit:
        db["daily_counts"][day]["timeouts"] += 1
        return
    elif int(d["READBYTES"]) < int(d["FILESIZE"]):
        db["daily_counts"][day]["failures"] += 1
        return

    # download was successful

    # download times
    db['download_times'][num_bytes].append(dl_time)

    # circuit rtt
    req = float(d["DATAREQUEST"])
    resp = float(d["DATARESPONSE"])
    if req > 0 and resp > 0:
        db['circuit_rtt'].append(resp - req)

    # throughput
    if num_bytes == 1048576 or num_bytes == 5242880:
        start = float(d["DATAPERC50"]) if num_bytes == 1048576 else float(d["DATAPERC10"])
        end = float(d["DATAPERC100"]) if num_bytes == 1048576 else float(d["DATAPERC20"])
        if start > 0 and end > 0 and end > start:
            tput_bits_per_second = 524288 * 8 / (end - start)
            db['client_goodput'].append(tput_bits_per_second)

def __parse_line(line):
    d = {}

    parts = line.strip().split()
    for part in parts:
        if '=' not in part:
            continue

        p = part.split('=')
        assert len(p) > 1

        key, value = p[0], p[1]
        d[key] = value

    return d
