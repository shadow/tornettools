import sys
import os
import logging
import shlex
import subprocess
import threading
import lzma

from time import sleep

from tornettools.util import which

def run(args):
    logging.info("Starting a simulation from {}".format(args.prefix))

    logging.info("Starting dstat")
    dstat_subp = __start_dstat(args)

    logging.info("Starting free loop")
    free_stop_event = threading.Event()
    free_thread = threading.Thread(target=__run_free_loop, args=(args, free_stop_event))
    free_thread.start()

    logging.info("Starting shadow")
    retcode = __run_shadow(args)

    logging.info("Cleaning up")
    __cleanup_subprocess(dstat_subp)
    free_stop_event.set()
    free_thread.join()

    logging.info(f"Done simulating; shadow returned '{retcode}'")
    return retcode

def __run_shadow(args):
    shadow_exe_path = which('shadow')
    if shadow_exe_path == None:
        return None

    with __open_file(f"{args.prefix}/shadow.log", args.do_compress) as outf:
        shadow_cmd = shlex.split(f"{shadow_exe_path} {args.shadow_args} shadow.config.xml")
        retcode = subprocess.run(shadow_cmd, cwd=args.prefix, stdout=outf)

    return retcode

def __run_free_loop(args, stop_event):
    date_exe_path = which('date')
    free_exe_path = which('free')

    with open(f"{args.prefix}/free.log", 'w') as outf:
        while not stop_event.is_set():
            if date_exe_path != None:
                date_cmd = shlex.split(date_exe_path)
                retcode = subprocess.run(date_cmd, cwd=args.prefix, stdout=outf, stderr=subprocess.STDOUT)

            if free_exe_path != None:
                free_cmd = shlex.split(f"{free_exe_path} -w -b -l")
                retcode = subprocess.run(free_cmd, cwd=args.prefix, stdout=outf, stderr=subprocess.STDOUT)

            sleep(1)

def __start_dstat(args):
    dstat_exe_path = which('dstat')

    if dstat_exe_path == None:
        return None

    dstat_cmd = shlex.split(f"{dstat_exe_path} -cmstTy --fs --output dstat.log")
    dstat_subp = subprocess.Popen(dstat_cmd, cwd=args.prefix, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    return dstat_subp

def __cleanup_subprocess(subp):
    # if subp exists but has yet to receive a return code, then we kill it
    if subp != None and subp.poll() is None:
        subp.terminate()
        subp.wait()

def __open_file(filepath, do_compress):
    if do_compress:
        return lzma.open(f"{filepath}.xz", 'wt')
    else:
        return open(filepath, 'w')
