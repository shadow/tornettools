import sys
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
        infile = lzma.open(filepath, 'r')
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
        logging.critical("Error extracting file {} using command {}".format(dst, cmd))
    assert completed_proc.returncode == 0

def type_nonnegative_integer(value):
    i = int(value)
    if i < 0: raise argparse.ArgumentTypeError("'%s' is an invalid non-negative int value" % value)
    return i

def type_fractional_float(value):
    i = float(value)
    if i <= 0.0 or i > 1.0:
        raise argparse.ArgumentTypeError("'%s' is an invalid fractional float value" % value)
    return i

def type_str_file_path_out(value):
    s = str(value)
    if s == "-":
        return s
    p = os.path.abspath(os.path.expanduser(s))
    make_directories(p)
    return p

def type_str_dir_path_out(value):
    s = str(value)
    p = os.path.abspath(os.path.expanduser(s))
    make_directories(p)
    return p

def type_str_path_in(value):
    s = str(value)
    if s == "-":
        return s
    p = os.path.abspath(os.path.expanduser(s))
    if not os.path.exists(p):
        raise argparse.ArgumentTypeError("path '%s' does not exist" % s)
    return p
