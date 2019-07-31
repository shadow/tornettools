import sys
import os
import json
import logging
import shutil
import shlex

from lxml import etree

from shadowtortools.generate_defaults import *
from shadowtortools.generate_tgen import *
from shadowtortools.generate_tor import *

def run(args):
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
        topology_dst_path = "{}/{}/{}.xz".format(args.prefix, CONFIG_DIRPATH, TMODEL_TOPOLOGY_FILENAME)
        __copy_and_extract_file(topology_src_path, topology_dst_path)

def __copy_and_extract_file(src, dst):
    shutil.copy2(src, dst)

    xz_cmd = "xz -d {}".format(dst)
    retcode = subprocess.call(shlex.split(xz_cmd), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if retcode != 0:
        logging.critical("Error extracting file {} using command {}".format(dst, cmd))
    assert retcode == 0

def __generate_shadow_config(args, authorities, relays, tgen_servers, perf_clients, tgen_clients):
    # create the XML for the shadow.config.xml file
    root = etree.Element("shadow")
    root.set("bootstraptime", "{}".format(BOOTSTRAP_LENGTH_SECONDS)) # disable bandwidth limits and packet loss for first 5 minutes
    root.set("stoptime", "{}".format(SIMULATION_LENGTH_SECONDS)) # stop after 1 hour of simulated time
    root.set("preload", "{}/lib/libshadow-interpose.so".format(SHADOW_INSTALL_PREFIX))
    root.set("environment", "OPENSSL_ia32cap=~0x200000200000000;EVENT_NOSELECT=1;EVENT_NOPOLL=1;EVENT_NOKQUEUE=1;EVENT_NODEVPOLL=1;EVENT_NOEVPORT=1;EVENT_NOWIN32=1")

    topology = etree.SubElement(root, "topology")
    if args.atlas_path is None:
        topology.set("path", "{}/{}".format(CONFIG_DIRPATH, TMODEL_TOPOLOGY_FILENAME))
    else:
        topology.set("path", "{}".format(args.atlas_path))

    plugin = etree.SubElement(root, "plugin")
    plugin.set("id", "tor")
    plugin.set("path", "{}/lib/libshadow-plugin-tor.so".format(SHADOW_INSTALL_PREFIX))

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
        __add_xml_tor_relay(args, root, authority, is_authority=True)

    for pos in ['ge', 'e', 'g', 'm']:
        # use reverse to sort each class from fastest to slowest when assigning the id counter
        for (fp, relay) in sorted(relays[pos].items(), key=lambda kv: kv[1]['weight'], reverse=True):
            __add_xml_tor_relay(args, root, relay, is_authority=False)

    for server in tgen_servers:
        __add_xml_server(args, root, server)

    for client in perf_clients:
        __add_xml_perfclient(args, root, client)

    for client in tgen_clients:
        __add_xml_markovclient(args, root, client)

    xml_str = etree.tostring(root, pretty_print=True, xml_declaration=False)
    with open("{}/{}".format(args.prefix, SHADOW_CONFIG_FILENAME), 'wb') as configfile:
        configfile.write(xml_str)

def __add_xml_server(args, root, server):
    # this should be a relative path
    tgenrc = "{}/{}".format(CONFIG_DIRPATH, TGENRC_SERVER_FILENAME)

    host = etree.SubElement(root, SHADOW_XML_HOST_KEY)
    host.set("id", server['name'])
    host.set("countrycodehint", server['country_code'])
    host.set("bandwidthup", "{}".format(BW_1GBIT_KIB))
    host.set("bandwidthdown", "{}".format(BW_1GBIT_KIB))

    process = etree.SubElement(host, SHADOW_XML_PROCESS_KEY)
    process.set("plugin", "tgen")
    # tgen starts at the end of shadow's "bootstrap" phase
    process.set("starttime", "{}".format(BOOTSTRAP_LENGTH_SECONDS))
    process.set("arguments", tgenrc)

def __add_xml_perfclient(args, root, client):
    # these should be relative paths
    torrc = "{}/{}".format(CONFIG_DIRPATH, TORRC_PERFCLIENT_FILENAME)
    tgenrc = "{}/{}".format(CONFIG_DIRPATH, TGENRC_PERFCLIENT_FILENAME)
    __add_xml_tgen_client(args, root, client['name'], client['country_code'], torrc, tgenrc)

def __add_xml_markovclient(args, root, client):
    # these should be relative paths
    torrc = "{}/{}".format(CONFIG_DIRPATH, TORRC_MARKOVCLIENT_FILENAME)
    tgenrc_filename = TGENRC_MARKOVCLIENT_FILENAME_FMT.format(client['name'])
    tgenrc = "{}/{}/{}".format(CONFIG_DIRPATH, TGENRC_MARKOVCLIENT_DIRNAME, tgenrc_filename)
    __add_xml_tgen_client(args, root, client['name'], client['country_code'], torrc, tgenrc)

def __add_xml_tgen_client(args, root, name, country, torrc, tgenrc):
    host = etree.SubElement(root, SHADOW_XML_HOST_KEY)
    host.set("id", name)
    host.set("countrycodehint", country)
    host.set("bandwidthup", "{}".format(BW_1GBIT_KIB))
    host.set("bandwidthdown", "{}".format(BW_1GBIT_KIB))

    process = etree.SubElement(host, SHADOW_XML_PROCESS_KEY)
    process.set("plugin", "tor")
    process.set("preload", "tor-preload")
    process.set("starttime", "{}".format(BOOTSTRAP_LENGTH_SECONDS-60)) # start before boostrapping ends
    process.set("arguments", TOR_ARGS_FMT.format(name, torrc))

    oniontrace_start_time = BOOTSTRAP_LENGTH_SECONDS-60+1
    __add_xml_oniontrace(args, host, oniontrace_start_time, name)

    process = etree.SubElement(host, SHADOW_XML_PROCESS_KEY)
    process.set("plugin", "tgen")
    # tgen starts at the end of shadow's "bootstrap" phase, and may have its own startup delay
    process.set("starttime", "{}".format(BOOTSTRAP_LENGTH_SECONDS))
    process.set("arguments", tgenrc)

def __add_xml_tor_relay(args, root, relay, is_authority=False):
    # prepare items for the host element
    kib = int(round(int(relay['bandwidth_capacity']) / 1024.0))

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
        torrc = "{}/{}".format(CONFIG_DIRPATH, TORRC_AUTHORITY_FILENAME)
    elif "exitguard" in relay['nickname']:
        starttime = 2
        torrc = "{}/{}".format(CONFIG_DIRPATH, TORRC_EXITRELAY_FILENAME)
    elif "exit" in relay['nickname']:
        starttime = 3
        torrc = "{}/{}".format(CONFIG_DIRPATH, TORRC_EXITRELAY_FILENAME)
    elif "guard" in relay['nickname']:
        starttime = 4
        torrc = "{}/{}".format(CONFIG_DIRPATH, TORRC_NONEXITRELAY_FILENAME)
    else:
        starttime = 5
        torrc = "{}/{}".format(CONFIG_DIRPATH, TORRC_NONEXITRELAY_FILENAME)

    tor_args = TOR_ARGS_FMT.format(relay['nickname'], torrc)
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
        run_time = SIMULATION_LENGTH_SECONDS-start_time
        tracefile_path = "{}/{}/{}/oniontrace.csv".format(SHADOW_DATA_PATH, SHADOW_HOSTS_PATH, name)
        process.set("arguments", "Mode=record TorControlPort={} LogLevel=info RunTime={} TraceFile={}".format(TOR_CONTROL_PORT, run_time, tracefile_path))
