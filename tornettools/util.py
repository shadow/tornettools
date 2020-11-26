import sys
import os
import logging
import json
import lzma

def make_dir_path(path):
    p = os.path.abspath(os.path.expanduser(path))
    if not os.path.exists(p):
        os.makedirs(p)

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
