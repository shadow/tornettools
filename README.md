### setup is easy with virtualenv and pip

    virtualenv -p /bin/python3 shadowtortoolsenv
    source shadowtortoolsenv/bin/activate
    pip install -r requirements.txt

### read the help menus

    shadowtortools -h
    shadowtortools stage -h
    shadowtortools generate -h

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

    shadowtortools stage consensuses-2019-01 server-descriptors-2019-01 userstats-relay-country.csv -g tor/src/config/geoip

### now we can used the staged files to generate many times
### e.g., use '-n 0.1' to generate a ShadowTor network at '10%' the scale of Tor

    shadowtortools generate relayinfo_staging_2019-01-01--2019-02-01.json userinfo_staging_2019-01-01--2019-02-01.json tmodel-ccs2018.github.io -n 0.1 -p shadowtor-0.1

# you can parse the torperf data so we can compare Tor and ShadowTor performance benchmarks

    shadowtortools parseperf torperf-2019-01

### now if you have shadow, tgen, and oniontrace installed, you can run shadow

    cd shadowtor-0.1
    shadow -w 12 shadow.config.xml > shadow.log
