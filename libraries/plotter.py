import numpy as np
import matplotlib.pyplot as plt
from scipy.interpolate import make_interp_spline
import matplotlib.ticker as plticker


def create_graph(data, usercolor, title=None, dimensions=(6, 3), draw=False):
    plt.rcParams['figure.figsize'] = [dimensions[0], dimensions[1]]
    T = np.array(list(range(0, len(data))))
    xnew = np.linspace(T.min(), T.max(), 240)
    spl = make_interp_spline(T, data, k=3)
    power_smooth = spl(xnew)

    # remove under 0
    power = []
    for x in power_smooth:
        if x < 0:
            x = 0
        power.append(x)

    power_smooth = np.array(power)

    fig = plt.figure()
    fig.patch.set_facecolor('#1D1E22')
    if title is not None:
        fig.suptitle(title, color='white')
    plt.autoscale(tight=True)
    plt.plot(xnew, power_smooth, color=usercolor)
    ax = plt.gca()
    loc = plticker.MultipleLocator(base=1.0)
    ax.xaxis.set_major_locator(loc)
    ax.set_facecolor('#1D1E22')
    ax.set_xlabel('Hour')
    # ax.set_ylabel('XP gain')

    ax.spines['bottom'].set_color('white')
    ax.spines['left'].set_color('white')
    ax.xaxis.label.set_color('white')
    ax.yaxis.label.set_color('white')
    ax.spines['right'].set_visible(False)
    ax.spines['top'].set_visible(False)
    ax.tick_params(axis='x', colors='white')
    ax.tick_params(axis='y', colors='white')
    plt.fill_between(xnew, power_smooth, color=usercolor, alpha=0.2)
    if draw:
        plt.show()
    plt.savefig('downloads/graph.png', facecolor='#1D1E22', bbox_inches='tight')
    plt.close()
