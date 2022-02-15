import os
import logging
import datetime
import subprocess

from tornettools.util import which, cmdsplit, find_matching_files_in_dir, open_writeable_file

def plot_tgen(args):
    tgentools_exe = which('tgentools')

    if tgentools_exe is None:
        logging.warning("Cannot find tgentools in your PATH. Is your python venv active? Do you have tgentools installed?")
        logging.warning("Unable to plot tgen data.")
        return

    # plot the tgen simulation data for each tgen json file in the tornet path
    for circuittype in ('exit', 'onionservice'):
        cmd_prefix_str = f"{tgentools_exe} plot --expression 'perfclient\\d+'{circuittype} --bytes --prefix perf.{circuittype}"
        for collection in args.tornet_collection_path:
            for json_path in find_matching_files_in_dir(collection, "tgen.analysis.json"):
                dir_path = os.path.dirname(json_path)
                dir_name = os.path.basename(dir_path)

                cmd_str = f"{cmd_prefix_str} --data {json_path} {dir_name}"
                cmd = cmdsplit(cmd_str)

                datestr = datetime.datetime.now().strftime("%Y-%m-%d.%H:%M:%S")

                with open_writeable_file(f"{dir_path}/tgentools.plot.{circuittype}.{datestr}.log") as outf:
                    logging.info(f"Using tgentools to plot data from {json_path} now...")
                    comproc = subprocess.run(cmd, cwd=dir_path, stdout=outf, stderr=subprocess.STDOUT)
                    logging.info(f"tgentools returned code {comproc.returncode}")
