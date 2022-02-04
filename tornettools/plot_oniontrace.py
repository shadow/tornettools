import os
import logging
import datetime
import subprocess

from tornettools.util import which, cmdsplit, find_matching_files_in_dir, open_writeable_file

def plot_oniontrace(args):
    oniontracetools_exe = which('oniontracetools')

    if oniontracetools_exe == None:
        logging.warning("Cannot find oniontracetools in your PATH. Is your python venv active? Do you have oniontracetools installed?")
        logging.warning("Unable to plot oniontrace data.")
        return

    # plot the tgen simulation data for each tgen json file in the tornet path
    cmd_prefix_str = f"{oniontracetools_exe} plot --expression 'relay|4uthority' --prefix 'relays'"
    for collection in args.tornet_collection_path:
        for json_path in find_matching_files_in_dir(collection, "oniontrace.analysis.json"):
            dir_path = os.path.dirname(json_path)
            dir_name = os.path.basename(dir_path)

            cmd_str = f"{cmd_prefix_str} --data {json_path} {dir_name}"
            cmd = cmdsplit(cmd_str)

            datestr = datetime.datetime.now().strftime("%Y-%m-%d.%H.%M.%S")

            with open_writeable_file(f"{dir_path}/oniontracetools.plot.{datestr}.log") as outf:
                logging.info(f"Using oniontracetools to plot data from {json_path} now...")
                comproc = subprocess.run(cmd, cwd=dir_path, stdout=outf, stderr=subprocess.STDOUT)
                logging.info(f"oniontracetools returned code {comproc.returncode}")
