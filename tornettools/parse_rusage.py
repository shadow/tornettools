import os
import logging
import datetime

from numpy import mean

from tornettools.util import open_readable_file, load_json_data, dump_json_data

def parse_resource_usage_logs(args):
    free_filepath = f"{args.prefix}/free.log"
    if not os.path.exists(free_filepath):
        free_filepath += ".xz"

    if not os.path.exists(free_filepath):
        logging.warning(f"Unable to find resource usage data at {free_filepath}")
        return False

    rusage = {}

    last_ts = None
    mem_header = None
    with open_readable_file(free_filepath) as inf:
        for line in inf:
            if line.count(':') == 2:
                dt = datetime.datetime.strptime(line.strip(), "%a %b %d %H:%M:%S %Z %Y")
                last_ts = dt.timestamp()
            elif 'total' in line and mem_header == None:
                mem_header = [p.strip() for p in line.strip().split()]
            elif "Mem:" in line:
                parts = [p.strip() for p in line.strip().split()]
                mem_counts = [int(p) for p in parts[1:]]

                memd = {f"mem_{mem_header[i]}": mem_counts[i] for i in range(len(mem_counts))}

                rusage.setdefault(last_ts, memd)

    if len(rusage) > 0:
        outpath = f"{args.prefix}/free.json.xz"
        dump_json_data(rusage, outpath, compress=True)
        return True
    else:
        logging.warning(f"Unable to parse resource data from {free_filepath}.")
        return False

def extract_resource_usage_plot_data(args):
    json_path = f"{args.prefix}/free.json"

    if not os.path.exists(json_path):
        json_path += ".xz"

    if not os.path.exists(json_path):
        logging.warning(f"Unable to find resource usage data at {json_path}.")
        return

    data = load_json_data(json_path)
    __extract_resource_usage(args, data)

def __extract_resource_usage(args, data):
    rusage = {"ram": __get_ram_usage(data), "run_time": __get_run_time(data)}
    outpath = f"{args.prefix}/tornet_plot_data/resource_usage.json"
    dump_json_data(rusage, outpath, compress=False)

def __get_ram_usage(data):
    used = {float(ts): data[ts]["mem_used"] for ts in data}

    ts_start = min(used.keys())
    mem_start = used[ts_start] # mem used by OS, i.e., before starting shadow
    mem_max = max(used.values())

    # subtract mem used by OS, get time offset from beginning of simulation
    gib_used_per_second = {int(ts-ts_start): (used[ts]-mem_start)/(1024.0**3) for ts in used}
    bytes_used_max = mem_max - mem_start
    gib_used_max = bytes_used_max/(1024.0**3)

    gib_minute_bins = {}
    for second in gib_used_per_second:
        gib_minute_bins.setdefault(int(second/60), []).append(gib_used_per_second[second])

    gib_used_per_minute = {minute: mean(gib_minute_bins[minute]) for minute in gib_minute_bins}

    return {"bytes_used_max": bytes_used_max, "gib_used_max": gib_used_max, "gib_used_per_minute": gib_used_per_minute}

def __get_run_time(data):
    times = [float(k) for k in data.keys()]

    dt_min = datetime.datetime.fromtimestamp(min(times))
    dt_max = datetime.datetime.fromtimestamp(max(times))
    runtime = dt_max - dt_min

    return {"human": str(runtime), "seconds": runtime.total_seconds()}
