import sys
import os
import logging
import shutil
import subprocess

from tornettools.util import which, cmdsplit

def run(args):
    logging.info("Starting to archive simulation results now.")

    if which('xz') == None or which('tar') == None or which('dd') == None:
        logging.warning("We require the tar, xz, and dd tools to archive the results.")
        logging.critical("Unable to archive with missing tools.")
        return

    shutil.copy2(f"{args.prefix}/shadow.data/hosts/4uthority1/cached-consensus", f"{args.prefix}/consensus")

    logging.info("Compressing consensus.")
    __xz_parallel(args, "consensus")
    logging.info("Compressing shadow config.")
    __xz_parallel(args, "shadow.config.yaml")
    logging.info("Compressing dstat log.")
    __xz_parallel(args, "dstat.log")
    logging.info("Compressing free log.")
    __xz_parallel(args, "free.log")
    logging.info("Compressing shadow log.")
    __xz_parallel(args, "shadow.log")

    logging.info("Compressing conf dir.")
    if __tar_xz_parallel(args, "conf"):
        shutil.rmtree(f"{args.prefix}/conf")

    logging.info("Compressing shadow template dir.")
    if __tar_xz_parallel(args, "shadow.data.template"):
        shutil.rmtree(f"{args.prefix}/shadow.data.template")

    logging.info("Compressing shadow data dir.")
    if __tar_xz_parallel(args, "shadow.data", excludes=['cached-*', 'diff-cache', 'keys', 'lock']):
        shutil.rmtree(f"{args.prefix}/shadow.data")

    logging.info("Compressing remaining log files.")
    for name in os.listdir(args.prefix):
        if name.endswith(".log"):
            __xz_parallel(args, name)

def __xz_parallel(args, filename):
    path = f"{args.prefix}/{filename}"
    if os.path.exists(path):
        xz_cmd = cmdsplit(f"xz -9 --threads={args.nprocesses} {path}")
        comproc = subprocess.run(xz_cmd, cwd=args.prefix, stdout=subprocess.DEVNULL)
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

    tar_cmd = cmdsplit(f"tar cf - {flag_str} {dirname}")
    tarproc = subprocess.Popen(tar_cmd, cwd=args.prefix, stdout=subprocess.PIPE)

    xz_cmd = cmdsplit(f"xz -9 --threads={args.nprocesses} -")
    xzproc = subprocess.Popen(xz_cmd, cwd=args.prefix, stdin=tarproc.stdout, stdout=subprocess.PIPE)

    dd_cmd = cmdsplit(f"dd of={dirname}.tar.xz")
    ddproc = subprocess.Popen(dd_cmd, cwd=args.prefix, stdin=xzproc.stdout, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # wait for the above and collec the return codes
    tar_rc = tarproc.wait()
    xz_rc = xzproc.wait()
    dd_rc = ddproc.wait()

    if tar_rc == 0 and xz_rc == 0 and dd_rc == 0:
        return True
    else:
        return False
