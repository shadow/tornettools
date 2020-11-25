#!/bin/bash

# run from base tornettools directory
# tornettools must have already been installed in a virtual environment
# in build/tornettoolsenv

#source build/tornettoolsenv/bin/activate

# must set these options *after* sourcing the above environment
set -euo pipefail

cd build

#wget https://collector.torproject.org/archive/relay-descriptors/consensuses/consensuses-2020-01.tar.xz
#wget https://collector.torproject.org/archive/relay-descriptors/server-descriptors/server-descriptors-2020-01.tar.xz
#wget https://metrics.torproject.org/userstats-relay-country.csv
#wget https://collector.torproject.org/archive/torperf/torperf-2020-01.tar.xz

#tar xaf consensuses-2020-01.tar.xz
#tar xaf server-descriptors-2020-01.tar.xz
#tar xaf torperf-2020-01.tar.xz

#GIT_SSL_NO_VERIFY=1 git clone https://github.com/tmodel-ccs2018/tmodel-ccs2018.github.io.git

#GIT_SSL_NO_VERIFY=1 git clone https://git.torproject.org/tor.git
#cd tor
#./autogen.sh
#./configure --disable-asciidoc
#make
#cd ..

export PATH=${PATH}:`pwd`/tor/src/core/or:`pwd`/tor/src/app:`pwd`/tor/src/tools

#tornettools parseperf torperf-2020-01

#tornettools stage \
#    consensuses-2020-01 \
#    server-descriptors-2020-01 \
#    userstats-relay-country.csv \
#    --geoip_path tor/src/config/geoip

for n in 0.05 0.1
do
    for p in 0.01 0.1
    do
        for s in 0.01 0.1
        do
            for t in 0.001 0.01
            do
                for l in 0.5 1.0 1.5
                do
                    tornettools generate \
                        relayinfo_staging_2020-01-01--2020-02-01.json \
                        userinfo_staging_2020-01-01--2020-02-01.json \
                        tmodel-ccs2018.github.io \
                        --network_scale ${n} \
                        --process_scale ${p} \
                        --server_scale ${s} \
                        --torperf_scale ${t} \
                        --load_scale ${l} \
                        --prefix tornet-${n}n-${p}p-${s}s-${t}t-${l}l
                done
            done
        done
    done
done
