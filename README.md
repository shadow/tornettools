
# process relay and user info
shadowtortools stage /scratch/201901/tor/consensuses-2019-01 /scratch/201901/tor/server-descriptors-2019-01 /scratch/201901/tor/userstats-relay-country.csv -g ~/dev/tor/src/config/geoip


export PATH=${PATH}:~/dev/shadow-plugin-tor/build/tor/src/core/or:~/dev/shadow-plugin-tor/build/tor/src/app:~/dev/shadow-plugin-tor/build/tor/src/tools
shadowtortools generate relayinfo_staging_2019-01-01--2019-02-01.json userinfo_staging_2019-01-01--2019-02-01.json -p network1
