import os

from bisect import bisect

class GeoIP():
    # geoip_path is the path to a geoip file distributed with the tor source code
    # e.g.: path/to/tor/src/config/geoip
    def __init__(self, geoip_path):
        self.geoip_path = geoip_path

        self.boundaries = []
        self.codes = {}

        # parse the geoip file
        # see here for supported range queries using bisection
        # https://stackoverflow.com/questions/23639361/fast-checking-of-ranges-in-python
        if os.path.exists(self.geoip_path):
            with open(self.geoip_path, "r") as f:
                for line in f:
                    # ignore comment lines
                    if line[0] == "#":
                        continue
                    # normal lines contain ranges and country code, e.g.: 123,125,US
                    # the geoip file may contain the same number twice, e.g.: 123,123,US
                    # so I assume the range are already half-open intervals
                    parts = line.strip().split(',')
                    low, high, code = int(parts[0]), int(parts[1]), parts[2]
                    # enforce assumption that the data is sorted
                    if len(self.boundaries) > 0:
                        assert self.boundaries[-1] <= low
                    assert low <= high
                    # add the half-open interval boundaries
                    self.boundaries.append(low)
                    self.boundaries.append(high)
                    # make sure we can look up the code later
                    self.codes[low] = code

    def ip_to_country_code(self, ip_address):
        # Convert a IPv4 address into a 32-bit integer.
        ip_array = ip_address.split('.')
        if len(ip_array) == 4:
            ipnum = (int(ip_array[0]) * 16777216) + (int(ip_array[1]) * 65536) + (int(ip_array[2]) * 256) + int(ip_array[3])
            # check if ip is in an interval from the parsed geoip data
            b = bisect(self.boundaries, ipnum)
            if (b % 2) == 1:
                # the ip is in a known interval defined in the geoip file.
                # b holds the index of the right side of the interval.
                # right_index = b
                left_index = b - 1
                low = self.boundaries[left_index]
                code = self.codes[low]
                return "{}".format(code)
            else:
                # ip is not in an interval defined in the geoip file
                pass
        # we don't know the country code
        return "AP"
