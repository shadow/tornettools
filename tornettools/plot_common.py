from matplotlib import use as mp_use
mp_use('Agg') # for systems without X11
import matplotlib.pyplot as pyplot
from matplotlib.backends.backend_pdf import PdfPages

from matplotlib import scale as mscale
from matplotlib import transforms as mtransforms
from matplotlib.ticker import FixedFormatter, FixedLocator
from matplotlib import rcParams

from scipy.stats import scoreatpercentile as score, t
from numpy import ma, mean, median, std, log10, quantile, sqrt, linspace, var
from numpy import array as nparray, log10 as nplog10

from tornettools.util import which

DEFAULT_COLORS = ['C0', 'C1', 'C2', 'C3', 'C4', 'C5', 'C6', 'C7', 'C8', 'C9', 'C10', 'C11']
DEFAULT_LINESTYLES = ['-', ':', '--', '-.']

class TailLog(mscale.ScaleBase):
    name = 'taillog'

    def __init__(self, axis, **kwargs):
        mscale.ScaleBase.__init__(self, axis)
        self.nines = kwargs.get('nines', 2)

    def get_transform(self):
        return self.Transform(self.nines)

    def set_default_locators_and_formatters(self, axis):
        # axis.set_major_locator(FixedLocator(
        #         nparray([1-10**(-k) for k in range(1+self.nines)])))
        # axis.set_major_formatter(FixedFormatter(
        #         [str(1-10**(-k)) for k in range(1+self.nines)]))

        #majloc = [10**(-1*self.nines)*k for k in range(100) if k >= 90 or k % 10 == 0]
        majloc = [0.0, 0.9, 0.99]
        majloc = [round(k, self.nines) for k in majloc]
        axis.set_major_locator(FixedLocator(nparray(majloc)))
        axis.set_major_formatter(FixedFormatter([str(k) for k in majloc]))

        minloc = [10**(-1*self.nines)*k for k in range(100) if k not in [0, 90, 99] and (k > 90 or k % 10 == 0)]
        minloc = [round(k, self.nines) for k in minloc]
        axis.set_minor_locator(FixedLocator(nparray(minloc)))
        axis.set_minor_formatter(FixedFormatter([str(k) for k in minloc]))

    def limit_range_for_scale(self, vmin, vmax, minpos):
        return vmin, min(1 - 10**(-self.nines), vmax)

    class Transform(mtransforms.Transform):
        input_dims = 1
        output_dims = 1
        is_separable = True

        def __init__(self, nines):
            mtransforms.Transform.__init__(self)
            self.nines = nines

        def transform_non_affine(self, a):
            masked = ma.masked_where(a > 1-10**(-1-self.nines), a)
            if masked.mask.any():
                return -ma.log10(1-a)
            else:
                return -nplog10(1-a)

        def inverted(self):
            return TailLog.InvertedTransform(self.nines)

    class InvertedTransform(mtransforms.Transform):
        input_dims = 1
        output_dims = 1
        is_separable = True

        def __init__(self, nines):
            mtransforms.Transform.__init__(self)
            self.nines = nines

        def transform_non_affine(self, a):
            return 1. - 10**(-a)

        def inverted(self):
            return TailLog.Transform(self.nines)

mscale.register_scale(TailLog)

def __get_error_factor(k, confidence):
    return t.ppf(confidence/2 + 0.5, k-1)/sqrt(k-1)

def __compute_sample_mean_and_error(bucket_list, confidence):
    means, mins, maxs = [], [], []
    z_cache = {}

    for i, bucket in enumerate(bucket_list):
        # get the error factor from the student's t distribution
        # and cache the result to minimize the number of ppf lookups
        k = len(bucket)
        z = z_cache.setdefault(k, __get_error_factor(k, confidence))

        # bucket will be a list of items, each of which will either
        # be the value (a number), or a list of two numbers (the
        # value and the resolution).  If it's just a value, the
        # correspinding resolution is 0.  Create the list of values
        # and the list of resolutions.
        emp_sample = [getfirstorself(item) for item in bucket]
        resolutions = [getsecondorzero(item) for item in bucket]

        # The resolution variance is 1/12 of the sum of the squares
        # of the resolutions
        resolution_variance = sum([res**2 for res in resolutions])/12

        m, v = mean(emp_sample), var(emp_sample)
        s = sqrt(v + resolution_variance)
        e = z*s

        means.append(m)
        mins.append(max(0, m-e))
        maxs.append(m+e)

    return means, mins, maxs

# compute a cdf with confidence intervals based on the dataset and plot it on axis
# dataset is a list of data
# confidence is the confidence interval level (eg 0.95 for 95% CIs)
# kwargs is passed to the plot function
# each data may be a list of values, or a list of [value, resolution] items
def draw_cdf_ci(axis, dataset, confidence=0.95, **kwargs):
    y = list(linspace(0, 0.99, num=1000))
    quantile_buckets = {q:[] for q in y}

    # we should have one empirical value for each simulation (ie data) for each quantile
    for data in dataset:
        num_items = len(data)
        if num_items == 0:
            continue

        data.sort(key=getfirstorself)

        for q in quantile_buckets:
            val_at_q = data[int((num_items-1) * q)]
            quantile_buckets[q].append(val_at_q)

    # compute the confidence intervals for each quantile
    bucket_list = [quantile_buckets[q] for _, q in enumerate(y)]
    x, x_min, x_max = __compute_sample_mean_and_error(bucket_list, confidence)

    # for debugging
    #axis.plot(x_min, y, label=f"k={k}", color=colors[l%len(colors)], linestyle=linestyle)
    #axis.plot(x_max, y, label=f"k={k}", color=colors[l%len(colors)], linestyle=linestyle)

    # if we wanted a ccdf
    #y = [1-q for q in y]

    plot_line = axis.plot(x, y, **kwargs)

    kwargs['alpha'] = 0.5
    kwargs['linestyle'] = '-'

    axis.fill_betweenx(y, x_min, x_max, **kwargs)
    fill_line = axis.fill(0, 0, color=kwargs['color'], alpha=kwargs['alpha'])

    return (plot_line[0], fill_line[0])

# compute a cdf from the data and plot it on the axis
# data may be a list of values, or a list of [value, resolution] items
def draw_cdf(axis, data, **kwargs):
    d = [getfirstorself(item) for item in data]
    y = list(linspace(0.0, 1.0, num=1000))
    x = quantile(d, y)
    plot_line = axis.plot(x, y, **kwargs)
    return plot_line[0]

# plot a line with error bars
# x is a list of x-coordinates
# ydata is a list of 'datas' for each x-coordinate
# each 'data' may be a list of values, or a list of [value, resolution] items
def draw_line_ci(axis, x, ydata, confidence=0.95, **kwargs):
    # compute the confidence intervals for each x-coordinate
    bucket_list = [ydata[i] for i, _ in enumerate(x)]
    y, y_min, y_max = __compute_sample_mean_and_error(bucket_list, confidence)

    plot_line = axis.plot(x, y, **kwargs)

    kwargs['alpha'] = 0.5
    kwargs['linestyle'] = '-'

    axis.fill_between(x, y_min, y_max, **kwargs)
    fill_line = axis.fill(0, 0, color=kwargs['color'], alpha=kwargs['alpha'])

    return (plot_line[0], fill_line[0])

# plot a line with error bars
# x is a list of x-coordinates
# ydata may be a list of values, or a list of [value, resolution] items (one for each x-coordinate)
def draw_line(axis, x, ydata, **kwargs):
    y = []
    for i, _ in enumerate(x):
        data = [getfirstorself(item) for item in ydata[i]]
        y.append(data)
    plot_line = axis.plot(x, y, **kwargs)
    return plot_line[0]

## helper - if the passed item is a list, return its first
## element; otherwise, return the item itself
def getfirstorself(item):
    if isinstance(item, list):
        return item[0]
    return item

## helper - if the passed item is a list, return its second
## element; otherwise, return 0
def getsecondorzero(item):
    if isinstance(item, list):
        return item[1]
    return 0

def log_stats(filename, msg, dist):
    #from numpy import mean, median, std
    #from scipy.stats import scoreatpercentile as score
    b = sorted(dist)#.values()
    b = [getfirstorself(item) for item in b]
    with open(filename, 'a') as outf:
        print(msg, file=outf)
        print("min={} q1={} median={} q3={} max={} mean={} stddev={}".format(min(b), score(b, 25), median(b), score(b, 75), max(b), mean(b), std(b)), file=outf)

def set_plot_options():
    options = {
        #'backend': 'PDF',
        'font.size': 12,
        'figure.figsize': (4,3),
        'figure.dpi': 100.0,
        'grid.color': '0.1',
        'grid.linestyle': ':',
        'grid.linewidth': 0.5,
        'axes.grid' : True,
        #'axes.grid.axis' : 'y',
        #'axes.axisbelow': True,
        'axes.titlesize' : 14,
        'axes.labelsize' : 10,
        'axes.formatter.limits': (-4,4),
        'xtick.labelsize' : 8,
        'ytick.labelsize' : 8,
        'lines.linewidth' : 2.0,
        'lines.markeredgewidth' : 0.5,
        'lines.markersize' : 10,
        'legend.fontsize' : 10,
        'legend.fancybox' : False,
        'legend.shadow' : False,
        'legend.borderaxespad' : 0.5,
        'legend.columnspacing' : 1.0,
        'legend.numpoints' : 1,
        'legend.handletextpad' : 0.25,
        'legend.handlelength' : 2.0,
        'legend.labelspacing' : 0.25,
        'legend.markerscale' : 1.0,
    }

    options_latex = {
        # turn on the following to embedd fonts; requires latex
        'ps.useafm' : True,
        'pdf.use14corefonts' : True,
        'text.usetex' : True,
        # 'text.latex.preamble': r'\boldmath',
        'text.latex.preamble': r'\usepackage{amsmath}',
    }

    for option_key in options:
        rcParams[option_key] = options[option_key]

    if which("latex") != None:
        for option_key in options_latex:
            rcParams[option_key] = options_latex[option_key]

    if 'figure.max_num_figures' in rcParams:
        rcParams['figure.max_num_figures'] = 50
    if 'figure.max_open_warning' in rcParams:
        rcParams['figure.max_open_warning'] = 50
    if 'legend.ncol' in rcParams:
        rcParams['legend.ncol'] = 50
