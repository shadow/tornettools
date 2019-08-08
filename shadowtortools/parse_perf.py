import sys
import os
import json
import logging

from subprocess import Popen, PIPE

def run(args):
    # as long as the download is within this bytes we consider it a full one
    tolerance = 1000

    # the data we extract
    db = {"data": {}, "type": "tgen", "version": "0.0.1"}

    count, onion_count = 0, 0

    # parse the files
    for root, dirs, files in os.walk(args.torperf_data_path):
        for file in files:
            fullpath = os.path.join(root, file)
            logging.info("Processing TorPerf file: '{}'".format(fullpath))
            with open(fullpath, 'r') as f:
                for line in f:
                    if '=' not in line: continue
                    d = {}
                    parts = line.strip().split()
                    for part in parts:
                        if '=' not in part: continue
                        p = part.split('=')
                        assert len(p) > 1
                        key, value = p[0], p[1]
                        d[key] = value

                    if 'ENDPOINTREMOTE' in d and '.onion' in d['ENDPOINTREMOTE']:
                        onion_count += 1
                        continue
                    else:
                        count += 1

                    start = float(d["START"])
                    #if start < begintime or (endtime > 0 and start > endtime): continue
                    if int(d["DIDTIMEOUT"]) == 1: continue

                    name = "perfclient-{}".format(d['HOSTNAMELOCAL'])
                    db['data'].setdefault(name, {"measurement_ip": "unknown", "tgen": {"stream_summary" :{"errors":{}, "time_to_first_byte_recv":{}, "time_to_first_byte_send":{}, "time_to_last_byte_recv":{}, "time_to_last_byte_send":{}}}})

                    totalbytes = int(d["READBYTES"])
                    if totalbytes < 1: continue
                    if totalbytes > 51200-tolerance and totalbytes < 51200+tolerance: totalbytes = 51200
                    if totalbytes > 1048576-tolerance and totalbytes < 1048576+tolerance: totalbytes = 1048576
                    if totalbytes > 5242880-tolerance and totalbytes < 5242880+tolerance: totalbytes = 5242880

                    if totalbytes not in db["data"][name]["tgen"]["stream_summary"]["time_to_first_byte_recv"]:
                        db["data"][name]["tgen"]["stream_summary"]["time_to_first_byte_recv"][totalbytes] = {1800:[]}
                        db["data"][name]["tgen"]["stream_summary"]["time_to_last_byte_recv"][totalbytes] = {1800:[]}

                    first = float(d["DATARESPONSE"])
                    if first >= start:
                        db["data"][name]["tgen"]["stream_summary"]["time_to_first_byte_recv"][totalbytes][1800].append(first-start)

                    last = float(d["DATACOMPLETE"])
                    if last >= start:
                        db["data"][name]["tgen"]["stream_summary"]["time_to_last_byte_recv"][totalbytes][1800].append(last-start)

    logging.info("We processed {} downloads and skipped {} onion downloads from the source data".format(count, onion_count))

    # this filename is used so that `tgentools plot` will automatically work!
    path = args.output_path
    if args.do_compress:
        with open("/dev/null", 'a') as nullf:
            path = "{}.xz".format(path)
            xzp = Popen([args.xz_path, "-"], stdin=PIPE, stdout=PIPE)
            ddp = Popen([args.dd_path, "of={}".format(path)], stdin=xzp.stdout, stdout=nullf, stderr=nullf)
            str = json.dumps(db, sort_keys=True, separators=(',', ': '), indent=2)
            xzp.stdin.write(str.encode('utf-8'))
            xzp.stdin.close()
            xzp.wait()
            ddp.wait()
    else:
        with open(path, 'w') as outf:
            json.dump(db, outf, sort_keys=True, separators=(',', ': '), indent=2)

    logging.info("Output stored in '{}'".format(path))
