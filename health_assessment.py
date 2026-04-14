import argparse
from pathlib import Path

import numpy as np
import pandas as pd


def read_csv_with_fallback(csv_path: Path) -> pd.DataFrame:
    encodings = ["utf-8-sig", "utf-8", "gb18030", "gbk", "latin1"]
    last_error = None
    for enc in encodings:
        try:
            return pd.read_csv(csv_path, encoding=enc)
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"Failed to read CSV with fallback encodings: {last_error}")


def robust_mad(values: np.ndarray) -> float:
    median = np.median(values)
    mad = np.median(np.abs(values - median))
    return float(1.4826 * mad + 1e-8)


def compute_health_index(df: pd.DataFrame, baseline_ratio: float = 0.2) -> tuple[pd.DataFrame, list[str], np.ndarray]:
    df_num = df.select_dtypes(include=[np.number]).copy()
    if df_num.shape[1] < 2:
        raise ValueError("Need at least 2 numeric columns (time + features or multiple features).")

    n_rows = len(df_num)
    base_n = max(30, int(n_rows * baseline_ratio))
    base_n = min(base_n, max(5, n_rows // 2))

    # Prefer using all numeric columns except a monotonic time-like first column.
    feature_cols = list(df_num.columns)
    first_col = feature_cols[0]
    first_values = df_num[first_col].to_numpy()
    if np.all(np.diff(first_values) >= 0) or np.all(np.diff(first_values) <= 0):
        feature_cols = feature_cols[1:]
    if not feature_cols:
        feature_cols = list(df_num.columns)

    X = df_num[feature_cols].replace([np.inf, -np.inf], np.nan)
    X = X.interpolate(limit_direction="both").bfill().ffill()
    Xv = X.to_numpy(dtype=float)

    baseline = Xv[:base_n, :]
    end_window = Xv[-base_n:, :]

    med = np.median(baseline, axis=0)
    scale = np.array([robust_mad(baseline[:, i]) for i in range(baseline.shape[1])])

    # Estimate degradation direction by comparing baseline vs end-window means.
    drift = np.mean(end_window, axis=0) - np.mean(baseline, axis=0)
    direction = np.where(np.abs(drift) < 1e-10, 1.0, np.sign(drift))

    z = (Xv - med) / scale
    degradation = np.clip(direction * z, 0.0, None)

    # Weight features by drift magnitude so more sensitive indicators contribute more.
    w = np.abs(drift)
    if np.all(w < 1e-12):
        w = np.ones_like(w)
    w = w / (np.sum(w) + 1e-12)

    fused = degradation @ w
    q95 = float(np.quantile(fused, 0.95) + 1e-8)
    score = np.clip(fused / q95, 0.0, 3.0)

    # Health index definition requested by user: 0 is healthy, 1 is close to failed.
    health = 1.0 - np.exp(-1.8 * score)
    health = np.maximum.accumulate(health)

    out = df.copy()
    out["fault_risk_score"] = score
    out["health_index"] = np.clip(health, 0.0, 1.0)
    return out, feature_cols, drift


def save_comparison_plot(
    result: pd.DataFrame,
    x_vals: np.ndarray,
    x_label: str,
    feature_cols: list[str],
    title: str,
    plot_path: Path,
) -> None:
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(11, 5.2), dpi=120)

    for idx, col in enumerate(feature_cols, start=1):
        ax.plot(x_vals, result[col].to_numpy(), linewidth=1.0, alpha=0.75, label=f"raw_indicator_{idx}")

    ax2 = ax.twinx()
    ax2.plot(x_vals, result["health_index"].to_numpy(), color="#d62728", linewidth=2.0, label="health_index")
    ax2.set_ylim(0.0, 1.0)

    ax.set_ylabel("Raw Indicator Value")
    ax2.set_ylabel("Health Index (0=healthy, 1=failed)")
    ax.set_xlabel(x_label)
    ax.set_title(title)
    ax.grid(alpha=0.25)

    lines1, labels1 = ax.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax.legend(lines1 + lines2, labels1 + labels2, loc="upper left", fontsize=8, ncol=2)

    fig.tight_layout()
    plot_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(plot_path)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description="Bearing fault health assessment (0-1)")
    parser.add_argument("--input", required=True, help="Input CSV path")
    parser.add_argument("--output", default="data/health_assessment_result.csv", help="Output CSV path")
    parser.add_argument("--baseline-ratio", type=float, default=0.2, help="Baseline ratio in (0, 0.5]")
    parser.add_argument("--plot", action="store_true", help="Export health index curve PNG")
    parser.add_argument("--plot-file", default="data/health_index_curve.png", help="PNG path for health curve")
    args = parser.parse_args()

    if not (0.01 <= args.baseline_ratio <= 0.5):
        raise ValueError("--baseline-ratio must be between 0.01 and 0.5")

    csv_path = Path(args.input)
    if not csv_path.exists():
        raise FileNotFoundError(f"Input CSV not found: {csv_path}")

    df = read_csv_with_fallback(csv_path)
    result, feature_cols, drift = compute_health_index(df, baseline_ratio=args.baseline_ratio)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output_path, index=False, encoding="utf-8-sig")

    if args.plot:
        num_cols = result.select_dtypes(include=[np.number]).columns.tolist()
        x_col = num_cols[0] if num_cols else None
        x_vals = result[x_col].to_numpy() if x_col else np.arange(len(result))
        x_label = x_col if (x_col and str(x_col).isascii()) else "Time"

        plot_base = Path(args.plot_file)
        stem = plot_base.stem
        suffix = plot_base.suffix if plot_base.suffix else ".png"

        full_plot_path = plot_base.with_name(f"{stem}_all{suffix}")
        save_comparison_plot(
            result=result,
            x_vals=x_vals,
            x_label=x_label if x_col else "Sample",
            feature_cols=feature_cols,
            title="All Raw Indicators vs Health Index",
            plot_path=full_plot_path,
        )

        # Plot top-3 most drifting raw indicators for visual comparison.
        top_n = min(3, len(feature_cols))
        top_idx = np.argsort(np.abs(drift))[-top_n:][::-1]
        top_cols = [feature_cols[int(i)] for i in top_idx]
        top_plot_path = plot_base.with_name(f"{stem}_top3{suffix}")
        save_comparison_plot(
            result=result,
            x_vals=x_vals,
            x_label=x_label if x_col else "Sample",
            feature_cols=top_cols,
            title="Top3 Raw Indicators vs Health Index",
            plot_path=top_plot_path,
        )

    start_health = float(result["health_index"].iloc[0])
    end_health = float(result["health_index"].iloc[-1])
    max_health = float(result["health_index"].max())

    print(f"rows={len(result)}")
    print(f"start_health={start_health:.6f}")
    print(f"end_health={end_health:.6f}")
    print(f"max_health={max_health:.6f}")
    print(f"output={output_path.resolve()}")
    if args.plot:
        print(f"plot_all={full_plot_path.resolve()}")
        print(f"plot_top3={top_plot_path.resolve()}")


if __name__ == "__main__":
    main()
