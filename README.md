# TorNetGen

![](https://github.com/shadow/tornetgen/workflows/Build/badge.svg)

This tool generates configuration files that can be used to set up and run
private Tor networks of a configurable scale. The configuration files that
are generated can be run in the
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

### setup is easy with virtualenv and pip

    virtualenv -p /bin/python3 tornetgenenv
    source tornetgenenv/bin/activate
    pip install -r requirements.txt
    pip install -I .

### read the help menus

    tornetgen -h
    tornetgen stage -h
    tornetgen generate -h

### grab the data we need

    wget https://collector.torproject.org/archive/relay-descriptors/consensuses/consensuses-2019-01.tar.xz
    wget https://collector.torproject.org/archive/relay-descriptors/server-descriptors/server-descriptors-2019-01.tar.xz
    wget https://metrics.torproject.org/userstats-relay-country.csv
    wget https://collector.torproject.org/archive/torperf/torperf-2019-01.tar.xz

### extract

    tar xaf consensuses-2019-01.tar.xz
    tar xaf server-descriptors-2019-01.tar.xz
    tar xaf torperf-2019-01.tar.xz

### we also utilize privcount Tor traffic model measurements

    git clone https://github.com/tmodel-ccs2018/tmodel-ccs2018.github.io.git

### we also need tor

    git clone https://git.torproject.org/tor.git
    cd tor
    ./autogen
    ./configure --disable-asciidoc
    make
    cd ..

### in order to generate, we need a tor and tor-gencert binaries (to generate relay keys)

    export PATH=${PATH}:`pwd`/tor/src/core/or:`pwd`/tor/src/app:`pwd`/tor/src/tools

### stage first, process relay and user info

    tornetgen stage consensuses-2019-01 server-descriptors-2019-01 userstats-relay-country.csv -g tor/src/config/geoip

### now we can used the staged files to generate many times
### e.g., use '-n 0.1' to generate a private Tor network at '10%' the scale of public Tor

    tornetgen generate relayinfo_staging_2019-01-01--2019-02-01.json userinfo_staging_2019-01-01--2019-02-01.json tmodel-ccs2018.github.io -n 0.1 -p tornet-0.1

# you can parse the torperf data so we can compare public Tor and our private Tor performance benchmarks

    tornetgen parseperf torperf-2019-01

### now if you have shadow, tgen, and oniontrace installed, you can run shadow

    cd tornet-0.1
    shadow -w 12 shadow.config.xml > shadow.log
