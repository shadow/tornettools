import os
import logging
import datetime

from tornettools.util import *

def parse_oniontrace_logs(args):
    otracetools_exe = which('oniontracetools')

    if otracetools_exe == None:
        logging.warning("Cannot find oniontracetools in your PATH. Is your python venv active? Do you have oniontracetools installed?")
        logging.warning("Unable to parse oniontrace simulation data.")
        return

    cmd_str = f"{otracetools_exe} parse -m {args.nprocesses} -e 'oniontrace.*\.log' shadow.data/hosts"
    cmd = shlex.split(cmd_str)

    datestr = datetime.now().strftime("%Y-%m-%d.%H:%M:%S")

    with open_writeable_file(f"{args.prefix}/oniontracetools.parse.{datestr}.log") as outf:
        logging.info("Parsing oniontrace log data with oniontracetools now...")
        comproc = subprocess.run(cmd, cwd=args.prefix, stdout=outf)
        logging.info(f"oniontracetools returned code {comproc.returncode}")

    return comproc.returncode == 0

def extract_oniontrace_plot_data(args):
    json_path = f"{args.prefix}/oniontrace.analysis.json"

    if not os.path.exists(json_path):
        json_path += ".xz"

    if not os.path.exists(json_path):
        logging.warning(f"Unable to find oniontrace analysis data at {json_path}.")
        return

    data = load_json_data(json_path)

    # skip the first 20 minutes to allow the network to reach steady state
    startts, stopts = 1200, -1

    __extract_circuit_build_times(args, data, startts, stopts)
    __extract_relay_tput(args, data, startts, stopts)

def __extract_circuit_build_times(args, data, startts, stopts):
    cbt = __get_perfclient_cbt(data, startts, stopts)
    outpath = f"{args.prefix}/plot.data/oniontrace_perfclient_cbt.json"
    dump_json_data(cbt, outpath, compress=False)

def __extract_relay_tput(args, data, startts, stopts):
    tput = __get_relay_tput(data, startts, stopts)
    outpath = f"{args.prefix}/plot.data/oniontrace_relay_tput.json"
    dump_json_data(tput, outpath, compress=False)

def __get_perfclient_cbt(data, startts, stopts):
    perf_cbt = {}

    # cbts can differ by microseconds
    resolution = 1.0/1000000.0

    if 'data' in data:
        for name in data['data']:
            if 'perfclient' not in name: continue

            circ = data['data'][name]['oniontrace']['circuit']
            key = 'build_time'
            if circ is None or key not in circ: continue

            cbt = circ[key]

            for secstr in cbt:
                sec = int(secstr)-946684800
                if sec >= startts and (stopts < 0 or sec < stopts):
                    perf_cbt.setdefault(sec, [])
                    for val in cbt[secstr]:
                        #item = [val, resolution]
                        item = val
                        perf_cbt[sec].append(item)

    return perf_cbt

def __get_relay_tput(data, startts, stopts):
    net_tput_sec = {}

    # resolution in 1 byte
    resolution = 1

    if 'data' in data:
        for name in data['data']:
            if 'relay' not in name and '4uthority' not in name: continue

            bw = data['data'][name]['oniontrace']['bandwidth']
            key = 'bytes_written'
            if bw is None or key not in bw: continue

            tput = bw[key]

            for secstr in tput:
                sec = int(secstr)-946684800
                if sec >= startts and (stopts < 0 or sec < stopts):
                    bytes = int(tput[secstr])
                    net_tput_sec.setdefault(sec, 0)
                    net_tput_sec[sec] += bytes

    return net_tput_sec
