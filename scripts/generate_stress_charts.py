#!/usr/bin/env python3
"""Turn a stress campaign's captured metrics into report-ready PNG charts.

Reads the artifacts scripts/seed_stress_corpus.py, the infra/k6/stress.js
run, scripts/run_fault_scenario.py, and scripts/sample_resources.sh produce,
plus a queue-drain series read directly from Prometheus (already scraping
trialscribe_jobs_total per feature 25 — this script does not add new
instrumentation). Colors follow the validated default palette in the
dataviz skill: fixed categorical order, status colors reserved for
pass/fail state, one hue light->dark for ordered magnitude, one axis per
chart. Run with matplotlib available ephemerally so the pinned stack does
not gain a permanent plotting dependency:

    uv run --with matplotlib==3.11.2 python scripts/generate_stress_charts.py
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]

SURFACE = "#fcfcfb"
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRID = "#e1e0d9"
BASELINE = "#c3c2b7"

CATEGORICAL = {
    "blue": "#2a78d6",
    "orange": "#eb6834",
    "aqua": "#1baf7a",
    "yellow": "#eda100",
    "magenta": "#e87ba4",
    "green": "#008300",
    "violet": "#4a3aa7",
    "red": "#e34948",
}
STATUS = {
    "good": "#0ca30c",
    "warning": "#fab219",
    "serious": "#ec835a",
    "critical": "#d03b3b",
}
SEQUENTIAL_ORDINAL = ["#86b6ef", "#5598e7", "#2a78d6", "#184f95"]

RESOURCE_CONTAINERS = ["gateway", "worker", "jobs", "postgres", "chroma"]
RESOURCE_COLORS = [
    CATEGORICAL["blue"],
    CATEGORICAL["orange"],
    CATEGORICAL["aqua"],
    CATEGORICAL["yellow"],
    CATEGORICAL["magenta"],
]


def _style_axes(ax: plt.Axes) -> None:
    ax.set_facecolor(SURFACE)
    for spine_name in ("top", "right"):
        ax.spines[spine_name].set_visible(False)
    for spine_name in ("left", "bottom"):
        ax.spines[spine_name].set_color(BASELINE)
    ax.tick_params(colors=INK_MUTED, labelsize=9)
    ax.grid(True, axis="y", color=GRID, linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)


def _new_figure(figsize: tuple[float, float] = (8, 4.5)) -> tuple[plt.Figure, plt.Axes]:
    fig, ax = plt.subplots(figsize=figsize, dpi=150)
    fig.patch.set_facecolor(SURFACE)
    _style_axes(ax)
    return fig, ax


def _save(fig: plt.Figure, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(out_path, facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"wrote {out_path}")


def read_json(path: Path) -> dict | None:
    if not path.is_file():
        print(f"skipping (not found): {path}")
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def chart_latency_percentiles(k6_summary: dict, out_path: Path) -> None:
    metrics = k6_summary.get("metrics", {})
    duration = metrics.get("http_req_duration", {})
    order = [("p50", "med"), ("p90", "p(90)"), ("p95", "p(95)"), ("p99", "p(99)")]
    labels: list[str] = []
    values: list[float] = []
    for label, key in order:
        if key in duration:
            labels.append(label)
            values.append(float(duration[key]))
    if not values:
        print("skipping latency chart: no http_req_duration percentiles in k6 summary")
        return
    fig, ax = _new_figure()
    bars = ax.bar(labels, values, color=SEQUENTIAL_ORDINAL[: len(values)], width=0.6, zorder=2)
    for bar, value in zip(bars, values, strict=True):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            value,
            f"{value:.0f} ms",
            ha="center",
            va="bottom",
            fontsize=9,
            color=INK_PRIMARY,
        )
    ax.set_ylabel("HTTP request duration (ms)", color=INK_SECONDARY)
    ax.set_title("Gateway request latency — spike + soak scenarios", color=INK_PRIMARY, loc="left")
    _save(fig, out_path)


def chart_check_pass_rates(k6_summary: dict, out_path: Path) -> None:
    root_group = k6_summary.get("root_group", {})
    checks = root_group.get("checks", {})
    if not checks:
        print("skipping check pass-rate chart: no checks in k6 summary")
        return
    rows: list[tuple[str, float]] = []
    for name, result in checks.items():
        passes = result.get("passes", 0)
        fails = result.get("fails", 0)
        total = passes + fails
        rate = 100.0 * passes / total if total else 0.0
        rows.append((name, rate))
    rows.sort(key=lambda row: row[1])
    labels = [name for name, _ in rows]
    rates = [rate for _, rate in rows]

    def status_color(rate: float) -> str:
        if rate >= 99.0:
            return STATUS["good"]
        if rate >= 95.0:
            return STATUS["warning"]
        return STATUS["critical"]

    colors = [status_color(rate) for rate in rates]
    fig, ax = _new_figure(figsize=(8, 0.45 * len(labels) + 1.5))
    bars = ax.barh(labels, rates, color=colors, height=0.6, zorder=2)
    for bar, rate in zip(bars, rates, strict=True):
        ax.text(
            min(rate + 1, 101),
            bar.get_y() + bar.get_height() / 2,
            f"{rate:.1f}%",
            va="center",
            fontsize=9,
            color=INK_PRIMARY,
        )
    ax.set_xlim(0, 108)
    ax.set_xlabel("Check pass rate (%)", color=INK_SECONDARY)
    ax.set_title("Request checks by endpoint — spike + soak scenarios", color=INK_PRIMARY, loc="left")
    _save(fig, out_path)


def read_resource_samples(csv_path: Path) -> dict[str, dict[str, list[tuple[float, float]]]]:
    series: dict[str, dict[str, list[tuple[float, float]]]] = {
        "cpu": defaultdict(list),
        "mem": defaultdict(list),
    }
    if not csv_path.is_file():
        return series
    with csv_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        start: float | None = None
        for row in reader:
            timestamp = float(row["timestamp"])
            if start is None:
                start = timestamp
            elapsed = timestamp - start
            name = row["container"]
            short_name = next(
                (candidate for candidate in RESOURCE_CONTAINERS if name.endswith(f"-{candidate}-1")),
                None,
            )
            if short_name is None:
                continue
            cpu = float(row["cpu_percent"].rstrip("%") or 0.0)
            mem = float(row["mem_percent"].rstrip("%") or 0.0)
            series["cpu"][short_name].append((elapsed, cpu))
            series["mem"][short_name].append((elapsed, mem))
    return series


def chart_resource_usage(csv_path: Path, out_dir: Path) -> None:
    series = read_resource_samples(csv_path)
    if not series["cpu"] and not series["mem"]:
        print(f"skipping resource charts: no usable rows in {csv_path}")
        return
    for metric_key, metric_label, filename in (
        ("cpu", "CPU usage (% of container limit)", "stress-resource-cpu.png"),
        ("mem", "Memory usage (% of container limit)", "stress-resource-memory.png"),
    ):
        fig, ax = _new_figure()
        plotted = False
        for index, container in enumerate(RESOURCE_CONTAINERS):
            points = sorted(series[metric_key].get(container, []))
            if not points:
                continue
            xs = [point[0] for point in points]
            ys = [point[1] for point in points]
            ax.plot(
                xs,
                ys,
                label=container,
                color=RESOURCE_COLORS[index % len(RESOURCE_COLORS)],
                linewidth=2,
                zorder=3,
            )
            plotted = True
        if not plotted:
            plt.close(fig)
            continue
        ax.set_xlabel("Seconds since sampling started", color=INK_SECONDARY)
        ax.set_ylabel(metric_label, color=INK_SECONDARY)
        ax.set_title(f"Container {metric_key.upper()} during the stress campaign", color=INK_PRIMARY, loc="left")
        ax.legend(frameon=False, labelcolor=INK_SECONDARY, fontsize=9, loc="upper left")
        _save(fig, out_dir / filename)


def prometheus_query_range(prometheus_url: str, query: str, start: float, end: float, step: str) -> list[list[float]]:
    url = (
        f"{prometheus_url}/api/v1/query_range?query={urllib.parse.quote(query)}"
        f"&start={start}&end={end}&step={step}"
    )
    try:
        with urllib.request.urlopen(url, timeout=15.0) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError) as error:
        print(f"warning: Prometheus query failed ({error}): {query}")
        return []
    results = payload.get("data", {}).get("result", [])
    if not results:
        return []
    summed: dict[float, float] = defaultdict(float)
    for series in results:
        for timestamp, value in series.get("values", []):
            summed[float(timestamp)] += float(value)
    return sorted(summed.items())


def chart_queue_drain(
    seed_summary: dict,
    prometheus_url: str,
    out_path: Path,
    *,
    end_time: float,
) -> None:
    started = seed_summary.get("started_at")
    finished = seed_summary.get("finished_at")
    if not started or not finished:
        print("skipping queue-drain chart: seed summary has no timestamps")
        return
    succeeded = prometheus_query_range(
        prometheus_url,
        'trialscribe_jobs_total{kind="index_document",outcome="succeeded"}',
        started - 5,
        end_time,
        "10s",
    )
    failed = prometheus_query_range(
        prometheus_url,
        'trialscribe_jobs_total{kind="index_document",outcome="failed"}',
        started - 5,
        end_time,
        "10s",
    )
    if not succeeded and not failed:
        print("skipping queue-drain chart: no data from Prometheus")
        return
    fig, ax = _new_figure()
    if succeeded:
        xs = [(timestamp - started) for timestamp, _ in succeeded]
        ys = [value for _, value in succeeded]
        ax.plot(xs, ys, label="succeeded", color=CATEGORICAL["blue"], linewidth=2, zorder=3)
        ax.fill_between(xs, ys, color=CATEGORICAL["blue"], alpha=0.08, zorder=2)
    if failed:
        xs = [(timestamp - started) for timestamp, _ in failed]
        ys = [value for _, value in failed]
        ax.plot(xs, ys, label="failed", color=CATEGORICAL["red"], linewidth=2, zorder=3)
    ax.set_xlabel("Seconds since seeding started", color=INK_SECONDARY)
    ax.set_ylabel("index_document jobs (cumulative)", color=INK_SECONDARY)
    ax.set_title("Ingestion queue drain during corpus seeding", color=INK_PRIMARY, loc="left")
    ax.legend(frameon=False, labelcolor=INK_SECONDARY, fontsize=9, loc="upper left")
    _save(fig, out_path)


def chart_circuit_breaker(fault_scenario: dict, out_path: Path) -> None:
    series = fault_scenario.get("circuit_state_series", [])
    phases = fault_scenario.get("phases", {})
    if not series:
        print("skipping circuit-breaker chart: no circuit_state_series")
        return
    origin = series[0][0]
    xs = [point[0] - origin for point in series]
    ys = [point[1] for point in series]
    fig, ax = _new_figure()
    for name, color in (("baseline", STATUS["good"]), ("faulted", STATUS["critical"]), ("recovery", STATUS["good"])):
        phase = phases.get(name)
        if not phase:
            continue
        ax.axvspan(
            phase["started_at"] - origin,
            phase["finished_at"] - origin,
            color=color,
            alpha=0.10,
            zorder=1,
        )
    ax.step(xs, ys, where="post", color=INK_PRIMARY, linewidth=2, zorder=3)
    ax.set_yticks([0, 1, 2])
    ax.set_yticklabels(["closed", "half-open", "open"])
    ax.set_ylim(-0.3, 2.3)
    ax.set_xlabel("Seconds since baseline phase started", color=INK_SECONDARY)
    ax.set_ylabel("Circuit breaker state", color=INK_SECONDARY)
    ax.set_title(
        "Fake chat provider fault injection — circuit breaker state",
        color=INK_PRIMARY,
        loc="left",
    )
    _save(fig, out_path)


def parse_args() -> argparse.Namespace:
    results_dir = REPO_ROOT / "infra" / "k6" / "results"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed-summary", default=str(results_dir / "seed-summary.json"))
    parser.add_argument("--k6-summary", default=str(results_dir / "stress-summary.json"))
    parser.add_argument("--fault-scenario", default=str(results_dir / "fault-scenario.json"))
    parser.add_argument("--resource-csv", default=str(results_dir / "resource-samples.csv"))
    parser.add_argument("--prometheus-url", default=os.environ.get("PROMETHEUS_URL", "http://127.0.0.1:9090"))
    parser.add_argument("--out-dir", default=str(REPO_ROOT / "docs" / "assets"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    out_dir = Path(args.out_dir)

    k6_summary = read_json(Path(args.k6_summary))
    if k6_summary is not None:
        chart_latency_percentiles(k6_summary, out_dir / "stress-latency-percentiles.png")
        chart_check_pass_rates(k6_summary, out_dir / "stress-check-pass-rates.png")

    chart_resource_usage(Path(args.resource_csv), out_dir)

    seed_summary = read_json(Path(args.seed_summary))
    if seed_summary is not None:
        chart_queue_drain(
            seed_summary,
            args.prometheus_url,
            out_dir / "stress-queue-drain.png",
            end_time=time.time(),
        )

    fault_scenario = read_json(Path(args.fault_scenario))
    if fault_scenario is not None:
        chart_circuit_breaker(fault_scenario, out_dir / "stress-circuit-breaker.png")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
