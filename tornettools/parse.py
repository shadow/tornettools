import logging
import os

from tornettools.parse_oniontrace import parse_oniontrace_logs, extract_oniontrace_plot_data
from tornettools.parse_tgen import parse_tgen_logs, extract_tgen_plot_data
from tornettools.parse_rusage import parse_resource_usage_logs, extract_resource_usage_plot_data
from tornettools.util import open_readable_file, dump_json_data

def run(args):
    logging.info("Parsing simulation output from {}".format(args.prefix))

    logging.info("Parsing tgen logs.")
    if args.skip_raw or parse_tgen_logs(args):
        logging.info("Extracting tgen plot data.")
        extract_tgen_plot_data(args)
    else:
        logging.warning("Parsing tgen logs failed, so we cannot extract tgen plot data.")

    logging.info("Parsing oniontrace logs.")
    if args.skip_raw or parse_oniontrace_logs(args):
        logging.info("Extracting oniontrace plot data.")
        extract_oniontrace_plot_data(args)
    else:
        logging.warning("Parsing oniontrace logs failed, so we cannot extract oniontrace plot data.")

    logging.info("Parsing resource usage logs.")
    if args.skip_raw or parse_resource_usage_logs(args):
        logging.info("Extracting resource usage plot data.")
        extract_resource_usage_plot_data(args)
    else:
        logging.warning("Parsing resource usage logs failed, so we cannot extract resource usage plot data.")

    __parse_tornettools_log(args)

    logging.info("Done parsing!")

def __parse_tornettools_log(args):
    gen_logs = [f for f in os.listdir(args.prefix) if f.startswith('tornettools.generate.')]
    if len(gen_logs) == 0:
        logging.warning("Unable to find simulation info in tornettools.generate.log file")
        return

    info = {}
    gen_log_path = f"{args.prefix}/{gen_logs[-1]}"
    with open_readable_file(gen_log_path) as inf:
        for line in inf:
            if "Seeded standard and numpy PRNGs" in line:
                info['tornettools_generate_seed'] = int(line.strip().split()[11].split('=')[1])
            elif "relays using scale factor" in line:
                parts = line.strip().split()
                l = len(parts)
                if l >= 7:
                    info['num_sampled_relays'] = int(parts[6])
                if l >= 9:
                    info['num_public_relays'] = int(parts[8])
                if l >= 14:
                    info['net_scale'] = float(parts[13])
            elif "Generated fingerprints and keys" in line:
                parts = line.strip().split()
                l = len(parts)
                if l >= 14:
                    info['num_dir_authorities'] = int(parts[13].strip('('))
            elif "TGen client processes to emulate" in line:
                parts = line.strip().split()
                l = len(parts)
                if l >= 9:
                    info['num_tgen_markov_clients'] = int(parts[8])
                if l >= 15:
                    info['num_emulated_users'] = int(parts[14])
                if l >= 20:
                    info['num_circuits_ten_minutes'] = int(parts[19])
            elif "perf nodes to benchmark Tor performance" in line:
                 parts = line.strip().split()
                 l = len(parts)
                 if l >= 9:
                     info['num_tgen_perf_clients'] = int(parts[8])
            elif "TGen clearnet servers" in line:
                 parts = line.strip().split()
                 l = len(parts)
                 if l >= 9:
                     info['num_tgen_servers'] = int(parts[8])
                 if l >= 14:
                     info['num_tgen_hiddenservices'] = int(parts[13])

    outpath = f"{args.prefix}/tornet.plot.data/simulation_info.json"
    dump_json_data(info, outpath, compress=False)
