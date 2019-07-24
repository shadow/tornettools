import sys
import os
import json
import logging

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

    logging.info("Constructing Shadow config XML file")
    generate_shadow_config(args, authorities, relays)

def generate_shadow_config(args, authorities, relays):
    # create the XML for the shadow.config.xml file
    root = etree.Element("shadow")
    root.set("bootstraptime", "300") # disable bandwidth limits and packet loss for first 5 minutes
    root.set("stoptime", "3600") # stop after 1 hour of simulated time
    root.set("preload", "{}/lib/libshadow-interpose.so".format(SHADOW_INSTALL_PREFIX))
    root.set("environment", "OPENSSL_ia32cap=~0x200000200000000;EVENT_NOSELECT=1;EVENT_NOPOLL=1;EVENT_NOKQUEUE=1;EVENT_NODEVPOLL=1;EVENT_NOEVPORT=1;EVENT_NOWIN32=1")

    topology = etree.SubElement(root, "topology")
    topology.set("path", "{}/share/atlas.201801.shadow113.graphml.xml".format(SHADOW_INSTALL_PREFIX))

    plugin = etree.SubElement(root, "plugin")
    plugin.set("id", "tor")
    plugin.set("path", "{}/lib/libshadow-plugin-tor.so".format(SHADOW_INSTALL_PREFIX))

    plugin = etree.SubElement(root, "plugin")
    plugin.set("id", "tor-preload")
    plugin.set("path", "{}/lib/libshadow-preload-tor.so".format(SHADOW_INSTALL_PREFIX))

    plugin = etree.SubElement(root, "plugin")
    plugin.set("id", "torctl")
    plugin.set("path", "{}/lib/libshadow-plugin-torctl.so".format(SHADOW_INSTALL_PREFIX))

    plugin = etree.SubElement(root, "plugin")
    plugin.set("id", "tgen")
    plugin.set("path", "{}/bin/tgen".format(SHADOW_INSTALL_PREFIX))

    for (fp, authority) in sorted(authorities.items(), key=lambda kv: kv[1]['nickname']):
        add_xml_relay(root, authority, is_authority=True)

    for pos in ['ge', 'e', 'g', 'm']:
        # use reverse to sort each class from fastest to slowest when assigning the id counter
        for (fp, relay) in sorted(relays[pos].items(), key=lambda kv: kv[1]['weight'], reverse=True):
            add_xml_relay(root, relay, is_authority=False)

    xml_str = etree.tostring(root, pretty_print=True, xml_declaration=False)
    with open("{}/{}".format(args.prefix, SHADOW_CONFIG_FILENAME), 'wb') as configfile:
        configfile.write(xml_str)

def add_xml_relay(root, relay, is_authority=False):
    # prepare items for the host element
    kib = int(round(int(relay['bandwidth_capacity']) / 1024.0))

    # add the host element and attributes
    host = etree.SubElement(root, "host")
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

    tor_args = DEFAULT_TOR_ARGS.format(relay['nickname'], torrc)
    if not is_authority:
        # Tor enforces a min rate for relays
        rate = max(BW_RATE_MIN, relay['bandwidth_rate'])
        burst = max(BW_RATE_MIN, relay['bandwidth_burst'])
        tor_args += " --BandwidthRate {} --BandwidthBurst {}".format(rate, burst)

    process = etree.SubElement(host, "process")

    process.set("plugin", "tor")
    process.set("preload", "tor-preload")
    process.set("starttime", "{}".format(starttime))
    process.set("arguments", "{}".format(tor_args))

    process = etree.SubElement(host, "process")

    process.set("plugin", "torctl")
    process.set("starttime", "{}".format(starttime+1))
    process.set("arguments", "localhost 9051 BW")
