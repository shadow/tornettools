# tornettools

![](https://github.com/shadow/tornettools/workflows/Build/badge.svg)

tornettools is a utility to guide you through the Tor network
experimentation process using Shadow, by assisting with the
following experimentation steps:

  - **stage**:     Process Tor metrics data for staging network generation
  - **generate**:  Generate TorNet network configurations
  - **simulate**:  Run a TorNet simulation in Shadow
  - **parse**:     Parse useful data from simulation log files
  - **plot**:      Plot previously parsed data to visualize results
  - **archive**:   Cleanup and compress Shadow simulation data

The configuration files that are generated can be run in the
[Shadow network simulator](https://github.com/shadow/shadow);
[NetMirage](https://crysp.uwaterloo.ca/software/netmirage)
and
[Chutney](https://gitweb.torproject.org/chutney.git)
may eventually support the files generated with this tool.

The generated networks include the use of
[TGen](https://github.com/shadow/tgen)
for the generation of realistic background traffic, and
[OnionTrace](https://github.com/shadow/oniontrace)
for the collection of information from Tor throughout an experiment.

### Citation

This tool was initially created as part of the following research publication. Please cite this paper if you use this tool in your work:

[Once is Never Enough: Foundations for Sound Statistical Inference in Tor Network Experimentation](https://www.robgjansen.com/publications/neverenough-sec2021.pdf)  
_Proceedings of [the 30th USENIX Security Symposium](https://www.usenix.org/conference/usenixsecurity21) (Sec 2021)_  
by [Rob Jansen](https://www.robgjansen.com), Justin Tracey, and [Ian Goldberg](https://cs.uwaterloo.ca/~iang)  

Here is a bibtex entry for latex users:

```bibtex
@inproceedings{neverenough-sec2021,
  author = {Rob Jansen and Justin Tracey and Ian Goldberg},
  title = {Once is Never Enough: Foundations for Sound Statistical Inference in {Tor} Network Experimentation},
  booktitle = {30th USENIX Security Symposium (Sec)},
  year = {2021},
  note = {See also \url{https://neverenough-sec2021.github.io}},
}
```

### setup is easy with virtualenv and pip

    python3 -m venv toolsenv
    source toolsenv/bin/activate
    pip install -r requirements.txt
    pip install -I .

### read the help menus

    tornettools -h
    tornettools stage -h
    tornettools generate -h
    tornettools simulate -h
    tornettools parse -h
    tornettools plot -h
    tornettools archive -h

### grab the data we need

    wget https://collector.torproject.org/archive/relay-descriptors/consensuses/consensuses-2020-11.tar.xz
    wget https://collector.torproject.org/archive/relay-descriptors/server-descriptors/server-descriptors-2020-11.tar.xz
    wget https://metrics.torproject.org/userstats-relay-country.csv
    wget https://collector.torproject.org/archive/onionperf/onionperf-2020-11.tar.xz
    wget -O bandwidth-2020-11.csv "https://metrics.torproject.org/bandwidth.csv?start=2020-11-01&end=2020-11-30"

### extract

    tar xaf consensuses-2020-11.tar.xz
    tar xaf server-descriptors-2020-11.tar.xz
    tar xaf onionperf-2020-11.tar.xz

### we also utilize privcount Tor traffic model measurements

    git clone https://github.com/tmodel-ccs2018/tmodel-ccs2018.github.io.git

### we also need tor

    sudo apt-get install openssl libssl-dev libevent-dev build-essential automake zlib1g zlib1g-dev
    git clone https://git.torproject.org/tor.git
    cd tor
    ./autogen.sh
    ./configure --disable-asciidoc --disable-unittests --disable-manpage --disable-html-manual
    make -j$(nproc)
    cd ..

### in order to generate, we need a tor and tor-gencert binaries (to generate relay keys)

    export PATH=${PATH}:`pwd`/tor/src/core/or:`pwd`/tor/src/app:`pwd`/tor/src/tools

### stage first, process relay and user info

    tornettools stage \
        consensuses-2020-11 \
        server-descriptors-2020-11 \
        userstats-relay-country.csv \
        tmodel-ccs2018.github.io \
        --onionperf_data_path onionperf-2020-11 \
        --bandwidth_data_path bandwidth-2020-11.csv \
        --geoip_path tor/src/config/geoip

### now we can used the staged files to generate many times

For example, use `--network_scale 0.01` to generate a private Tor network at '1%' the scale of public Tor:

    tornettools generate \
        relayinfo_staging_2020-11-01--2020-11-30.json \
        userinfo_staging_2020-11-01--2020-11-30.json \
        networkinfo_staging.gml \
        tmodel-ccs2018.github.io \
        --network_scale 0.01 \
        --prefix tornet-0.01

### now you can run a simulation and process the results

Make sure you have already installed [shadow](https://github.com/shadow/shadow), [tgen](https://github.com/shadow/tgen), and [oniontrace](https://github.com/shadow/oniontrace).

Note that simulating a '1%' Tor network for 60 simulation minutes can take as much as 30GiB of RAM.

    tornettools simulate tornet-0.01
    tornettools parse tornet-0.01
    tornettools plot \
        tornet-0.01 \
        --tor_metrics_path tor_metrics_2020-11-01--2020-11-30.json \
        --prefix pdfs
    tornettools archive tornet-0.01

Performance metrics are plotted in the graph files in the pdfs directory.
