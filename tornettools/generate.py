import sys
import os
import json
import yaml
import logging
import shlex
import shutil
import random
from ipaddress import IPv4Address
import base64

import networkx as nx

from tornettools.generate_defaults import *
from tornettools.generate_tgen import *
from tornettools.generate_tor import *

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

    os.mkdir("{}/{}".format(args.prefix, CONFIG_DIRNAME))

    # only copy the compressed atlas file if the user did not give us a custom path
    if args.atlas_path is None:
        logging.info("Copying atlas topology file (use the '-a/--atlas' option to disable)")
        topology_src_path = "{}/data/shadow/network/{}.xz".format(args.tmodel_git_path, TMODEL_TOPOLOGY_FILENAME)
        topology_dst_path = "{}/{}/{}.xz".format(args.prefix, CONFIG_DIRNAME, TMODEL_TOPOLOGY_FILENAME)
        shutil.copy2(topology_src_path, topology_dst_path)
        args.atlas_path = topology_dst_path

    # read the staged network info graph, which contains all of the atlas graph nodes
    logging.info(f"Reading staged network info {args.network_info_path}")
    network = nx.readwrite.gml.read_gml(args.network_info_path, label='id')
    logging.info("Finished reading staged network info")

    # get the set of relays we will create in shadow
    logging.info("Sampling Tor relays now")
    relays, relay_count = get_relays(args)

    # generate key material and fingerprints for these relays
    logging.info("Generating Tor key material now, this may take awhile...")
    authorities, relays = generate_tor_keys(args, relays)

    logging.info("Generating Clients")
    tgen_clients, perf_clients = get_clients(args)

    logging.info("Generating Servers")
    tgen_servers = get_servers(args, len(tgen_clients))

    # a map from hostnames to the host's torrc-defaults
    host_torrc_defaults = {}
    host_torrc_defaults.update({x['nickname']: {'includes': [TORRC_RELAY_FILENAME, TORRC_RELAY_AUTHORITY_FILENAME]} for x in authorities.values()})
    host_torrc_defaults.update({x['nickname']: __relay_host_torrc_defaults(x) for y in relays.values() for x in y.values()})
    host_torrc_defaults.update({x['name']: {'includes': [TORRC_CLIENT_FILENAME, TORRC_CLIENT_PERF_FILENAME]} for x in perf_clients})
    host_torrc_defaults.update({x['name']: {'includes': [TORRC_CLIENT_FILENAME, TORRC_CLIENT_MARKOV_FILENAME]} for x in tgen_clients})
    host_torrc_defaults.update({x['name']: {'includes': [TORRC_HIDDENSERVICE_FILENAME]} for x in tgen_servers if 'hs_hostname' in x})

    logging.info("Generating Tor configuration files")
    generate_tor_config(args, authorities, relays, host_torrc_defaults)

    logging.info("Generating TGen configuration files")
    generate_tgen_config(args, tgen_clients, tgen_servers)

    logging.info("Constructing Shadow config YAML file")
    __generate_shadow_config(args, network, authorities, relays, tgen_servers, perf_clients, tgen_clients)

def __assign_address(used_addresses, ip_address_hint):
    offset = 0
    while True:
        candidate = ip_address_hint + offset
        if candidate.is_global and candidate not in used_addresses:
            break
        offset += 1
    used_addresses.add(candidate)
    return candidate

def __relay_to_torrc_default_include(relay):
    if "exitguard" in relay['nickname']:
        return TORRC_RELAY_EXITGUARD_FILENAME
    elif "exit" in relay['nickname']:
        return TORRC_RELAY_EXITONLY_FILENAME
    elif "guard" in relay['nickname']:
        return TORRC_RELAY_GUARDONLY_FILENAME
    else:
        return TORRC_RELAY_OTHER_FILENAME

def __relay_host_torrc_defaults(relay):
    includes = [TORRC_RELAY_FILENAME, __relay_to_torrc_default_include(relay)]

    # only non-authority relays should have bandwidth config options set
    rate = max(BW_RATE_MIN, relay['bandwidth_rate'])
    burst = max(BW_RATE_MIN, relay['bandwidth_burst'])

    return {'includes': includes, 'bandwidth_rate': rate, 'bandwidth_burst': burst}

def __generate_shadow_config(args, network, authorities, relays, tgen_servers, perf_clients, tgen_clients):
    # create the YAML for the shadow.config.yaml file

    config = {}
    config["general"] = {}
    config["network"] = {}
    config["hosts"] = {}

    config["general"]["bootstrap_end_time"] = BOOTSTRAP_LENGTH_SECONDS # disable bandwidth limits and packet loss for first 5 minutes
    config["general"]["stop_time"] = SIMULATION_LENGTH_SECONDS # stop after 1 hour of simulated time

    # for compatability with old tornettools sims, this is also set as a default shadow argument in the cli
    config["general"]["template_directory"] = "shadow.data.template"

    # the atlas topology is complete, so we can use only direct edges
    config["network"]["use_shortest_path"] = False

    config["network"]["graph"] = {}
    config["network"]["graph"]["type"] = "gml"
    config["network"]["graph"]["file"] = {}
    config["network"]["graph"]["file"]["path"] = str(args.atlas_path)
    config["network"]["graph"]["file"]["compression"] = "xz"

    used_addresses = set()

    for (fp, authority) in sorted(authorities.items(), key=lambda kv: kv[1]['nickname']):
        config["hosts"].update(__tor_relay(args, network, used_addresses, authority, fp, is_authority=True))

    for pos in ['ge', 'e', 'g', 'm']:
        # use reverse to sort each class from fastest to slowest when assigning the id counter
        for (fp, relay) in sorted(relays[pos].items(), key=lambda kv: kv[1]['weight'], reverse=True):
            config["hosts"].update(__tor_relay(args, network, used_addresses, relay, fp, is_authority=False))

    for server in tgen_servers:
        config["hosts"].update(__server(args, network, server))

    for client in perf_clients:
        config["hosts"].update(__perfclient(args, network, client))

    for client in tgen_clients:
        config["hosts"].update(__markovclient(args, network, client))

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

def __filter_nodes(network, ip_address_hint, country_code_hint):
    # networkx stores the node 'id' separately, so take the node id from the tuple and combine it
    # with the other node properties
    all_nodes = [{'id': node_id, **node} for (node_id, node) in network.nodes(data=True)]

    if ip_address_hint is not None and not ip_address_hint.is_global:
        # ignore the hint if the IP address is not global
        logging.debug(f"Ignoring non-global address {ip_address_hint}")
        ip_address_hint = None

    if country_code_hint is not None:
        # normalize the country code
        country_code_hint = country_code_hint.casefold()

    # are there any nodes with the same ip address?
    ip_match_found = any('ip_address' in node and IPv4Address(node['ip_address']) == ip_address_hint for node in all_nodes)

    if ip_match_found:
        # get all nodes with exact IP matches, regardless of the country code
        candidate_nodes = [node for node in all_nodes if 'ip_address' in node and IPv4Address(node['ip_address']) == ip_address_hint]
    else:
        # get all nodes with the same country code
        candidate_nodes = [node for node in all_nodes if 'country_code' in node and node['country_code'].casefold() == country_code_hint]

        # if no node had the same country code, use all nodes
        if len(candidate_nodes) == 0:
            candidate_nodes = [node for node in all_nodes]

        any_ip_found = any('ip_address' in node for node in candidate_nodes)

        # if a node has an IP address and we were given an IP hint, perform longest prefix matching
        if any_ip_found and ip_address_hint is not None:
            # exclude nodes without an IP address
            candidate_nodes = [node for node in candidate_nodes if 'ip_address' in node]

            # function to compute the prefix match between two IPv4 addresses
            # the 32-bit mask is required since python uses signed integers
            #   (see https://stackoverflow.com/questions/210629/python-unsigned-32-bit-bitwise-arithmetic/210740)
            def compute_prefix_match(ip_1, ip_2): return ~(int(ip_1)^int(ip_2)) & 0xffffffff

            # get the prefix match for each node
            prefix_matches = [(node, compute_prefix_match(IPv4Address(node['ip_address']), ip_address_hint)) for node in candidate_nodes]

            # get the longest prefix match
            max_prefix_match = max(prefix_matches, key=lambda x: x[1])[1]

            # get the nodes with the longest prefix match
            candidate_nodes = [node for (node, prefix_match) in prefix_matches if prefix_match == max_prefix_match]

            # given the 'compute_prefix_match' function above, these nodes should all have the same IP address
            assert len(set([IPv4Address(node['ip_address']) for node in candidate_nodes])) == 1

    return candidate_nodes

def __server(args, network, server):
    # Make sure we have enough bandwidth for the expected number of clients
    scaled_bw_kbit = __get_scaled_tgen_server_bandwidth_kbit(args)
    host_bw_kbit = max(BW_1GBIT_KBIT, scaled_bw_kbit)

    # filter the network graph nodes by their country, and choose one node
    country_code_hint = server.get('country_code')
    chosen_node = random.choice(__filter_nodes(network, None, country_code_hint))

    # add the host element and attributes
    host = {}
    host['network_node_id'] = chosen_node['id']

    host["bandwidth_up"] = "{} kilobit".format(host_bw_kbit)
    host["bandwidth_down"] = "{} kilobit".format(host_bw_kbit)

    host["processes"] = []

    process = {}
    process["path"] = "{}/bin/tgen".format(SHADOW_INSTALL_PREFIX)
    process["args"] = get_host_rel_conf_path(TGENRC_SERVER_FILENAME)
    # tgen starts at the end of shadow's "bootstrap" phase
    process["start_time"] = BOOTSTRAP_LENGTH_SECONDS

    host["processes"].append(process)

    if 'hs_hostname' in server:
        # prepare the hostname and hs_ed25519_secret_key files for the onion service
        hosts_prefix = "{}/{}/{}".format(args.prefix, SHADOW_TEMPLATE_PATH, SHADOW_HOSTS_PATH)
        server_prefix = "{}/{}".format(hosts_prefix, server['name'])
        hs_prefix = "{}/hs".format(server_prefix)

        if not os.path.exists(hs_prefix):
            os.makedirs(hs_prefix, 0o700)

        with open("{}/{}".format(hs_prefix, 'hostname'), 'w') as outf:
            outf.write(server['hs_hostname']+'\n')
        with open("{}/{}".format(hs_prefix, 'hs_ed25519_secret_key'), 'wb') as outf:
            outf.write(b"== ed25519v1-secret: type0 ==\x00\x00\x00" + base64.b64decode(server['hs_ed25519_secret_key']))

        # tor process for the hidden service
        process = {}
        process["path"] = "{}/bin/tor".format(SHADOW_INSTALL_PREFIX)
        process["args"] = __format_tor_args(server['name'])
        process["start_time"] = BOOTSTRAP_LENGTH_SECONDS-60 # start before boostrapping ends

        host["processes"].append(process)

    return {server['name']: host}

def __perfclient(args, network, client):
    return __tgen_client(args, network, client['name'], client['country_code'], \
        get_host_rel_conf_path(TGENRC_PERFCLIENT_FILENAME))

def __markovclient(args, network, client):
    # these should be relative paths
    return __tgen_client(args, network, client['name'], client['country_code'], \
        TGENRC_MARKOVCLIENT_FILENAME)

def __format_tor_args(name):
    args = [
        f"--Address {name}",
        f"--Nickname {name}",
        f"--defaults-torrc {TORRC_DEFAULTS_HOST_FILENAME}",
        f"-f {TORRC_HOST_FILENAME}",
    ]
    return ' '.join(args)

def __tgen_client(args, network, name, country, tgenrc_fname):
    # Make sure we have enough bandwidth for the simulated number of users
    scaled_bw_kbit = __get_scaled_tgen_client_bandwidth_kbit(args)
    host_bw_kbit = max(BW_1GBIT_KBIT, scaled_bw_kbit)

    # filter the network graph nodes by their country, and choose one node
    country_code_hint = country
    chosen_node = random.choice(__filter_nodes(network, None, country_code_hint))

    # add the host element and attributes
    host = {}
    host['network_node_id'] = chosen_node['id']

    host["bandwidth_up"] = "{} kilobit".format(host_bw_kbit)
    host["bandwidth_down"] = "{} kilobit".format(host_bw_kbit)

    host["processes"] = []

    process = {}
    process["path"] = "{}/bin/tor".format(SHADOW_INSTALL_PREFIX)
    process["args"] = __format_tor_args(name)
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

def __tor_relay(args, network, used_addresses, relay, orig_fp, is_authority=False):
    # prepare items for the host element
    kbits = 8 * int(round(int(relay['bandwidth_capacity']) / 1000.0))

    hosts_prefix = "{}/{}/{}".format(args.prefix, SHADOW_TEMPLATE_PATH, SHADOW_HOSTS_PATH)
    with open("{}/{}/fingerprint-public-tor".format(hosts_prefix, relay['nickname']), 'w') as outf:
        outf.write(f"{orig_fp}\n")

    # filter the network graph nodes by their IP address and country, and choose one node
    ip_address_hint = IPv4Address(relay['address']) if 'address' in relay else None
    country_code_hint = relay.get('country_code')
    chosen_node = random.choice(__filter_nodes(network, ip_address_hint, country_code_hint))

    # add the host element and attributes
    host = {}
    host['network_node_id'] = chosen_node['id']

    if ip_address_hint:
        host["ip_addr"] = str(__assign_address(used_addresses, ip_address_hint))

    host["bandwidth_down"] = "{} kilobit".format(kbits)
    host["bandwidth_up"] = "{} kilobit".format(kbits)

    # prepare items for the tor process element
    if is_authority:
        starttime = 1
    elif "exitguard" in relay['nickname']:
        starttime = 2
    elif "exit" in relay['nickname']:
        starttime = 3
    elif "guard" in relay['nickname']:
        starttime = 4
    else:
        starttime = 5

    host['processes'] = []

    process = {}
    process["path"] = "{}/bin/tor".format(SHADOW_INSTALL_PREFIX)
    process["args"] = str(__format_tor_args(relay['nickname']))
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
