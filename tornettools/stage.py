import sys
import os
import logging
import lzma

from tornettools.generate_defaults import TMODEL_TOPOLOGY_FILENAME
from tornettools.util import dump_json_data
from tornettools.util_geoip import GeoIP

from ipaddress import IPv4Address
from multiprocessing import Pool, cpu_count
from statistics import median
from datetime import datetime, timezone

from stem import Flag
from stem.descriptor import parse_file

import networkx as nx

# this is parsed from the consensus files
class Relay():
    def __init__(self, fingerprints, address):
        self.fingerprints = fingerprints
        self.address = address
        # the length of this list indicates the number of consensuses the relay appeared in
        self.weights = []
        # a count of the number of consensuses in which the relay had the exit flag
        self.num_exit = 0
        # a count of the number of consensuses in which the relay had the guard flag
        self.num_guard = 0
        # bandwidth information parsed from server descriptor files
        self.bandwidths = Bandwidths()

# this is parsed from the server descriptor files
class Bandwidths():
    def __init__(self):
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
    consensuses = process(num_processes, consensus_paths, parse_consensus, lambda x: x)
    min_unix_time = min([c['pub_dt'] for c in consensuses])
    max_unix_time = max([c['pub_dt'] for c in consensuses])

    servdesc_paths = get_file_list(args.server_descriptor_path)
    logging.info("Processing {} server descriptor files from {}...".format(len(servdesc_paths), args.server_descriptor_path))
    sdesc_args = [[p, min_unix_time, max_unix_time] for p in servdesc_paths]
    serverdescs = process(num_processes, sdesc_args, parse_serverdesc, lambda x: x)

    families = families_from_serverdescs(serverdescs)

    geo = None
    if args.geoip_path is not None:
        geo = GeoIP(args.geoip_path)

    cluster_consensuses(families, geo, consensuses)

    relays = relays_from_consensuses(consensuses)
    network_stats = network_stats_from_consensuses(consensuses)
    #timestr = get_time_suffix(min_unix_time, max_unix_time)
    #logging.info("Found {} total unique relays during {} with a median network size of {} relays".format(len(relays), timestr, network_stats['med_count_total']))

    bandwidths = bandwidths_from_serverdescs(serverdescs)

    found_bandwidths = 0
    for relay in relays.values():
        for fingerprint in relay.fingerprints:
            cluster_bandwidths = []
            bandwidth = bandwidths.get(fingerprint)
            if bandwidth is not None:
                cluster_bandwidths.append({
                    'bandwidth_capacity': int(bandwidth.max_obs_bw),
                    'bandwidth_rate': int(median(bandwidth.bw_rates)) if len(bandwidth.bw_rates) > 0 else 0,
                    'bandwidth_burst': int(median(bandwidth.bw_bursts)) if len(bandwidth.bw_bursts) > 0 else 0,
                })
            if len(cluster_bandwidths) > 0:
                relay.bandwidth_capacity = max(b['bandwidth_capacity'] for b in cluster_bandwidths)
                relay.bandwidth_rate = max(b['bandwidth_rate'] for b in cluster_bandwidths)
                relay.bandwidth_burst = max(b['bandwidth_burst'] for b in cluster_bandwidths)
                found_bandwidths += 1
            else:
                relay.bandwidth_capacity = 0
                relay.bandwidth_rate = 0
                relay.bandwidth_burst = 0

    logging.info("We found bandwidth information for {} of {} relays".format(found_bandwidths, len(relays)))
    # for (k, v) in sorted(relays.items(), key=lambda kv: kv[1].bandwidths.max_obs_bw):
    #    logging.info("fp={} capacity={}".format(k, v.bandwidths.max_obs_bw))

    output = {
        'min_unix_time': min_unix_time,
        'max_unix_time': max_unix_time,
        'network_stats': network_stats,
        'relays': {}
    }

    for fingerprint in relays:
        r = relays[fingerprint]

        output['relays'][fingerprint] = {
            'fingerprints': r.fingerprints,
            'address': r.address,
            'running_frequency': float(len(r.weights)) / float(len(consensus_paths)), # frac consensuses in which relay appeared
            'guard_frequency': float(r.num_guard) / float(len(r.weights)), # when running, frac consensuses with exit flag
            'exit_frequency': float(r.num_exit) / float(len(r.weights)), # when running, frac consensuses with guard flag
            'weight': float(median(r.weights)) if len(r.weights) > 0 else 0.0,
            'bandwidth_capacity': r.bandwidth_capacity,
            'bandwidth_rate': r.bandwidth_rate,
            'bandwidth_burst': r.bandwidth_burst,
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
            print("interrupted, terminating process pool", file=sys.stderr)
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

    # valid_after is for V3 descriptors, V2 use net_status.published
    pub_dt = net_status.valid_after.replace(tzinfo=timezone.utc).timestamp()
    assert(pub_dt is not None)

    result = {
        'type': 'consensus',
        'pub_dt': pub_dt,
        'relays': relays,
    }

    return result

def get_cluster_key(families, geo, fingerprint, address):
    masked_ip = int(IPv4Address(address)) & 0xffff0000
    # We're using fairly wide IP address ranges; but we can separate
    # hosts that we know to be in different countries.
    country = geo.ip_to_country_code(address) if geo else None
    # family will be missing if we didn't have a descriptor
    # for the given relay.
    family = families.get(fingerprint) or f'<{fingerprint}>'
    return (masked_ip, country, family)

def cluster_consensuses(families, geo, consensuses):
    for c in consensuses:
        clustered_relays = {}
        for fingerprint, relay in c['relays'].items():
            clustered_relays.setdefault(get_cluster_key(families, geo, fingerprint, relay['address']), []).append((fingerprint, relay))
        new_relays = {}
        for pairs in clustered_relays.values():
            fingerprints = [p[0] for p in pairs]
            fingerprints.sort()

            relays = [p[1] for p in pairs]
            new_relays[sorted(fingerprints)[0]] = {
                'address': sorted([r['address'] for r in relays])[0],
                'weight': sum([r['weight'] for r in relays]),
                'is_guard': any([r['is_guard'] for r in relays]),
                'is_exit': any([r['is_exit'] for r in relays]),
                'fingerprints': fingerprints,
            }
        logging.info("Clustered {} relays into {} relays".format(len(c['relays']), len(new_relays)))
        c['relays'] = new_relays

        weights = {
            'total': 0,
            'exitguard': 0,
            'guard': 0,
            'exit': 0,
            'middle': 0,
        }
        counts = {
            'total': 0,
            'exitguard': 0,
            'guard': 0,
            'exit': 0,
            'middle': 0,
        }

        for r in new_relays.values():
            bw_weight = r['weight']
            weights["total"] += bw_weight
            counts["total"] += 1
            if r['is_guard'] and r['is_exit']:
                weights["exitguard"] += bw_weight
                counts["exitguard"] += 1
            elif r['is_guard']:
                weights["guard"] += bw_weight
                counts["guard"] += 1
            elif r['is_exit']:
                weights["exit"] += bw_weight
                counts["exit"] += 1
            else:
                weights["middle"] += bw_weight
                counts["middle"] += 1

        # weights are normalized on a per-consensus basis
        for r in new_relays.values():
            r['weight'] /= weights["total"]
        for position_type in weights:
            if position_type == "total":
                continue
            weights[position_type] /= weights["total"]

        c['weights'] = weights
        c['counts'] = counts

def add_bandwidths(consensuses, serverdescs):
    pass

def relays_from_consensuses(consensuses):
    relays = {}

    for consensus in consensuses:
        assert(consensus is not None)
        assert(consensus['type'] == 'consensus')
        for fingerprint, consensus_relay in consensus['relays'].items():
            r = relays.setdefault(fingerprint, Relay(consensus_relay['fingerprints'], consensus_relay['address']))

            r.weights.append(consensus_relay['weight'])

            if consensus_relay['is_exit']:
                r.num_exit += 1
            if consensus_relay['is_guard']:
                r.num_guard += 1

    return relays

def network_stats_from_consensuses(consensuses):
    network_stats = {}

    counts_t, counts_eg, counts_e, counts_g, counts_m = [], [], [], [], []
    weights_t, weights_eg, weights_e, weights_g, weights_m = [], [], [], [], []

    for consensus in consensuses:
        assert(consensus is not None)
        assert(consensus['type'] == 'consensus')

        weights_t.append(consensus['weights']['total'])
        weights_eg.append(consensus['weights']['exitguard'])
        weights_g.append(consensus['weights']['guard'])
        weights_e.append(consensus['weights']['exit'])
        weights_m.append(consensus['weights']['middle'])

        counts_t.append(consensus['counts']['total'])
        counts_eg.append(consensus['counts']['exitguard'])
        counts_g.append(consensus['counts']['guard'])
        counts_e.append(consensus['counts']['exit'])
        counts_m.append(consensus['counts']['middle'])

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

    return network_stats

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

    # Convert fingerprints in family to match fingerprints we use everywhere else.
    # i.e. remove the $ prefix and ensure upper-case.
    family = set([fp[1:].upper() for fp in relay.family])

    assert(family is not None)
    # Ensure own fingerprint is in family
    family.add(relay.fingerprint)

    result = {
        'type': 'serverdesc',
        'family': family,
        'pub_dt': relay.published,
        'fprint': relay.fingerprint,
        'address': relay.address,
        'bw_obs': relay.observed_bandwidth,
        'bw_rate': avg_bw if avg_bw is not None else 0,
        'bw_burst': bst_bw if bst_bw is not None else 0,
        'bw_adv': advertised_bw,
    }

    return result

def families_from_serverdescs(serverdescs):
    family_sets = {}

    for sd in serverdescs:
        if sd is None:
            continue

        if sd['type'] != 'serverdesc':
            continue

        # Each relay's family is the union of all the families it has published.
        family_sets.setdefault(sd['fprint'], set()).update(sd['family'])

    # Remove non-mutuals
    for fp, family in family_sets.items():
        mutuals = set()
        for other_fp in family:
            other_family = family_sets.get(other_fp)
            if other_family is not None and fp in other_family:
                mutuals.add(other_fp)
        # Mutate `family` to contain only mutuals; don't reassign since we're iterating through the dict.
        if len(family) != len(mutuals):
            logging.info(f"XXX Dropping non-mutuals shrunk family from {len(family)} to {len(mutuals)}")
        family.clear()
        family.update(mutuals)

    # Add transitives
    for fp, family in family_sets.items():
        transitives = set()
        to_process = family_sets[fp].copy()
        while len(to_process) > 0:
            other_fp = to_process.pop()
            if other_fp in transitives:
                # Already processed
                continue
            transitives.add(other_fp)
            to_process.update(family_sets[other_fp])
        if len(family) != len(transitives):
            logging.info(f"XXX Adding transitives grew family from {len(family)} to {len(transitives)}")
        family.clear()
        family.update(transitives)

    # Convert to normalized string
    families = {}
    for fp, family_set in family_sets.items():
        families[fp] = str(sorted(list(family_set)))

    return families

def bandwidths_from_serverdescs(serverdescs):
    bandwidths = {}

    for sd in serverdescs:
        if sd is None:
            continue

        if sd['type'] != 'serverdesc':
            continue

        bandwidths.setdefault(sd['fprint'], Bandwidths())

        b = bandwidths[sd['fprint']]

        b.max_obs_bw = max(b.max_obs_bw, sd['bw_obs'])
        b.bw_rates.append(sd['bw_rate'])
        b.bw_bursts.append(sd['bw_burst'])

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
