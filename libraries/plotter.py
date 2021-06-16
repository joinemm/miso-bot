import matplotlib.pyplot as plt
import matplotlib.ticker as plticker
import numpy as np
from scipy.interpolate import make_interp_spline


def create_graph(
    data,
    usercolor,
    title=None,
    dimensions=(6, 3),
    draw=False,
    background_color="#2f3136",
):
    plt.rcParams["figure.figsize"] = [dimensions[0], dimensions[1]]
    T = np.array(list(range(0, len(data))))
    xnew = np.linspace(T.min(), T.max(), 240)
    spl = make_interp_spline(T, data, k=3)
    power_smooth = spl(xnew)

    # remove under 0
    power = []
    for x in power_smooth:
        power.append(min(x, 0))

    power_smooth = np.array(power)

    fig = plt.figure()
    fig.patch.set_facecolor(background_color)
    if title is not None:
        fig.suptitle(title, color="white")
    plt.autoscale(tight=True)
    plt.plot(xnew, power_smooth, color=usercolor)
    ax = plt.gca()
    loc = plticker.MultipleLocator(base=1.0)
    ax.xaxis.set_major_locator(loc)
    ax.set_facecolor(background_color)
    ax.set_xlabel("Hour (UTC)")
    # ax.set_ylabel('XP gain')

    ax.spines["bottom"].set_color("white")
    ax.spines["left"].set_color("white")
    ax.xaxis.label.set_color("white")
    ax.yaxis.label.set_color("white")
    ax.spines["right"].set_visible(False)
    ax.spines["top"].set_visible(False)
    ax.tick_params(axis="x", colors="white")
    ax.tick_params(axis="y", colors="white")
    plt.fill_between(xnew, power_smooth, color=usercolor, alpha=0.2)
    if draw:
        plt.show()
    plt.savefig("downloads/graph.png", facecolor=background_color, bbox_inches="tight")
    plt.close()


def time_series_graph(frame, data, color, background_color="#2f3136"):
    x = np.array(frame)
    y = np.array(data)
    fig = plt.figure()
    fig.patch.set_facecolor(background_color)
    plt.autoscale(tight=True)
    plt.plot(x, y, color=color)

    ax = plt.gca()
    ax.set_facecolor(background_color)

    ax.spines["bottom"].set_color("white")
    ax.spines["left"].set_color("white")
    ax.xaxis.label.set_color("white")
    ax.yaxis.label.set_color("white")
    ax.spines["right"].set_visible(False)
    ax.spines["top"].set_visible(False)
    ax.tick_params(axis="x", colors="white")
    ax.tick_params(axis="y", colors="white")
    ax.ticklabel_format(useOffset=False, style="plain", axis="y")
    ax.get_yaxis().get_major_formatter().set_useOffset(False)
    ax.get_yaxis().get_major_formatter().set_scientific(False)
    plt.xticks(rotation=45)

    plt.savefig("downloads/graph.png", facecolor=background_color, bbox_inches="tight")
    plt.close()
