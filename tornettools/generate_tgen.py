import os
import json
import logging
import stem.process
import stem.connection
import tempfile

from math import ceil
from numpy.random import choice, uniform
from random import randrange

from networkx import DiGraph, write_graphml

from tornettools.generate_defaults import (CONFIG_DIRNAME, ONIONPERF_COUNTRY_CODES,
                                           PRIVCOUNT_PERIODS_PER_DAY, SHADOW_HOSTS_PATH,
                                           SHADOW_TEMPLATE_PATH, TGENRC_FLOWMODEL_FILENAME_FMT,
                                           TGENRC_MARKOVCLIENT_FILENAME,
                                           TGENRC_PERFCLIENT_EXIT_FILENAME,
                                           TGENRC_PERFCLIENT_HS_FILENAME, TGENRC_SERVER_FILENAME,
                                           TGEN_CLIENT_MIN_COUNT, TGEN_SERVER_PORT,
                                           TMODEL_PACKETMODEL_FILENAME, TMODEL_STREAMMODEL_FILENAME,
                                           TOR_SOCKS_PORT, get_host_rel_conf_path)
from tornettools.util import load_json_data

def __round_or_ceil(x):
    """Round to the nearest integer, except don't round down to zero.

    Useful for avoiding inadvertent 0 counts when scaling down to small networks
    while still allowing explicit zero counts (e.g. --torperf_scale=0).

    1.8 => 2
    1.1 => 1
    0.8 => 1
    0.1 => 1
    0.0 => 0
    """
    res = round(x)
    if res == 0:
        res = ceil(x)
    return res

def generate_tgen_config(args, tgen_clients, exit_peers, hs_peers):
    # make sure the config directory exists
    abs_conf_path = "{}/{}".format(args.prefix, CONFIG_DIRNAME)
    if not os.path.exists(abs_conf_path):
        os.makedirs(abs_conf_path)

    hosts_prefix = "{}/{}/{}".format(args.prefix, SHADOW_TEMPLATE_PATH, SHADOW_HOSTS_PATH)
    if not os.path.exists(hosts_prefix):
        os.makedirs(hosts_prefix)

    __generate_tgenrc_server(abs_conf_path)
    __generate_tgenrc_perfclient(exit_peers, os.path.join(abs_conf_path, TGENRC_PERFCLIENT_EXIT_FILENAME))
    __generate_tgenrc_perfclient(hs_peers, os.path.join(abs_conf_path, TGENRC_PERFCLIENT_HS_FILENAME))
    __generate_tgenrc_markovclients(abs_conf_path, hosts_prefix, tgen_clients)
    __generate_tgen_traffic_models(args, abs_conf_path)

def __generate_tgenrc_server(abs_conf_path):
    G = DiGraph()
    G.add_node("start", serverport="{}".format(TGEN_SERVER_PORT), loglevel="message", stallout="0 seconds", timeout="0 seconds")
    path = "{}/{}".format(abs_conf_path, TGENRC_SERVER_FILENAME)
    write_graphml(G, path)

def __generate_tgenrc_perfclient(server_peers, path):
    server_peers = ','.join(server_peers)
    proxy = "localhost:{}".format(TOR_SOCKS_PORT)

    G = DiGraph()

    # need info level logs so we can collect incremental download times, which we
    # later use for comparing the client goodput metric with Tor metrics data
    G.add_node("start", loglevel="info", socksproxy=proxy, peers=server_peers, packetmodelmode="path")

    # torperf uses 5 minute pause, but we reduce it for shadow
    G.add_node("pause", time="1 minute")

    # torperf uses 300, 1800, and 3600 second timeouts, but we reduce them for shadow
    G.add_node("stream_50k", sendsize="1000 bytes", recvsize="50 KiB", stallout="0 seconds", timeout="15 seconds")
    G.add_node("stream_1m", sendsize="1000 bytes", recvsize="1 MiB", stallout="0 seconds", timeout="60 seconds")
    G.add_node("stream_5m", sendsize="1000 bytes", recvsize="5 MiB", stallout="0 seconds", timeout="120 seconds")

    G.add_edge("start", "pause")

    # after the pause, we start another pause timer while *at the same time* choosing one of
    # the file sizes and downloading it from one of the servers in the server pool
    G.add_edge("pause", "pause")

    # these are chosen with weighted probability, change edge 'weight' attributes to adjust probability
    G.add_edge("pause", "stream_50k", weight="12.0")
    G.add_edge("pause", "stream_1m", weight="2.0")
    G.add_edge("pause", "stream_5m", weight="1.0")

    write_graphml(G, path)

def __generate_tgenrc_markovclients(abs_conf_path, hosts_prefix, tgen_clients):
    for tgen_client in tgen_clients:
        __generate_tgenrc_markovclient(abs_conf_path, hosts_prefix, tgen_client)

def __generate_tgenrc_markovclient(abs_conf_path, hosts_prefix, tgen_client):
    server_peers = ','.join(tgen_client['peers'])
    circuit_rate_exp = float(tgen_client['circuit_rate_exp'])
    usec_per_circ = int(round(1.0 / circuit_rate_exp))

    # write the flow model that will instruct tgen when to build new circuits
    # tgen clients with the same rate param can share flow model files
    flowmodelname = TGENRC_FLOWMODEL_FILENAME_FMT.format(usec_per_circ)
    flowmodel_abspath = "{}/{}".format(abs_conf_path, flowmodelname)
    if not os.path.exists(flowmodel_abspath):
        __generate_tgen_flowmodel(flowmodel_abspath, circuit_rate_exp)

    # we need a new tgenrc for each markov client, even though some of them share the flow model,
    # because each of them gets new random seeds
    socksauthseed = "{}".format(randrange(1, 1000000000))
    markovmodelseed = "{}".format(randrange(1, 1000000000))

    # we use the following paths in the tgenrc, they should be relative
    fmodel_relpath = get_host_rel_conf_path(flowmodelname)
    smodel_relpath = get_host_rel_conf_path(TMODEL_STREAMMODEL_FILENAME)
    pmodel_relpath = get_host_rel_conf_path(TMODEL_PACKETMODEL_FILENAME)

    # at startup, delay walking the tgen graph for a random period in the range [1,60] seconds
    startup_delay = "{}".format(randrange(60) + 1)

    # now generate the tgenrc graphml file
    G = DiGraph()

    proxy = "localhost:{}".format(TOR_SOCKS_PORT)

    # use a absolute timeout of 10 minutes (the default circuit lifetime)
    # idle streams stallout after 5 minutes (the default timeout in apache)
    G.add_node("start",
               loglevel=tgen_client['log_level'],
               time=startup_delay,
               socksproxy=proxy,
               peers=server_peers,
               stallout="5 minutes",
               timeout="10 minutes"
               )
    G.add_node("traffic",
               socksauthseed=socksauthseed,
               flowmodelpath=fmodel_relpath,
               streammodelpath=smodel_relpath,
               packetmodelpath=pmodel_relpath,
               packetmodelmode="path",
               markovmodelseed=markovmodelseed
               )

    # we loop generating traffic until the experiment ends
    G.add_edge("start", "traffic")
    G.add_edge("traffic", "traffic")

    host_dir = "{}/{}".format(hosts_prefix, tgen_client['name'])
    if not os.path.exists(host_dir):
        os.makedirs(host_dir)

    tgenrc_path = "{}/{}".format(host_dir, TGENRC_MARKOVCLIENT_FILENAME)
    write_graphml(G, tgenrc_path)

def __generate_tgen_flowmodel(path, rate):
    G = DiGraph()

    G.add_node('s0', type="state", name='start')
    G.add_node('s1', type="state", name='generate')

    G.add_edge('s0', 's1', type='transition', weight=1.0)
    G.add_edge('s1', 's1', type='transition', weight=1.0)

    G.add_node('o1', type="observation", name='+')

    G.add_edge('s1', 'o1', type='emission', weight=1.0, distribution='exponential', param_rate=rate)

    write_graphml(G, path)

def __generate_tgen_traffic_models(args, abs_conf_path):
    # packet model taken from measurement 8-9 in the tmodel ccs2018 paper
    privcount_packetmodel_path = '{}/data/privcount/measurement8/9/privcount.traffic.model.1522196794-1522283493.json'.format(args.tmodel_git_path)
    tgen_packetmodel_path = '{}/{}'.format(abs_conf_path, TMODEL_PACKETMODEL_FILENAME)
    __generate_tgen_markov_model(privcount_packetmodel_path, "packet_model", tgen_packetmodel_path)

    # stream model taken from measurement 9-9 in the tmodel ccs2018 paper
    privcount_streammodel_path = '{}/data/privcount/measurement9/9/privcount.traffic.model.1524154791-1524241191.json'.format(args.tmodel_git_path)
    tgen_streammodel_path = '{}/{}'.format(abs_conf_path, TMODEL_STREAMMODEL_FILENAME)
    __generate_tgen_markov_model(privcount_streammodel_path, "stream_model", tgen_streammodel_path)

def __generate_tgen_markov_model(privcount_tmodel_src_path, tmodel_key, tgen_tmodel_dst_path):
    with open(privcount_tmodel_src_path, 'r') as privcount_tmodel_file:
        tmodel = json.load(privcount_tmodel_file)
        hmm = tmodel[tmodel_key]

    state_ctr = 0
    obs_ctr = 0
    name_to_id = {}

    G = DiGraph()

    id = 's{}'.format(state_ctr)
    name = __convert_privcount_key_to_tgen_key("start")
    name_to_id[name] = id
    state_ctr += 1
    G.add_node(id, type='state', name=name)

    # add the state nodes and the observations nodes
    for state in hmm['state_space']:
        id = 's{}'.format(state_ctr)
        name = __convert_privcount_key_to_tgen_key(state)
        name_to_id[name] = id
        state_ctr += 1
        G.add_node(id, type='state', name=name)

    for observation in hmm['observation_space']:
        id = 'o{}'.format(obs_ctr)
        name = __convert_privcount_key_to_tgen_key(observation)
        name_to_id[name] = id
        obs_ctr += 1
        G.add_node(id, type="observation", name=name)

    # edges between states are called transitions
    for state in hmm['start_probability']:
        srcid = name_to_id[__convert_privcount_key_to_tgen_key("start")]
        dstid = name_to_id[__convert_privcount_key_to_tgen_key(state)]
        p = float(hmm['start_probability'][state])
        G.add_edge(srcid, dstid, type='transition', weight=p)

    for srcstate in hmm['transition_probability']:
        for dststate in hmm['transition_probability'][srcstate]:
            srcid = name_to_id[__convert_privcount_key_to_tgen_key(srcstate)]
            dstid = name_to_id[__convert_privcount_key_to_tgen_key(dststate)]
            p = float(hmm['transition_probability'][srcstate][dststate])
            G.add_edge(srcid, dstid, type='transition', weight=p)

    # edges from states to observations are called emissions
    for state in hmm['emission_probability']:
        for observation in hmm['emission_probability'][state]:
            srcid = name_to_id[__convert_privcount_key_to_tgen_key(state)]
            dstid = name_to_id[__convert_privcount_key_to_tgen_key(observation)]

            # params format is [prob, lognorm_mu, lognorm_sigma, exp_lambda]
            params = hmm['emission_probability'][state][observation]
            p = float(params[0])

            G.add_edge(srcid, dstid, type='emission', weight=p)

            # after an emission happens, we have parameters to tell us how long to wait
            # until making the next transition

            if observation == 'F':
                # this observation is terminal, so the delay doesnt matter
                G[srcid][dstid]['distribution'] = "uniform"
                G[srcid][dstid]['param_low'] = 0.0
                G[srcid][dstid]['param_high'] = 0.0
            else:
                lognorm_mu = float(params[1])
                lognorm_sigma = float(params[2])
                exp_lambda = float(params[3])

                if exp_lambda > 0.0:
                    G[srcid][dstid]['distribution'] = "exponential"
                    G[srcid][dstid]['param_rate'] = exp_lambda
                else:
                    G[srcid][dstid]['distribution'] = "lognormal"
                    G[srcid][dstid]['param_location'] = lognorm_mu
                    G[srcid][dstid]['param_scale'] = lognorm_sigma

    write_graphml(G, tgen_tmodel_dst_path)

def __convert_privcount_key_to_tgen_key(str):
    if str == "s0Active":
        return "Active"
    elif str == "s1Dwell":
        return "Dwell"
    elif str == "s2End":
        return "End"
    elif str == "$":
        return "+"
    else:
        return str

def __calculate_number_of_servers(args, n_exit_clients, n_hs_clients):
    n_exit_servers = __round_or_ceil(n_exit_clients * args.server_scale)
    n_hs_servers = __round_or_ceil(n_hs_clients * args.server_scale)

    return (n_exit_servers, n_hs_servers)

def get_servers(args, clients):
    tgen_servers = []

    n_exit_clients = len([x for x in clients if not x['is_hs_client']])
    n_hs_clients = len([x for x in clients if x['is_hs_client']])

    (n_exit_servers, n_hs_servers) = __calculate_number_of_servers(args, n_exit_clients, n_hs_clients)

    # each server will be placed in a country
    # right now we use client stats to decide where to place servers
    # we may want to update this to use server-specific country distributions
    country_codes, country_probs = __load_user_data(args)

    keys = generate_onion_service_keys(args.torexe, n_hs_servers)

    server_counter = 0

    for i in range(n_exit_servers):
        chosen_country_code = choice(country_codes, p=country_probs)
        server = {
            'name': 'server{}exit'.format(server_counter + 1),
            'country_code': chosen_country_code,
            'is_hs_server': False,
        }
        tgen_servers.append(server)
        server_counter += 1

    for i in range(n_hs_servers):
        (privkey, onion_url) = keys[i]
        chosen_country_code = choice(country_codes, p=country_probs)
        server = {
            'name': 'server{}onionservice'.format(server_counter + 1),
            'country_code': chosen_country_code,
            'hs_ed25519_secret_key': privkey,
            'hs_hostname': onion_url,
            'is_hs_server': True,
        }
        tgen_servers.append(server)
        server_counter += 1

    logging.info("We will use {} TGen exit servers and {} TGen onion-service servers to serve {} TGen exit clients and {} TGen onion-service clients".format(n_exit_servers, n_hs_servers, n_exit_clients, n_hs_clients))

    return tgen_servers

def get_clients(args):
    '''
    Generate clients based on real measurements of Tor traffic.
    We use data from the following research paper:
      "Privacy-Preserving Dynamic Learning of Tor Network Traffic"
      25th ACM Conference on Computer and Communication Security (CCS 2018)
      Rob Jansen, Matthew Traudt, and Nick Hopper

    Our entry and exits collecting stats were a certain fraction of Tor during the PrivCount measurements:
      Period 1: scale=0.0126, path=data/privcount/measurement1/privcount.tallies.1508707017-1508793717.json
      Period 2: scale=0.0113, path=data/privcount/measurement2/privcount.tallies.1510708289-1510794689.json
      Period 3: scale=0.0213, path=data/privcount/measurement3/privcount.tallies.1515796790-1515883190.json
      Period 4: scale=0.0214, path=data/privcount/measurement4/privcount.tallies.1515970490-1516057190.json
      Period 5: scale=0.0227, path=data/privcount/measurement5/privcount.tallies.1512058187-1512144587.json
      Period 6: scale=0.0229, path=data/privcount/measurement6/privcount.tallies.1516319636-1516406336.json
      Period 7: scale=0.0254, path=data/privcount/measurement7/privcount.tallies.1516493936-1516580336.json
    '''

    # client counts taken from measurement 1 in the tmodel ccs2018 paper.
    measurement1_scale = 0.0126
    tally_path = '{}/data/privcount/measurement1/privcount.tallies.1508707017-1508793717.json'.format(args.tmodel_git_path)
    with open(tally_path, 'r') as tally_file:
        measurement1 = json.load(tally_file)

    # circuits per client historgram taken from measurement 2 in the tmodel ccs2018 paper.
    # measurement2_scale = 0.0113
    # tally_path = '{}/data/privcount/measurement2/privcount.tallies.1510708289-1510794689.json'.format(args.tmodel_git_path)
    # with open(tally_path, 'r') as tally_file:
    #     measurement2 = json.load(tally_file)

    # exit circuit count taken from measurement 3 in the tmodel ccs2018 paper.
    measurement3_scale = 0.0213
    tally_path = '{}/data/privcount/measurement3/privcount.tallies.1515796790-1515883190.json'.format(args.tmodel_git_path)
    with open(tally_path, 'r') as tally_file:
        measurement3 = json.load(tally_file)

    n_total_users, n_active_users, n_inactive_users = __get_client_counts(measurement1, measurement1_scale, args.network_scale)
    logging.info("Privcount measurements scaled to {} Tor users, {} active and {} inactive".format(n_total_users, n_active_users, n_inactive_users))

    n_total_exit_circs, n_active_exit_circs, n_inactive_exit_circs = __get_exit_circuit_counts(measurement3, measurement3_scale, args.network_scale)
    logging.info("Privcount measurements scaled to {} exit circuits, {} active and {} inactive".format(n_total_exit_circs, n_active_exit_circs, n_inactive_exit_circs))

    n_exit_users, n_hs_users, n_circuits_per_user = __get_tgen_users(args, n_active_users, n_active_exit_circs)

    tgen_clients, total_exit_circuits_10_mins, total_hs_circuits_10_mins = __get_tgen_clients(args, n_exit_users, n_hs_users, n_circuits_per_user)

    logging.info("We will use {} TGen client processes to emulate {} Tor exit users and create {} exit circuits every 10 minutes in aggregate".format(
        sum([1 for c in tgen_clients if not c['is_hs_client']]),
        n_exit_users,
        total_exit_circuits_10_mins))

    logging.info("We will use {} TGen client processes to emulate {} Tor onion-service users and create {} onion-service circuits every 10 minutes in aggregate".format(
        sum([1 for c in tgen_clients if c['is_hs_client']]),
        n_hs_users,
        total_hs_circuits_10_mins))

    perf_clients = __get_perf_clients(args, n_exit_users, n_hs_users)

    logging.info("We will use {} exit perf nodes to benchmark Tor exit performance".format(
        sum([1 for c in perf_clients if not c['is_hs_client']])))
    logging.info("We will use {} onion-service perf nodes to benchmark Tor onion-service performance".format(
        sum([1 for c in perf_clients if c['is_hs_client']])))

    return tgen_clients, perf_clients

def __get_perf_clients(args, n_exit_users, n_hs_users):
    perf_clients = []

    n_perf = args.torperf_num_onion_service + args.torperf_num_exit
    if (args.torperf_num_onion_service != args.torperf_num_exit
            and args.torperf_num_onion_service != 0
            and args.torperf_num_exit != 0):
        logging.warning("Unequal number of perf nodes. Is this what you meant? "
                        f"torperf_num_onion_service={args.torperf_num_onion_service} "
                        f"torperf_num_exit={args.torperf_num_exit}")

    for (i, is_hs_client) in ((x, x >= args.torperf_num_exit) for x in range(n_perf)):
        chosen_country_code = choice(ONIONPERF_COUNTRY_CODES)
        client = {
            'country_code': chosen_country_code,
            'is_hs_client': is_hs_client,
        }

        if is_hs_client:
            client['name'] = 'perfclient{}onionservice'.format(i + 1)
        else:
            client['name'] = 'perfclient{}exit'.format(i + 1)

        perf_clients.append(client)

    return perf_clients

def __load_user_data(args):
    # geographical user info taken from stage command output, i.e., tor metrics
    user_data = load_json_data(args.user_info_path)

    country_codes = sorted(user_data.keys())
    country_probs = [float(user_data[code]) for code in country_codes]

    return country_codes, country_probs

def __get_tgen_users(args, n_users, n_exit_circuits):
    # The privcount data has the total number of users. During that time
    # roughtly 5% of of usage was onion services. We model this by splitting
    # out 5% of the users to be "onion service users".
    # When we update our measurements, we should get a more precise number
    # here.
    estimated_hs_frac = 0.05
    n_estimated_hs_users = n_users * estimated_hs_frac
    n_estimated_exit_users = n_users - n_estimated_hs_users

    # Calculate the number of circuits each tgen creates every 10 minutes.
    # We have measurements of the number of exit circuits and number of exit
    # users, which estimates the load per user in the measured network.
    # For now we assume the same per-user load in onion services.
    n_estimated_circuits_per_user = n_exit_circuits / n_estimated_exit_users

    # Final load in circuits-per-user, with configured total load scaling.
    n_circuits_per_user = n_estimated_circuits_per_user * args.load_scale

    # Final number of users to simulate, with configured per-type scaling.
    n_hs_users = n_estimated_hs_users * args.onion_service_user_scale
    n_exit_users = n_estimated_exit_users * args.exit_user_scale

    return (n_exit_users, n_hs_users, n_circuits_per_user)

def __get_tgen_clients(args, n_exit_users, n_hs_users, n_circuits_per_user):
    # we need a set of TGen clients generating Tor client load
    tgen_clients = []

    # Calculate number of tgen instances used to emulate n_hs_users.
    # We typically use a smaller number of tgen instances than the number of users
    # we're emulating for efficiency (configured via args.process_scale).
    # However we don't allow args.process_scale to drive the number of processes lower than
    # TGEN_CLIENT_MIN_COUNT (or the number of users, whichever is smaller).
    n_hs_tgen_min = min(__round_or_ceil(n_hs_users), TGEN_CLIENT_MIN_COUNT)
    n_hs_tgen = max(__round_or_ceil(n_hs_users * args.process_scale), n_hs_tgen_min)
    if n_hs_tgen > 0:
        hs_users_per_hs_tgen = n_hs_users / n_hs_tgen
        n_circuits_per_hs_tgen = __round_or_ceil(n_circuits_per_user * hs_users_per_hs_tgen)

    # Same for exit users.
    n_exit_tgen_min = min(__round_or_ceil(n_exit_users), TGEN_CLIENT_MIN_COUNT)
    n_exit_tgen = max(__round_or_ceil(n_exit_users * args.process_scale), n_exit_tgen_min)
    if n_exit_tgen > 0:
        exit_users_per_exit_tgen = n_exit_users / n_exit_tgen
        n_circuits_per_exit_tgen = __round_or_ceil(n_circuits_per_user * exit_users_per_exit_tgen)

    # each client will be placed in a country
    country_codes, country_probs = __load_user_data(args)

    total_exit_circuits_10_mins = 0
    total_hs_circuits_10_mins = 0
    for (i, is_hs_client) in ((x, x >= n_exit_tgen) for x in range(n_exit_tgen + n_hs_tgen)):
        # where to place the tgen process
        chosen_country_code = choice(country_codes, p=country_probs)

        # how many total circuits should the tgen process create
        # note - sampling the circuit-per-client distribution turns out to be inaccurate, likely
        #        because there was a DoS attack on Tor during the measurement which caused entry
        #        relays to see ~10 times as many circuits as exit relays. So instead we use the
        #        more accurate total circuit counts from exits.
        #num_circs_every_10_minutes = __sample_active_circuits_per_n_clients(measurement2, n_users_per_tgen)
        if is_hs_client:
            num_circs_every_10_minutes = n_circuits_per_hs_tgen
            total_hs_circuits_10_mins += n_circuits_per_hs_tgen
        else:
            num_circs_every_10_minutes = n_circuits_per_exit_tgen
            total_exit_circuits_10_mins += n_circuits_per_exit_tgen

        # convert circuit count into a rate for the exponential distribution
        usec_in_10_minutes = 10.0 * 60.0 * 1000.0 * 1000.0
        usec_per_circ = usec_in_10_minutes / num_circs_every_10_minutes
        exponential_rate = 1.0 / usec_per_circ

        client = {
            'circuit_rate_exp': exponential_rate,
            'country_code': chosen_country_code,
            'log_level': 'info' if i == 0 else 'message',
            'is_hs_client': is_hs_client,
        }

        if is_hs_client:
            client['name'] = 'markovclient{}onionservice'.format(i + 1)
        else:
            client['name'] = 'markovclient{}exit'.format(i + 1)

        tgen_clients.append(client)

    return tgen_clients, total_exit_circuits_10_mins, total_hs_circuits_10_mins

def __get_client_counts(measurement, privcount_scale, tornet_scale):
    # extract the counts from the tally file data
    total_count = measurement['EntryClientIPCount']['bins'][0][2]
    active_count = measurement['EntryActiveClientIPCount']['bins'][0][2]
    inactive_count = measurement['EntryInactiveClientIPCount']['bins'][0][2]

    # we need to convert the counts at the privcount scale, to counts at our tornet scale
    scale_factor = tornet_scale / privcount_scale / PRIVCOUNT_PERIODS_PER_DAY

    total_scaled = __round_or_ceil(total_count * scale_factor)
    active_scaled = __round_or_ceil(active_count * scale_factor)
    inactive_scaled = __round_or_ceil(inactive_count * scale_factor)

    return total_scaled, active_scaled, inactive_scaled

def __get_exit_circuit_counts(measurement, privcount_scale, tornet_scale):
    # extract the counts from the tally file data
    total_count = measurement['ExitCircuitCount']['bins'][0][2]
    active_count = measurement['ExitActiveCircuitCount']['bins'][0][2]
    inactive_count = measurement['ExitInactiveCircuitCount']['bins'][0][2]

    # we need to convert the counts at the privcount scale, to counts at our tornet scale
    scale_factor = tornet_scale / privcount_scale / PRIVCOUNT_PERIODS_PER_DAY

    total_scaled = __round_or_ceil(total_count * scale_factor)
    active_scaled = __round_or_ceil(active_count * scale_factor)
    inactive_scaled = __round_or_ceil(inactive_count * scale_factor)

    return total_scaled, active_scaled, inactive_scaled

def __sample_active_circuits_per_n_clients(measurement, n_clients):
    # return the num of circuits we expect n_clients would create in 10 minutes
    # 10 minutes is the period over which privcount counts the circ-per-client histogram
    count = 0
    for i in range(n_clients):
        count += __sample_active_circuits_per_client(measurement)
    # exits saw ~1/10 of the circs entries see, possibly related to DoS on tor during measurement
    # note - this is hand-wavy magic
    return __round_or_ceil(count / 10.0)

def __sample_active_circuits_per_client(measurement):
    return __sample_bins(measurement['EntryClientIPActiveCircuitCount']['bins'])

def __sample_bins(bins):
    counts, indices = [], []
    for i in range(len(bins)):
        indices.append(i)
        counts.append(bins[i][2])

    total = float(sum(counts))
    probs = []
    for i in indices:
        probs.append(counts[i] / total)

    # choose one bin index using probs as the prob distribution
    bin_index_choice = int(float(choice(indices, 1, p=probs)))

    # now choose uniformly from all values represented by the bin
    low, high = bins[bin_index_choice][0], bins[bin_index_choice][1]
    if high == float('inf'):
        # we cannot reasonably expect the distribution to extend to infinity,
        # so intead use a multiple of the low end of the bin to represent
        # the high end of the infinity bin
        high = low * 8.0
    value = int(round(uniform(low, high)))

    return value

def generate_onion_service_keys(tor_cmd, n):
    with tempfile.TemporaryDirectory(prefix='tornettools-hs-keygen-') as dir_name:
        config = {'DisableNetwork': '1', 'DataDirectory': dir_name, 'ControlPort': '9030'}
        tor_process = stem.process.launch_tor_with_config(config,
                                                          tor_cmd=tor_cmd,
                                                          init_msg_handler=logging.debug,
                                                          take_ownership=True,
                                                          completion_percent=0)
        controller = stem.connection.connect(control_port=('127.0.0.1', 9030))

        keys = []

        for x in range(n):
            hs = controller.create_ephemeral_hidden_service(80)
            assert hs.private_key_type == 'ED25519-V3'

            keys.append((hs.private_key, hs.service_id + '.onion'))

        controller.close()

        # must make sure process ends before the temporary directory is removed,
        # otherwise there's a race condition
        tor_process.kill()
        tor_process.wait()

        return keys
