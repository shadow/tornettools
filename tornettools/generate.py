import sys
import os
import json
import yaml
import logging
import shlex

from tornettools.generate_defaults import *
from tornettools.generate_tgen import *
from tornettools.generate_tor import *
from tornettools.util import copy_and_extract_file

def run(args):
    if args.torexe == None:
        logging.critical("Unable to find a 'tor' executable in PATH, but we need it to generate keys. Did you build 'tor'? Did you set your PATH or provide the path to the 'tor' executable?")
        logging.critical("Refusing to generate a network without 'tor'.")
        return
    if args.torgencertexe == None:
        logging.critical("Unable to find a 'tor-gencert' executable in PATH, but we need it to generate keys. Did you build 'tor-gencert'? Did you set your PATH or provide the path to the 'tor-gencert' executable?")
        logging.critical("Refusing to generate a network without 'tor-gencert'.")
        return

    logging.info(f"Generating network using tor and tor-gencert at {args.torexe} and {args.torgencertexe}")

    # get the set of relays we will create in shadow
    logging.info("Sampling Tor relays now")
    relays, relay_count = get_relays(args)

    # generate key material and fingerprints for these relays
    logging.info("Generating Tor key material now, this may take awhile...")
    authorities, relays = generate_tor_keys(args, relays)

    logging.info("Generating Tor configuration files")
    generate_tor_config(args, authorities, relays)

    logging.info("Generating Clients")
    tgen_clients, perf_clients = get_clients(args)

    logging.info("Generating Servers")
    tgen_servers = get_servers(args, len(tgen_clients))

    logging.info("Generating TGen configuration files")
    generate_tgen_config(args, tgen_clients, tgen_servers)

    logging.info("Constructing Shadow config YAML file")
    __generate_shadow_config(args, authorities, relays, tgen_servers, perf_clients, tgen_clients)

    # only copy the atlas file if the user did not tell us where it has the atlas stored
    if args.atlas_path is None:
        logging.info("Copying atlas topology file (use the '-a/--atlas' option to disable)")
        topology_src_path = "{}/data/shadow/network/{}.xz".format(args.tmodel_git_path, TMODEL_TOPOLOGY_FILENAME)
        topology_dst_path = "{}/{}/{}.xz".format(args.prefix, CONFIG_DIRNAME, TMODEL_TOPOLOGY_FILENAME)
        copy_and_extract_file(topology_src_path, topology_dst_path)

def __generate_shadow_config(args, authorities, relays, tgen_servers, perf_clients, tgen_clients):
    # create the YAML for the shadow.config.yaml file

    config = {}
    config["general"] = {}
    config["network"] = {}
    config["hosts"] = {}

    config["general"]["bootstrap_end_time"] = BOOTSTRAP_LENGTH_SECONDS # disable bandwidth limits and packet loss for first 5 minutes
    config["general"]["stop_time"] = SIMULATION_LENGTH_SECONDS # stop after 1 hour of simulated time

    # the atlas topology is complete, so we can use only direct edges
    config["network"]["use_shortest_path"] = False

    config["network"]["graph"] = {}
    config["network"]["graph"]["type"] = "gml"

    if args.atlas_path is None:
        config["network"]["graph"]["path"] = "{}/{}".format(CONFIG_DIRNAME, TMODEL_TOPOLOGY_FILENAME)
    else:
        config["network"]["graph"]["path"] = str(args.atlas_path)

    for (fp, authority) in sorted(authorities.items(), key=lambda kv: kv[1]['nickname']):
        config["hosts"].update(__tor_relay(args, authority, fp, is_authority=True))

    for pos in ['ge', 'e', 'g', 'm']:
        # use reverse to sort each class from fastest to slowest when assigning the id counter
        for (fp, relay) in sorted(relays[pos].items(), key=lambda kv: kv[1]['weight'], reverse=True):
            config["hosts"].update(__tor_relay(args, relay, fp, is_authority=False))

    for server in tgen_servers:
        config["hosts"].update(__server(args, server))

    for client in perf_clients:
        config["hosts"].update(__perfclient(args, client))

    for client in tgen_clients:
        config["hosts"].update(__markovclient(args, client))

    with open("{}/{}".format(args.prefix, SHADOW_CONFIG_FILENAME), 'w') as configfile:
        yaml.dump(config, configfile, sort_keys=False)

def __get_scaled_tgen_client_bandwidth_kbit(args):
    # 10 Mbit/s per "user" that a tgen client simulates
    n_users_per_tgen = round(1.0 / args.process_scale)
    scaled_bw = n_users_per_tgen * 10 * BW_1MBIT_KBIT
    return scaled_bw

def __get_scaled_tgen_server_bandwidth_kbit(args):
    scaled_client_bw = __get_scaled_tgen_client_bandwidth_kbit(args)
    n_clients_per_server = round(1.0 / args.process_scale)
    scaled_bw = scaled_client_bw * n_clients_per_server
    return scaled_bw

def __server(args, server):
    # Make sure we have enough bandwidth for the expected number of clients
    scaled_bw_kbit = __get_scaled_tgen_server_bandwidth_kbit(args)
    host_bw_kbit = max(BW_1GBIT_KBIT, scaled_bw_kbit)

    host = {}
    host["options"] = {}
    host["options"]["country_code_hint"] = str(server['country_code']).upper()

    host["bandwidth_up"] = "{} kilobit".format(host_bw_kbit)
    host["bandwidth_down"] = "{} kilobit".format(host_bw_kbit)

    host["processes"] = []

    process = {}
    process["path"] = "{}/bin/tgen".format(SHADOW_INSTALL_PREFIX)
    process["args"] = get_host_rel_conf_path(TGENRC_SERVER_FILENAME)
    # tgen starts at the end of shadow's "bootstrap" phase
    process["start_time"] = BOOTSTRAP_LENGTH_SECONDS

    host["processes"].append(process)

    return {server['name']: host}

def __perfclient(args, client):
    return __tgen_client(args, client['name'], client['country_code'], \
        TORRC_PERFCLIENT_FILENAME, get_host_rel_conf_path(TGENRC_PERFCLIENT_FILENAME))

def __markovclient(args, client):
    # these should be relative paths
    return __tgen_client(args, client['name'], client['country_code'], \
        TORRC_MARKOVCLIENT_FILENAME, TGENRC_MARKOVCLIENT_FILENAME)

def __format_tor_args(name, torrc_fname):
    args = [
        f"--Address {name}",
        f"--Nickname {name}",
        f"--DataDirectory .",
        f"--GeoIPFile {SHADOW_INSTALL_PREFIX}/share/geoip",
        f"--defaults-torrc {get_host_rel_conf_path(TORRC_COMMON_FILENAME)}",
        f"-f {get_host_rel_conf_path(torrc_fname)}",
    ]
    return ' '.join(args)

def __tgen_client(args, name, country, torrc_fname, tgenrc_fname):
    # Make sure we have enough bandwidth for the simulated number of users
    scaled_bw_kbit = __get_scaled_tgen_client_bandwidth_kbit(args)
    host_bw_kbit = max(BW_1GBIT_KBIT, scaled_bw_kbit)

    host = {}
    host["options"] = {}
    host["options"]["country_code_hint"] = str(country).upper()

    host["bandwidth_up"] = "{} kilobit".format(host_bw_kbit)
    host["bandwidth_down"] = "{} kilobit".format(host_bw_kbit)

    host["processes"] = []

    process = {}
    process["path"] = "{}/bin/tor".format(SHADOW_INSTALL_PREFIX)
    process["args"] = __format_tor_args(name, torrc_fname)
    process["start_time"] = BOOTSTRAP_LENGTH_SECONDS-60 # start before boostrapping ends

    host["processes"].append(process)

    oniontrace_start_time = BOOTSTRAP_LENGTH_SECONDS-60+1
    host["processes"].extend(__oniontrace(args, oniontrace_start_time, name))

    process = {}
    process["path"] = "{}/bin/tgen".format(SHADOW_INSTALL_PREFIX)
    process["args"] = tgenrc_fname
    # tgen starts at the end of shadow's "bootstrap" phase, and may have its own startup delay
    process["start_time"] = BOOTSTRAP_LENGTH_SECONDS

    host["processes"].append(process)

    return {name: host}

def __tor_relay(args, relay, orig_fp, is_authority=False):
    # prepare items for the host element
    kbits = 8 * int(round(int(relay['bandwidth_capacity']) / 1000.0))

    hosts_prefix = "{}/{}/{}".format(args.prefix, SHADOW_TEMPLATE_PATH, SHADOW_HOSTS_PATH)
    with open("{}/{}/fingerprint-public-tor".format(hosts_prefix, relay['nickname']), 'w') as outf:
        outf.write(f"{orig_fp}\n")

    # add the host element and attributes
    host = {}
    host["options"] = {}
    host["options"]["ip_address_hint"] = relay['address']
    host["options"]["country_code_hint"] = str(relay['country_code']).upper()

    host["bandwidth_down"] = "{} kilobit".format(kbits)
    host["bandwidth_up"] = "{} kilobit".format(kbits)

    # prepare items for the tor process element
    if is_authority:
        starttime = 1
        torrc_fname = TORRC_AUTHORITY_FILENAME
    elif "exitguard" in relay['nickname']:
        starttime = 2
        torrc_fname = TORRC_EXITRELAY_FILENAME
    elif "exit" in relay['nickname']:
        starttime = 3
        torrc_fname = TORRC_EXITRELAY_FILENAME
    elif "guard" in relay['nickname']:
        starttime = 4
        torrc_fname = TORRC_NONEXITRELAY_FILENAME
    else:
        starttime = 5
        torrc_fname = TORRC_NONEXITRELAY_FILENAME

    tor_args = __format_tor_args(relay['nickname'], torrc_fname)
    if not is_authority:
        # Tor enforces a min rate for relays
        rate = max(BW_RATE_MIN, relay['bandwidth_rate'])
        burst = max(BW_RATE_MIN, relay['bandwidth_burst'])
        tor_args += " --BandwidthRate {} --BandwidthBurst {}".format(rate, burst)

    host['processes'] = []

    process = {}
    process["path"] = "{}/bin/tor".format(SHADOW_INSTALL_PREFIX)
    process["args"] = str(tor_args)
    process["start_time"] = starttime

    host['processes'].append(process)

    oniontrace_start_time = starttime+1
    host['processes'].extend(__oniontrace(args, oniontrace_start_time, relay['nickname']))

    return {relay['nickname']: host}

def __oniontrace(args, start_time, name):
    processes = []

    if args.events_csv is not None:
        process = {}
        process["path"] = "{}/bin/oniontrace".format(SHADOW_INSTALL_PREFIX)
        process["args"] = "Mode=log TorControlPort={} LogLevel=info Events={}".format(TOR_CONTROL_PORT, args.events_csv)
        process["start_time"] = start_time
        processes.append(process)

    if args.do_trace:
        start_time = max(start_time, BOOTSTRAP_LENGTH_SECONDS)
        process = {}
        process["path"] = "{}/bin/oniontrace".format(SHADOW_INSTALL_PREFIX)
        run_time = SIMULATION_LENGTH_SECONDS-start_time-1
        process["args"] = "Mode=record TorControlPort={} LogLevel=info RunTime={} TraceFile=oniontrace.csv".format(TOR_CONTROL_PORT, run_time)
        process["start_time"] = start_time
        processes.append(process)

    return processes
