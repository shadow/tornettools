#!/bin/bash

# run from base tornettools directory
# assumptions made by this script:
#   - you have installed libevent and openssl libraries and header files
#   - you have installed the build tools needed to build tor
#   - python, git, tar, wget, xz-tools are accessible

python -m venv build/tornettoolsenv
source build/tornettoolsenv/bin/activate

# must set these options *after* sourcing the above environment
set -euo pipefail

pip install -r requirements.txt
pip install -I .

cd build

wget https://collector.torproject.org/archive/relay-descriptors/consensuses/consensuses-2020-11.tar.xz
wget https://collector.torproject.org/archive/relay-descriptors/server-descriptors/server-descriptors-2020-11.tar.xz
wget https://metrics.torproject.org/userstats-relay-country.csv
wget https://collector.torproject.org/archive/onionperf/onionperf-2020-11.tar.xz
wget -O bandwidth-2020-11.csv "https://metrics.torproject.org/bandwidth.csv?start=2020-11-01&end=2020-11-30"

tar xaf consensuses-2020-11.tar.xz
tar xaf server-descriptors-2020-11.tar.xz
tar xaf onionperf-2020-11.tar.xz
xz -k -d tmodel-ccs2018.github.io/data/shadow/network/atlas-lossless.201801.shadow113.graphml.xml.xz

GIT_SSL_NO_VERIFY=1 git clone https://github.com/tmodel-ccs2018/tmodel-ccs2018.github.io.git

GIT_SSL_NO_VERIFY=1 git clone https://git.torproject.org/tor.git
cd tor
./autogen.sh
./configure --disable-asciidoc --disable-unittests --disable-manpage --disable-html-manual
make
cd ..

export PATH=${PATH}:`pwd`/tor/src/core/or:`pwd`/tor/src/app:`pwd`/tor/src/tools

tornettools stage \
    consensuses-2020-11 \
    server-descriptors-2020-11 \
    userstats-relay-country.csv \
    --onionperf_data_path onionperf-2020-11 \
    --bandwidth_data_path bandwidth-2020-11.csv \
    --geoip_path tor/src/config/geoip

for n in 0.01 0.1
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
                        relayinfo_staging_2020-11-01--2020-12-01.json \
                        userinfo_staging_2020-11-01--2020-12-01.json \
                        tmodel-ccs2018.github.io \
                        --network_scale ${n} \
                        --process_scale ${p} \
                        --server_scale ${s} \
                        --torperf_scale ${t} \
                        --load_scale ${l} \
                        --atlas tmodel-ccs2018.github.io/data/shadow/network/atlas-lossless.201801.shadow113.graphml.xml \
                        --prefix tornet-${n}n-${p}p-${s}s-${t}t-${l}l
                done
            done
        done
    done
done

tornettools simulate tornet-0.01n-0.01p-0.01s-0.01t-1.0l
tornettools parse tornet-0.01n-0.01p-0.01s-0.01t-1.0l
tornettools plot tornet-0.01n-0.01p-0.01s-0.01t-1.0l --tor_metrics_path tor_metrics_2020-11-01--2020-11-30.json --prefix pdfs
tornettools archive tornet-0.01n-0.01p-0.01s-0.01t-1.0l
