import sys
import os
import logging

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
