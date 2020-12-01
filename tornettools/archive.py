import sys
import os
import logging
import shutil
import shlex
import subprocess

from tornettools.util import which

def run(args):
    if which('xz') == None or which('tar') == None or which('dd') == None:
        logging.warning("We require the tar, xz, and dd tools to archive the results.")
        logging.critical("Unable to archive with missing tools.")
        return

    shutil.copy2(f"{args.prefix}/shadow.data/hosts/4uthority1/cached-consensus", f"{args.prefix}/consensus")

    __xz_parallel(args, "consensus")
    __xz_parallel(args, "dstat.log")
    __xz_parallel(args, "free.log")
    __xz_parallel(args, "shadow.log")
    __xz_parallel(args, "shadow.config.xml")

    if __tar_xz_parallel(args, "conf"):
        shutil.rmtree(f"{args.prefix}/conf")

    if __tar_xz_parallel(args, "shadow.data.template"):
        shutil.rmtree(f"{args.prefix}/shadow.data.template")

    if __tar_xz_parallel(args, "shadow.data", excludes=['cached-*', 'diff-cache', 'keys', 'lock']):
        shutil.rmtree(f"{args.prefix}/shadow.data")

def __xz_parallel(args, filename):
    path = f"{args.prefix}/{filename}"
    if os.path.exists(path):
        comproc = subprocess.run(shlex.split(f"xz -9e --threads={args.nprocesses} {path}"),
            cwd=args.prefix, stdout=subprocess.DEVNULL)
        if comproc.returncode == 0:
            return True
    return False

def __tar_xz_parallel(args, dirname, excludes=[]):
    dirpath = f"{args.prefix}/{dirname}"
    if not os.path.exists(dirpath):
        return False

    # we are basically trying to do something like:
    # tar cf - FLAGS dirname | xz -8e --threads=N > dirname.tar.xz

    flags = [f"--exclude='{e}'" for e in excludes]
    flag_str = ' '.join(flags)

    # NOTE: DO NOT USE shlex.split() in the tar command;
    # we need the ' chars in the exclude strings for the tar command, but shlex removes them
    tar_cmd = f"tar cf - {flag_str} {dirname}"
    tarproc = Popen(tar_cmd.split(), cwd=args.prefix, stdout=subprocess.PIPE)

    xz_cmd = f"xz -8e --threads={args.nprocesses} -"
    xzproc = Popen(shlex.split(xz_cmd), cwd=args.prefix, stdin=tarproc.stdout, stdout=subprocess.PIPE)

    dd_cmd = f"dd of={dirname}.tar.xz"
    ddproc = Popen(shlex.split(dd_cmd), cwd=args.prefix, stdin=xzproc.stdout, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # wait for the above and collec the return codes
    tar_rc = tarproc.wait()
    xz_rc = xzproc.wait()
    dd_rc = ddproc.wait()

    if tar_rc == 0 and xz_rc == 0 and dd_rc == 0:
        return True
    else:
        return False
