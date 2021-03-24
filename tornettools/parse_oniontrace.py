import os
import logging
import datetime
import subprocess

from tornettools.util import which, cmdsplit, open_writeable_file, load_json_data, dump_json_data

def parse_oniontrace_logs(args):
    otracetools_exe = which('oniontracetools')

    if otracetools_exe == None:
        logging.warning("Cannot find oniontracetools in your PATH. Is your python venv active? Do you have oniontracetools installed?")
        logging.warning("Unable to parse oniontrace simulation data.")
        return

    cmd_str = f"{otracetools_exe} parse -m {args.nprocesses} -e '.*\.oniontrace\.[0-9]+.stdout' shadow.data/hosts"
    cmd = cmdsplit(cmd_str)

    datestr = datetime.datetime.now().strftime("%Y-%m-%d.%H:%M:%S")

    with open_writeable_file(f"{args.prefix}/oniontracetools.parse.{datestr}.log") as outf:
        logging.info("Parsing oniontrace log data with oniontracetools now...")
        comproc = subprocess.run(cmd, cwd=args.prefix, stdout=outf, stderr=subprocess.STDOUT)
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

    # parse performance stats only after the network has reached steady state
    startts, stopts = args.converge_time, -1 if args.run_time < 0 else args.converge_time + args.run_time

    __extract_circuit_build_times(args, data, startts, stopts)
    __extract_relay_tput(args, data, startts, stopts)

def __extract_circuit_build_times(args, data, startts, stopts):
    cbt = __get_perfclient_cbt(data, startts, stopts)
    outpath = f"{args.prefix}/tornet.plot.data/perfclient_circuit_build_time.json"
    dump_json_data(cbt, outpath, compress=False)

def __extract_relay_tput(args, data, startts, stopts):
    tput = __get_relay_tput(data, startts, stopts)
    outpath = f"{args.prefix}/tornet.plot.data/relay_goodput.json"
    dump_json_data(tput, outpath, compress=False)

def __get_perfclient_cbt(data, startts, stopts):
    perf_cbt = []

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
                    for val in cbt[secstr]:
                        #item = [val, resolution]
                        item = val
                        perf_cbt.append(item)

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
