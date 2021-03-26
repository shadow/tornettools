import sys
import os
import json
import logging
import shlex

from lxml import etree

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

    logging.info("Constructing Shadow config XML file")
    __generate_shadow_config(args, authorities, relays, tgen_servers, perf_clients, tgen_clients)

    # only copy the atlas file if the user did not tell us where it has the atlas stored
    if args.atlas_path is None:
        logging.info("Copying atlas topology file (use the '-a/--atlas' option to disable)")
        topology_src_path = "{}/data/shadow/network/{}.xz".format(args.tmodel_git_path, TMODEL_TOPOLOGY_FILENAME)
        topology_dst_path = "{}/{}/{}.xz".format(args.prefix, CONFIG_DIRNAME, TMODEL_TOPOLOGY_FILENAME)
        copy_and_extract_file(topology_src_path, topology_dst_path)

def __generate_shadow_config(args, authorities, relays, tgen_servers, perf_clients, tgen_clients):
    # create the XML for the shadow.config.xml file
    root = etree.Element("shadow")
    root.set("bootstraptime", "{}".format(BOOTSTRAP_LENGTH_SECONDS)) # disable bandwidth limits and packet loss for first 5 minutes
    root.set("stoptime", "{}".format(SIMULATION_LENGTH_SECONDS)) # stop after 1 hour of simulated time
    root.set("preload", "{}/lib/libshadow-shim.so".format(SHADOW_INSTALL_PREFIX))
    root.set("environment", "OPENSSL_ia32cap=~0x200000200000000;EVENT_NOSELECT=1;EVENT_NOPOLL=1;EVENT_NOKQUEUE=1;EVENT_NODEVPOLL=1;EVENT_NOEVPORT=1;EVENT_NOWIN32=1")

    topology = etree.SubElement(root, "topology")
    if args.atlas_path is None:
        topology.set("path", "{}/{}".format(CONFIG_DIRNAME, TMODEL_TOPOLOGY_FILENAME))
    else:
        topology.set("path", "{}".format(args.atlas_path))

    plugin = etree.SubElement(root, "plugin")
    plugin.set("id", "tor")
    plugin.set("path", "{}/bin/tor".format(SHADOW_INSTALL_PREFIX))

    plugin = etree.SubElement(root, "plugin")
    plugin.set("id", "tor-preload")
    plugin.set("path", "{}/lib/libshadow-preload-tor.so".format(SHADOW_INSTALL_PREFIX))

    if args.events_csv is not None or args.do_trace:
        plugin = etree.SubElement(root, "plugin")
        plugin.set("id", "oniontrace")
        plugin.set("path", "{}/bin/oniontrace".format(SHADOW_INSTALL_PREFIX))

    plugin = etree.SubElement(root, "plugin")
    plugin.set("id", "tgen")
    plugin.set("path", "{}/bin/tgen".format(SHADOW_INSTALL_PREFIX))

    for (fp, authority) in sorted(authorities.items(), key=lambda kv: kv[1]['nickname']):
        __add_xml_tor_relay(args, root, authority, fp, is_authority=True)

    for pos in ['ge', 'e', 'g', 'm']:
        # use reverse to sort each class from fastest to slowest when assigning the id counter
        for (fp, relay) in sorted(relays[pos].items(), key=lambda kv: kv[1]['weight'], reverse=True):
            __add_xml_tor_relay(args, root, relay, fp, is_authority=False)

    for server in tgen_servers:
        __add_xml_server(args, root, server)

    for client in perf_clients:
        __add_xml_perfclient(args, root, client)

    for client in tgen_clients:
        __add_xml_markovclient(args, root, client)

    xml_str = etree.tostring(root, pretty_print=True, xml_declaration=False)
    with open("{}/{}".format(args.prefix, SHADOW_CONFIG_FILENAME), 'wb') as configfile:
        configfile.write(xml_str)

def __get_scaled_tgen_client_bandwidth_kib(args):
    # 10 Mbit/s per "user" that a tgen client simulates
    n_users_per_tgen = round(1.0 / args.process_scale)
    scaled_bw = n_users_per_tgen * 10 * BW_1MBIT_KIB
    return scaled_bw

def __get_scaled_tgen_server_bandwidth_kib(args):
    scaled_client_bw = __get_scaled_tgen_client_bandwidth_kib(args)
    n_clients_per_server = round(1.0 / args.process_scale)
    scaled_bw = scaled_client_bw * n_clients_per_server
    return scaled_bw

def __add_xml_server(args, root, server):
    # Make sure we have enough bandwidth for the expected number of clients
    scaled_bw = __get_scaled_tgen_server_bandwidth_kib(args)
    host_bw = max(BW_1GBIT_KIB, scaled_bw)

    host = etree.SubElement(root, SHADOW_XML_HOST_KEY)
    host.set("id", server['name'])
    host.set("countrycodehint", server['country_code'])
    host.set("bandwidthup", "{}".format(host_bw))
    host.set("bandwidthdown", "{}".format(host_bw))

    process = etree.SubElement(host, SHADOW_XML_PROCESS_KEY)
    process.set("plugin", "tgen")
    # tgen starts at the end of shadow's "bootstrap" phase
    process.set("starttime", "{}".format(BOOTSTRAP_LENGTH_SECONDS))
    process.set("arguments", get_host_rel_conf_path(TGENRC_SERVER_FILENAME))

def __add_xml_perfclient(args, root, client):
    __add_xml_tgen_client(args, root, client['name'], client['country_code'], \
        TORRC_PERFCLIENT_FILENAME, TGENRC_PERFCLIENT_FILENAME)

def __add_xml_markovclient(args, root, client):
    # these should be relative paths
    tgenrc_filename = TGENRC_MARKOVCLIENT_FILENAME_FMT.format(client['name'])
    __add_xml_tgen_client(args, root, client['name'], client['country_code'], \
        TORRC_MARKOVCLIENT_FILENAME, tgenrc_filename, tgenrc_subdirname=TGENRC_MARKOVCLIENT_DIRNAME)

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

def __add_xml_tgen_client(args, root, name, country, torrc_fname, tgenrc_fname, tgenrc_subdirname=None):
    # Make sure we have enough bandwidth for the simulated number of users
    scaled_bw = __get_scaled_tgen_client_bandwidth_kib(args)
    host_bw = max(BW_1GBIT_KIB, scaled_bw)

    host = etree.SubElement(root, SHADOW_XML_HOST_KEY)
    host.set("id", name)
    host.set("countrycodehint", country)
    host.set("bandwidthup", "{}".format(host_bw))
    host.set("bandwidthdown", "{}".format(host_bw))

    process = etree.SubElement(host, SHADOW_XML_PROCESS_KEY)
    process.set("plugin", "tor")
    process.set("preload", "tor-preload")
    process.set("starttime", "{}".format(BOOTSTRAP_LENGTH_SECONDS-60)) # start before boostrapping ends
    process.set("arguments", __format_tor_args(name, torrc_fname))

    oniontrace_start_time = BOOTSTRAP_LENGTH_SECONDS-60+1
    __add_xml_oniontrace(args, host, oniontrace_start_time, name)

    process = etree.SubElement(host, SHADOW_XML_PROCESS_KEY)
    process.set("plugin", "tgen")
    # tgen starts at the end of shadow's "bootstrap" phase, and may have its own startup delay
    process.set("starttime", "{}".format(BOOTSTRAP_LENGTH_SECONDS))
    process.set("arguments", get_host_rel_conf_path(tgenrc_fname, rc_subdirname=tgenrc_subdirname))

def __add_xml_tor_relay(args, root, relay, orig_fp, is_authority=False):
    # prepare items for the host element
    kib = int(round(int(relay['bandwidth_capacity']) / 1024.0))

    hosts_prefix = "{}/{}/{}".format(args.prefix, SHADOW_TEMPLATE_PATH, SHADOW_HOSTS_PATH)
    with open("{}/{}/fingerprint-public-tor".format(hosts_prefix, relay['nickname']), 'w') as outf:
        outf.write(f"{orig_fp}\n")

    # add the host element and attributes
    host = etree.SubElement(root, SHADOW_XML_HOST_KEY)
    host.set("id", relay['nickname'])
    host.set("iphint", relay['address'])
    host.set("countrycodehint", relay['country_code'])
    host.set("bandwidthdown", "{}".format(kib))
    host.set("bandwidthup", "{}".format(kib))

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

    process = etree.SubElement(host, SHADOW_XML_PROCESS_KEY)

    process.set("plugin", "tor")
    process.set("preload", "tor-preload")
    process.set("starttime", "{}".format(starttime))
    process.set("arguments", "{}".format(tor_args))

    oniontrace_start_time = starttime+1
    __add_xml_oniontrace(args, host, oniontrace_start_time, relay['nickname'])

def __add_xml_oniontrace(args, parent_elm, start_time, name):
    if args.events_csv is not None:
        process = etree.SubElement(parent_elm, SHADOW_XML_PROCESS_KEY)
        process.set("plugin", "oniontrace")
        process.set("starttime", "{}".format(start_time))
        process.set("arguments", "Mode=log TorControlPort={} LogLevel=info Events={}".format(TOR_CONTROL_PORT, args.events_csv))

    if args.do_trace:
        start_time = max(start_time, BOOTSTRAP_LENGTH_SECONDS)
        process = etree.SubElement(parent_elm, SHADOW_XML_PROCESS_KEY)
        process.set("plugin", "oniontrace")
        process.set("starttime", "{}".format(start_time))
        run_time = SIMULATION_LENGTH_SECONDS-start_time-1
        process.set("arguments", "Mode=record TorControlPort={} LogLevel=info RunTime={} TraceFile=oniontrace.csv".format(TOR_CONTROL_PORT, run_time))
