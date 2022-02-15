import os
import logging
import json
import lzma
import re
import shutil
import shlex

def make_directories(path):
    p = os.path.abspath(os.path.expanduser(path))
    d = os.path.dirname(path)
    if not os.path.exists(d):
        os.makedirs(d)

# test if program is in path
def which(program):
    # returns None if not found
    return shutil.which(program)

def cmdsplit(cmd_str):
    return shlex.split(cmd_str)

def open_writeable_file(filepath, compress=False):
    make_directories(filepath)
    if compress:
        if not filepath.endswith(".xz"):
            filepath += ".xz"
        outfile = lzma.open(filepath, 'wt')
    else:
        outfile = open(filepath, 'w')
    return outfile

def open_readable_file(filepath):
    if not os.path.exists(filepath) and not filepath.endswith('.xz'):
        filepath += ".xz" # look for the compressed version
    if filepath.endswith('.xz'):
        infile = lzma.open(filepath, 'rt')
    else:
        infile = open(filepath, 'r')
    return infile

def dump_json_data(output, outfile_path, compress=False):
    with open_writeable_file(outfile_path, compress) as outfile:
        json.dump(output, outfile, sort_keys=True, separators=(',', ': '), indent=2)

def load_json_data(infile_path):
    with open_readable_file(infile_path) as infile:
        data = json.load(infile)
    return data

def find_matching_files_in_dir(search_dir, filepattern):
    if type(filepattern) == str:
        # Interpret as a literal string
        logging.info(f"Searching for files containing {filepattern} in directory tree at {search_dir}")
        filepattern = re.compile('.*' + re.escape(filepattern) + '.*')
    else:
        logging.info(f"Searching for files matching {filepattern.pattern} in directory tree at {search_dir}")
    found = []
    for root, dirs, files in os.walk(search_dir):
        for name in files:
            if filepattern.match(name):
                p = os.path.join(root, name)
                logging.info("Found {}".format(p))
                found.append(p)
    logging.info(f"Found {len(found)} total files")
    return found

# Useful for spelling integer constants multiple ways.  e.g. it can be useful
# to spell 1 Mebi as 1048576 if that's how it's spelled out in other
# documentation, *and* as 2 ** 20 to be able to easily verify that it's really
# exactly 1 Mebi and not something slightly different.
# e.g.:
#     start_bytes = aka_int(2**20, 1048576)
def aka_int(x, y):
    assert(x == y)
    return x

# Looks for the given data point, first in
# stream['elapsed_seconds']['payload_bytes_recv'], and then falls back to
# stream['elapsed_seconds']['payload_progress_recv']. Returns None if not found
# in either.
#
# This is useful because, e.g., tgen data currently doesn't have 4 MiB in
# `payload_bytes_recv`, but *does* have progress 0.8 of 5 MiB streams in
# `payload_progress_recv`.
def tgen_stream_seconds_at_bytes(stream, num_bytes):
    es = stream.get('elapsed_seconds')
    if es is None:
        return None
    seconds = es['payload_bytes_recv'].get(str(num_bytes))
    if seconds is not None:
        return float(seconds)
    progress = num_bytes / float(stream['stream_info']['recvsize'])
    seconds = es['payload_progress_recv'].get(str(progress))
    if seconds is not None:
        return float(seconds)
    return None
