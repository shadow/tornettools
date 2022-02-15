import logging
import subprocess
import threading

from time import sleep

from tornettools.util import which, cmdsplit, open_writeable_file

def run(args):
    logging.info("Starting a simulation from tornet prefix {}".format(args.prefix))

    logging.info("Starting dstat")
    dstat_subp = __start_dstat(args)

    logging.info("Starting free loop")
    free_stop_event = threading.Event()
    free_thread = threading.Thread(target=__run_free_loop, args=(args, free_stop_event))
    free_thread.start()

    try:
        logging.info("Starting shadow")
        comproc = __run_shadow(args)

        logging.info("Cleaning up")
        __cleanup_subprocess(dstat_subp)
    finally:
        free_stop_event.set()
        free_thread.join()

    if comproc is None:
        logging.warning("Simulation was not started")
        return 1

    logging.info(f"Done simulating; shadow returned code '{comproc.returncode}'")
    return comproc.returncode

def __run_shadow(args):
    if args.shadow_exe is None:
        logging.warning("Cannot find shadow in your PATH. Do you have shadow installed? Did you update your PATH?")
        logging.warning("Unable to run simulation without shadow.")
        return None

    shadow_cmd_str = f"{args.shadow_exe} {args.shadow_args} {args.shadow_config}"

    if args.use_realtime:
        # chrt manipulates the real-time attributes of a process (see `man chrt`)
        chrt_exe_path = which('chrt')

        if chrt_exe_path is None:
            logging.warning("Cannot find chrt in your PATH. Do you have chrt installed?")
            logging.warning("Unable to run simulation with realtime scheduling without chrt.")
            return None

        # --fifo sets realtime scheduling policy to SCHED_FIFO
        shadow_cmd_str = f"{chrt_exe_path} --fifo 1 {shadow_cmd_str}"

    with open_writeable_file(f"{args.prefix}/shadow.log", compress=args.do_compress) as outf:
        shadow_cmd = cmdsplit(shadow_cmd_str)
        comproc = subprocess.run(shadow_cmd, cwd=args.prefix, stdout=outf)

    return comproc

def __run_free_loop(args, stop_event):
    date_exe_path = which('date')
    free_exe_path = which('free')

    with open(f"{args.prefix}/free.log", 'w') as outf:
        while not stop_event.is_set():
            if date_exe_path is not None:
                date_cmd = cmdsplit(f"{date_exe_path} --utc '+%s.%N %Z seconds since epoch'")
                subprocess.run(date_cmd, cwd=args.prefix, stdout=outf, stderr=subprocess.STDOUT)

            if free_exe_path is not None:
                free_cmd = cmdsplit(f"{free_exe_path} -w -b -l")
                subprocess.run(free_cmd, cwd=args.prefix, stdout=outf, stderr=subprocess.STDOUT)

            sleep(1)

def __start_dstat(args):
    dstat_exe_path = which('dstat')

    if dstat_exe_path is None:
        return None

    dstat_cmd = cmdsplit(f"{dstat_exe_path} -cmstTy --fs --output dstat.log")
    dstat_subp = subprocess.Popen(dstat_cmd, cwd=args.prefix, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    return dstat_subp

def __cleanup_subprocess(subp):
    # if subp exists but has yet to receive a return code, then we kill it
    if subp is not None and subp.poll() is None:
        subp.terminate()
        subp.wait()
