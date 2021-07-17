import os
import logging
import json
import lzma
import shutil
import shlex
import subprocess

def make_directories(path):
    p = os.path.abspath(os.path.expanduser(path))
    d = os.path.dirname(path)
    if not os.path.exists(d):
        os.makedirs(d)

## test if program is in path
def which(program):
    #returns None if not found
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

def copy_and_extract_file(src, dst):
    shutil.copy2(src, dst)

    xz_cmd = "xz -d {}".format(dst)
    completed_proc = subprocess.run(shlex.split(xz_cmd), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if completed_proc.returncode != 0:
        logging.critical("Error extracting file {} using command {}".format(dst, xz_cmd))
    assert completed_proc.returncode == 0

def find_matching_files_in_dir(search_dir, filename):
    logging.info(f"Searching for files with name {filename} in directory tree at {search_dir}")
    found = []
    for root, dirs, files in os.walk(search_dir):
        for name in files:
            if filename in name:
                p = os.path.join(root, name)
                logging.info("Found {}".format(p))
                found.append(p)
    logging.info(f"Found {len(found)} total files")
    return found
