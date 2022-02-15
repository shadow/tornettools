import logging
import os
import re

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

            match = re.search(r'Seeded standard and numpy PRNGs with seed=(\d+)', line)
            if match:
                info['tornettools_generate_seed'] = int(match.groups()[0])
                continue
            match = re.search('Chose (\d+) of (\d+) relays using scale factor (\S+)', line)
            if match:
                info['num_sampled_relays'] = int(match.groups()[0])
                info['num_public_relays'] = int(match.groups()[1])
                info['net_scale'] = float(match.groups()[2])
                continue
            match = re.search(r'Generated fingerprints and keys for (\d+) Tor nodes \((\d+) authorities and (\d+) relays', line)
            if match:
                info['num_dir_authorities'] = int(match.groups()[1])
                continue
            match = re.search(r'We will use (\d+) TGen client processes to emulate (\S+) Tor exit users and create (\d+) exit circuits', line)
            if match:
                info['num_tgen_exit_markov_clients'] = int(match.groups()[0])
                info['num_tgen_exit_emulated_users'] = float(match.groups()[1])
                info['num_exit_circuits_ten_minutes'] = int(match.groups()[2])
                continue
            match = re.search(r'We will use (\d+) TGen client processes to emulate (\S+) Tor onion-service users and create (\d+) onion-service circuits', line)
            if match:
                info['num_tgen_hs_markov_clients'] = int(match.groups()[0])
                info['num_tgen_hs_emulated_users'] = float(match.groups()[1])
                info['num_hs_circuits_ten_minutes'] = int(match.groups()[2])
                continue
            match = re.search(r'We will use (\d+) exit perf nodes to benchmark Tor exit performance', line)
            if match:
                info['num_tgen_exit_perf_clients'] = int(match.groups()[0])
                continue
            match = re.search(r'We will use (\d+) onion-service perf nodes to benchmark Tor onion-service performance', line)
            if match:
                info['num_tgen_hs_perf_clients'] = int(match.groups()[0])
                continue
            match = re.search(r'We will use (\d+) TGen exit servers and (\d+) TGen onion-service servers', line)
            if match:
                info['num_tgen_exit_servers'] = int(match.groups()[0])
                info['num_tgen_onionservice_servers'] = int(match.groups()[1])
                continue

    outpath = f"{args.prefix}/tornet.plot.data/simulation_info.json"
    dump_json_data(info, outpath, compress=False)
