import sys
import os
import logging
import lzma
import datetime

from tornettools.generate_defaults import TMODEL_TOPOLOGY_FILENAME
from tornettools.util import dump_json_data
from tornettools.util_geoip import GeoIP

from multiprocessing import Pool, cpu_count
from statistics import median
from datetime import datetime, timezone

from stem import Flag
from stem.descriptor import parse_file

import networkx as nx

# this is parsed from the consensus files
class Relay():
    def __init__(self, fingerprint, address):
        self.fingerprint = fingerprint
        self.address = address
        # the length of this list indicates the number of consensuses the relay appeared in
        self.weights = []
        # a count of the number of consensuses in which the relay had the exit flag
        self.num_exit = 0
        # a count of the number of consensuses in which the relay had the guard flag
        self.num_guard = 0
        # bandwidth information parsed from server descriptor files
        self.bandwidths = Bandwidths(fingerprint)

# this is parsed from the server descriptor files
class Bandwidths():
    def __init__(self, fingerprint):
        self.fingerprint = fingerprint
        self.max_obs_bw = 0
        self.bw_rates = []
        self.bw_bursts = []

def run(args):
    min_unix_time, max_unix_time = stage_relays(args)
    stage_users(args, min_unix_time, max_unix_time)
    stage_graph(args)

# this function parses a userstats-relay-country.csv file from
# https://metrics.torproject.org/userstats-relay-country.csv
def stage_users(args, min_unix_time, max_unix_time):
    codes_by_unix_time = {}

    logging.info("Processing user file from {}...".format(args.user_stats_path))

    with open(args.user_stats_path, 'r') as infile:
        for line in infile:
            # skip the header; the first 4 chars are the year, e.g., '2011'
            if line[0:2] != '20':
                continue

            parts = line.strip().split(',')

            date = str(parts[0]) # like '2019-01-01'
            country_code = str(parts[1]) # like 'us'
            user_count = int(parts[2]) # like '14714'

            dt = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            unix_time = int(dt.strftime("%s")) # returns stamp like 1548910800

            if unix_time < min_unix_time or unix_time > max_unix_time:
                continue

            filter = set(['', 'a1', 'a2', '??'])
            if country_code in filter:
                continue

            codes_by_unix_time.setdefault(unix_time, {}).setdefault(country_code, 0)
            codes_by_unix_time[unix_time][country_code] += user_count

    # compute probs of each country over time
    probs_by_country_code = {}
    for unix_time in codes_by_unix_time:
        total_user_count = float(sum(codes_by_unix_time[unix_time].values()))

        for country_code in codes_by_unix_time[unix_time]:
            prob = codes_by_unix_time[unix_time][country_code] / total_user_count
            probs_by_country_code.setdefault(country_code, []).append(prob)

    # get median country prob for each
    output = {}
    for country_code in probs_by_country_code:
        probs = probs_by_country_code[country_code]
        med_prob = median(probs) if len(probs) > 0 else 0.0
        output.setdefault(country_code, med_prob)

    # re-normalize
    total_prob = float(sum(output.values()))
    for country_code in output:
        output[country_code] = output[country_code] / total_prob

    timesuffix = get_time_suffix(min_unix_time, max_unix_time)
    user_info_path = f"{args.prefix}/userinfo_staging_{timesuffix}.json"
    logging.info("Writing user info to {}".format(user_info_path))
    dump_json_data(output, user_info_path, compress=False)

# this function parses consensus and server descriptor files from, e.g.,
# https://collector.torproject.org/archive/relay-descriptors/consensuses/consensuses-2019-01.tar.xz
# https://collector.torproject.org/archive/relay-descriptors/server-descriptors/server-descriptors-2019-01.tar.xz
def stage_relays(args):
    num_processes = args.nprocesses if args.nprocesses > 0 else cpu_count()

    logging.info("Starting to process Tor metrics data using {} processes".format(num_processes))

    consensus_paths = get_file_list(args.consensus_path)
    logging.info("Processing {} consensus files from {}...".format(len(consensus_paths), args.consensus_path))
    relays, min_unix_time, max_unix_time, network_stats = process(num_processes, consensus_paths, parse_consensus, combine_parsed_consensus_results)

    servdesc_paths = get_file_list(args.server_descriptor_path)
    logging.info("Processing {} server descriptor files from {}...".format(len(servdesc_paths), args.server_descriptor_path))
    sdesc_args = [[p, min_unix_time, max_unix_time] for p in servdesc_paths]
    bandwidths = process(num_processes, sdesc_args, parse_serverdesc, combine_parsed_serverdesc_results)

    found_bandwidths = 0
    for fingerprint in relays:
        if fingerprint in bandwidths:
            # overwrite empty bandwidth with parsed bandwidth info
            relays[fingerprint].bandwidths = bandwidths[fingerprint]
            found_bandwidths += 1

    logging.info("We found bandwidth information for {} of {} relays".format(found_bandwidths, len(relays)))
    # for (k, v) in sorted(relays.items(), key=lambda kv: kv[1].bandwidths.max_obs_bw):
    #    logging.info("fp={} capacity={}".format(k, v.bandwidths.max_obs_bw))

    geo = None
    if args.geoip_path is not None:
        geo = GeoIP(args.geoip_path)

    output = {
        'min_unix_time': min_unix_time,
        'max_unix_time': max_unix_time,
        'network_stats': network_stats,
        'relays': {}
    }

    for fingerprint in relays:
        r = relays[fingerprint]

        output['relays'][fingerprint] = {
            'fingerprint': r.fingerprint,
            'address': r.address,
            'running_frequency': float(len(r.weights)) / float(len(consensus_paths)), # frac consensuses in which relay appeared
            'guard_frequency': float(r.num_guard) / float(len(r.weights)), # when running, frac consensuses with exit flag
            'exit_frequency': float(r.num_exit) / float(len(r.weights)), # when running, frac consensuses with guard flag
            'weight': float(median(r.weights)) if len(r.weights) > 0 else 0.0,
            'bandwidth_capacity': int(r.bandwidths.max_obs_bw),
            'bandwidth_rate': int(median(r.bandwidths.bw_rates)) if len(r.bandwidths.bw_rates) > 0 else 0,
            'bandwidth_burst': int(median(r.bandwidths.bw_bursts)) if len(r.bandwidths.bw_bursts) > 0 else 0,
        }

        if geo is not None:
            output['relays'][fingerprint]['country_code'] = geo.ip_to_country_code(r.address)

    timesuffix = get_time_suffix(min_unix_time, max_unix_time)
    relay_info_path = f"{args.prefix}/relayinfo_staging_{timesuffix}.json"
    logging.info("Writing relay info to {}".format(relay_info_path))
    dump_json_data(output, relay_info_path, compress=False)

    return min_unix_time, max_unix_time

def stage_graph(args):
    atlas_path = os.path.join(args.tmodel_git_path, "data/shadow/network/", TMODEL_TOPOLOGY_FILENAME + ".xz")

    with lzma.open(atlas_path) as f:
        logging.info(f"Reading compressed network graph {atlas_path}")
        network = nx.readwrite.gml.read_gml(f, label='id')
        logging.info("Finished reading network graph")

    # create new graph and copy only the nodes
    network = nx.classes.function.create_empty_copy(network)

    # it takes networkx a few minutes to read the atlas graph, so we save a smaller graph containing
    # only the atlas graph nodes so that the 'generate' step can read these nodes much quicker
    network_info_path = f"{args.prefix}/networkinfo_staging.gml"
    nx.readwrite.gml.write_gml(network, network_info_path)

def get_file_list(dir_path):
    file_paths = []
    for root, _, filenames in os.walk(dir_path):
        for filename in filenames:
            file_paths.append(os.path.join(root, filename))
    return file_paths

def get_time_suffix(min_unix_time, max_unix_time):
    min_str = datetime.fromtimestamp(min_unix_time, timezone.utc).strftime("%Y-%m-%d")
    max_str = datetime.fromtimestamp(max_unix_time, timezone.utc).strftime("%Y-%m-%d")
    return "{}--{}".format(min_str, max_str)

def process(num_processes, file_paths, map_func, reduce_func):
    results = []

    if num_processes > 1:
        p = Pool(num_processes)
        try:
            async_result = p.map_async(map_func, file_paths)
            while not async_result.ready():
                async_result.wait(1)
            results = async_result.get()
        except KeyboardInterrupt:
            print >> sys.stderr, "interrupted, terminating process pool"
            p.terminate()
            p.join()
            sys.exit(1)
    else:
        for path in file_paths:
            results.append(map_func(path))

    return reduce_func(results)

def parse_consensus(path):
    net_status = next(parse_file(path, document_handler='DOCUMENT', validate=False))

    relays = {}
    weights = {"total": 0, "exit": 0, "guard": 0, "exitguard": 0, "middle": 0}
    counts = {"total": 0, "exit": 0, "guard": 0, "exitguard": 0, "middle": 0}

    for (fingerprint, router_entry) in net_status.routers.items():
        if Flag.BADEXIT in router_entry.flags or Flag.RUNNING not in router_entry.flags or Flag.VALID not in router_entry.flags:
            continue

        relays.setdefault(fingerprint, {})

        relays[fingerprint]['address'] = router_entry.address
        relays[fingerprint]['weight'] = router_entry.bandwidth

        if Flag.GUARD in router_entry.flags and Flag.FAST in router_entry.flags and Flag.STABLE in router_entry.flags:
            relays[fingerprint]['is_guard'] = True
        else:
            relays[fingerprint]['is_guard'] = False

        if Flag.EXIT in router_entry.flags and router_entry.exit_policy.is_exiting_allowed():
            relays[fingerprint]['is_exit'] = True
        else:
            relays[fingerprint]['is_exit'] = False

        # fill in the weights
        bw_weight = float(router_entry.bandwidth)

        weights["total"] += bw_weight
        counts["total"] += 1
        if relays[fingerprint]['is_guard'] and relays[fingerprint]['is_exit']:
            weights["exitguard"] += bw_weight
            counts["exitguard"] += 1
        elif relays[fingerprint]['is_guard']:
            weights["guard"] += bw_weight
            counts["guard"] += 1
        elif relays[fingerprint]['is_exit']:
            weights["exit"] += bw_weight
            counts["exit"] += 1
        else:
            weights["middle"] += bw_weight
            counts["middle"] += 1

    # weights are normalized on a per-consensus basis
    for fingerprint in relays:
        relays[fingerprint]['weight'] /= weights["total"]
    for position_type in weights:
        if position_type == "total":
            continue
        weights[position_type] /= weights["total"]

    result = {
        'type': 'consensus',
        'pub_dt': net_status.valid_after, # valid_after is for V3 descriptors, V2 use net_status.published
        'relays': relays,
        'weights': weights,
        'counts': counts,
    }

    return result

def combine_parsed_consensus_results(results):
    relays = {}
    network_stats = {}
    min_unix_time, max_unix_time = None, None

    counts_t, counts_eg, counts_e, counts_g, counts_m = [], [], [], [], []
    weights_t, weights_eg, weights_e, weights_g, weights_m = [], [], [], [], []

    for result in results:
        if result is None:
            continue

        if result['type'] != 'consensus':
            continue

        if result['pub_dt'] is not None:
            unix_time = result['pub_dt'].replace(tzinfo=timezone.utc).timestamp()
            if min_unix_time is None or unix_time < min_unix_time:
                min_unix_time = unix_time
            if max_unix_time is None or unix_time > max_unix_time:
                max_unix_time = unix_time

        weights_t.append(result['weights']['total'])
        weights_eg.append(result['weights']['exitguard'])
        weights_g.append(result['weights']['guard'])
        weights_e.append(result['weights']['exit'])
        weights_m.append(result['weights']['middle'])

        counts_t.append(result['counts']['total'])
        counts_eg.append(result['counts']['exitguard'])
        counts_g.append(result['counts']['guard'])
        counts_e.append(result['counts']['exit'])
        counts_m.append(result['counts']['middle'])

        for fingerprint in result['relays']:
            relays.setdefault(fingerprint, Relay(fingerprint, result['relays'][fingerprint]['address']))

            r = relays[fingerprint]

            r.weights.append(result['relays'][fingerprint]['weight'])

            if result['relays'][fingerprint]['is_exit']:
                r.num_exit += 1
            if result['relays'][fingerprint]['is_guard']:
                r.num_guard += 1

    network_stats = {
        # the counts are whole numbers
        'med_count_exitguard': int(round(median(counts_eg))),
        'med_count_guard': int(round(median(counts_g))),
        'med_count_exit': int(round(median(counts_e))),
        'med_count_middle': int(round(median(counts_m))),
        'med_count_total': int(round(median(counts_t))),
        # the weights are normalized (fractional)
        'med_weight_exitguard': float(median(weights_eg)),
        'med_weight_guard': float(median(weights_g)),
        'med_weight_exit': float(median(weights_e)),
        'med_weight_middle': float(median(weights_m)),
        'med_weight_total': 1.0, # for completeness
    }

    timestr = get_time_suffix(min_unix_time, max_unix_time)
    logging.info("Found {} total unique relays during {} with a median network size of {} relays".format(len(relays), timestr, network_stats['med_count_total']))

    return relays, min_unix_time, max_unix_time, network_stats

# this func is run by helper processes in process pool
def parse_serverdesc(args):
    path, min_time, max_time = args
    relay = next(parse_file(path, document_handler='DOCUMENT', descriptor_type='server-descriptor 1.0', validate=False))

    if relay is None:
        return None

    pub_ts = relay.published.replace(tzinfo=timezone.utc).timestamp()
    if pub_ts < min_time or pub_ts > max_time:
        return None

    if relay.observed_bandwidth is None:
        return None

    advertised_bw = relay.observed_bandwidth

    avg_bw = relay.average_bandwidth
    bst_bw = relay.burst_bandwidth

    if avg_bw is not None and avg_bw < advertised_bw:
        advertised_bw = avg_bw
    if bst_bw is not None and bst_bw < advertised_bw:
        advertised_bw = bst_bw

    result = {
        'type': 'serverdesc',
        'pub_dt': relay.published,
        'fprint': relay.fingerprint,
        'address': relay.address,
        'bw_obs': relay.observed_bandwidth,
        'bw_rate': avg_bw if avg_bw is not None else 0,
        'bw_burst': bst_bw if bst_bw is not None else 0,
        'bw_adv': advertised_bw,
    }

    return result

def combine_parsed_serverdesc_results(results):
    bandwidths = {}

    for result in results:
        if result is None:
            continue

        if result['type'] != 'serverdesc':
            continue

        bandwidths.setdefault(result['fprint'], Bandwidths(result['fprint']))

        b = bandwidths[result['fprint']]

        b.max_obs_bw = max(b.max_obs_bw, result['bw_obs'])
        b.bw_rates.append(result['bw_rate'])
        b.bw_bursts.append(result['bw_burst'])

    return bandwidths

def parse_extrainfo(path): # unused right now, but might be useful
    xinfo = next(parse_file(path, document_handler='DOCUMENT', descriptor_type='extra-info 1.0', validate=False))

    read_max_rate, read_avg_rate = 0, 0
    if xinfo.read_history_values is not None and xinfo.read_history_interval is not None:
        read_max_rate = int(max(xinfo.read_history_values) / xinfo.read_history_interval)
        read_avg_rate = int((sum(xinfo.read_history_values) / len(xinfo.read_history_values)) / xinfo.read_history_interval)

    write_max_rate, write_avg_rate = 0, 0
    if xinfo.write_history_values is not None and xinfo.write_history_interval is not None:
        write_max_rate = int(max(xinfo.write_history_values) / xinfo.write_history_interval)
        write_avg_rate = int((sum(xinfo.write_history_values) / len(xinfo.write_history_values)) / xinfo.write_history_interval)

    result = {
        'type': type,
        'pub_dt': xinfo.published,
        'fprint': xinfo.fingerprint,
        'nickname': xinfo.nickname,
        'bytes_read_max': read_max_rate,
        'bytes_read_avg': read_avg_rate,
        'bytes_write_max': write_max_rate,
        'bytes_write_avg': write_avg_rate,
    }

    return result
