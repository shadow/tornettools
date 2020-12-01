import sys
import os
import logging
import json
import lzma
import subprocess

def make_dir_path(path):
    p = os.path.abspath(os.path.expanduser(path))
    if not os.path.exists(p):
        os.makedirs(p)

def make_directories(path):
    d = os.path.dirname(path)
    if not os.path.exists(d):
        os.makedirs(d)

## test if program is in path
def which(program):
    def is_exe(fpath):
        return os.path.isfile(fpath) and os.access(fpath, os.X_OK)
    fpath, _ = os.path.split(program)
    if fpath:
        if is_exe(program):
            return program
    else:
        for path in os.environ["PATH"].split(os.pathsep):
            exe_file = os.path.join(path, program)
            if is_exe(exe_file):
                return exe_file
    #return "Error: Path Not Found"
    return None

def dump_json_data(args, output, outfile_basename):
    outfile_path = "{}/{}".format(args.prefix, outfile_basename)

    if args.do_compress:
        outfile_path += ".xz"
        outfile = lzma.open(outfile_path, 'wt')
    else:
        outfile = open(outfile_path, 'w')

    json.dump(output, outfile, sort_keys=True, separators=(',', ': '), indent=2)
    outfile.close()

def load_json_data(infile_path):
    if infile_path.endswith('.xz'):
        infile = lzma.open(infile_path, 'r')
    else:
        infile = open(infile_path, 'r')

    data = json.load(infile)
    infile.close()

    return data

def copy_and_extract_file(src, dst):
    shutil.copy2(src, dst)

    xz_cmd = "xz -d {}".format(dst)
    retcode = subprocess.run(shlex.split(xz_cmd), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if retcode != 0:
        logging.critical("Error extracting file {} using command {}".format(dst, cmd))
    assert retcode == 0

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
    make_dir_path(os.path.dirname(p))
    return p

def type_str_dir_path_out(value):
    s = str(value)
    p = os.path.abspath(os.path.expanduser(s))
    make_dir_path(p)
    return p

def type_str_path_in(value):
    s = str(value)
    if s == "-":
        return s
    p = os.path.abspath(os.path.expanduser(s))
    if not os.path.exists(p):
        raise argparse.ArgumentTypeError("path '%s' does not exist" % s)
    return p
