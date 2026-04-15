import argparse
from pathlib import Path

import numpy as np
import pandas as pd

"""轴承健康度评估命令行工具。

核心输出：
- fault_risk_score：归一化后的退化风险分数
- health_index：单调退化健康度指标，范围 [0, 1]，其中 0 最健康、1 接近失效
"""


def read_csv_with_fallback(csv_path: Path) -> pd.DataFrame:
    """针对工业数据常见混合编码，按多种编码依次尝试读取 CSV。"""
    encodings = ["utf-8-sig", "utf-8", "gb18030", "gbk", "latin1"]
    last_error = None
    for enc in encodings:
        try:
            return pd.read_csv(csv_path, encoding=enc)
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"Failed to read CSV with fallback encodings: {last_error}")


def robust_mad(values: np.ndarray) -> float:
    """基于 MAD 返回鲁棒尺度估计（在正态分布下近似标准差）。"""
    median = np.median(values)
    mad = np.median(np.abs(values - median))
    return float(1.4826 * mad + 1e-8)


def compute_health_index(df: pd.DataFrame, baseline_ratio: float = 0.2) -> tuple[pd.DataFrame, list[str], np.ndarray]:
    """基于数值指标计算故障风险与健康度（0=健康，1=退化严重）。"""
    df_num = df.select_dtypes(include=[np.number]).copy()
    if df_num.shape[1] < 2:
        raise ValueError("Need at least 2 numeric columns (time + features or multiple features).")

    n_rows = len(df_num)
    # 用早期样本构建稳定基线窗口，同时避免窗口过小或过大。
    base_n = max(30, int(n_rows * baseline_ratio))
    base_n = min(base_n, max(5, n_rows // 2))

    # 优先使用全部数值列；若第 1 列呈单调趋势则视为时间列并排除。
    feature_cols = list(df_num.columns)
    first_col = feature_cols[0]
    first_values = df_num[first_col].to_numpy()
    if np.all(np.diff(first_values) >= 0) or np.all(np.diff(first_values) <= 0):
        feature_cols = feature_cols[1:]
    if not feature_cols:
        feature_cols = list(df_num.columns)

    X = df_num[feature_cols].replace([np.inf, -np.inf], np.nan)
    # 先插值，再首尾填充，尽量避免因缺失值丢弃样本。
    X = X.interpolate(limit_direction="both").bfill().ffill()
    Xv = X.to_numpy(dtype=float)

    baseline = Xv[:base_n, :]
    end_window = Xv[-base_n:, :]

    med = np.median(baseline, axis=0)
    # 每个特征采用鲁棒尺度，降低振动类信号中异常点的影响。
    scale = np.array([robust_mad(baseline[:, i]) for i in range(baseline.shape[1])])

    # 通过比较基线窗口与末端窗口均值，估计各指标退化方向。
    drift = np.mean(end_window, axis=0) - np.mean(baseline, axis=0)
    direction = np.where(np.abs(drift) < 1e-10, 1.0, np.sign(drift))

    z = (Xv - med) / scale
    # 仅保留沿退化方向的偏移；反向变化视为非退化贡献。
    degradation = np.clip(direction * z, 0.0, None)

    # 按漂移幅度分配权重，使更敏感的指标贡献更大。
    w = np.abs(drift)
    if np.all(w < 1e-12):
        w = np.ones_like(w)
    w = w / (np.sum(w) + 1e-12)

    fused = degradation @ w
    # 用高分位值归一化，降低极端尖峰对结果的敏感性。
    q95 = float(np.quantile(fused, 0.95) + 1e-8)
    score = np.clip(fused / q95, 0.0, 3.0)

    # 健康度语义：0 最健康，1 最接近失效。
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
    """保存双轴对比图：左轴原始指标，右轴健康度。"""
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(11, 5.2), dpi=120)

    for idx, col in enumerate(feature_cols, start=1):
        # 图例标签使用 ASCII，避免部分环境缺少中文字形导致告警。
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
    """命令行入口：批量健康度评估，并可选导出可视化图像。"""
    # 解析运行参数：输入数据、基线比例、输出路径和绘图选项。
    parser = argparse.ArgumentParser(description="Bearing fault health assessment (0-1)")
    parser.add_argument("--input", required=True, help="Input CSV path")
    parser.add_argument("--output", default="data/health_assessment_result.csv", help="Output CSV path")
    parser.add_argument("--baseline-ratio", type=float, default=0.2, help="Baseline ratio in (0, 0.5]")
    parser.add_argument("--plot", action="store_true", help="Export health index curve PNG")
    parser.add_argument("--plot-file", default="data/health_index_curve.png", help="PNG path for health curve")
    args = parser.parse_args()

    # 基线比例安全约束，避免基线过于不稳定或过度平滑。
    if not (0.01 <= args.baseline_ratio <= 0.5):
        raise ValueError("--baseline-ratio must be between 0.01 and 0.5")

    csv_path = Path(args.input)
    if not csv_path.exists():
        raise FileNotFoundError(f"Input CSV not found: {csv_path}")

    # 执行核心流程：读取数据 -> 计算健康度 -> 落盘结果。
    df = read_csv_with_fallback(csv_path)
    result, feature_cols, drift = compute_health_index(df, baseline_ratio=args.baseline_ratio)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output_path, index=False, encoding="utf-8-sig")

    if args.plot:
        # x 轴优先取首个数值列（通常是时间），否则回退到样本序号。
        num_cols = result.select_dtypes(include=[np.number]).columns.tolist()
        x_col = num_cols[0] if num_cols else None
        x_vals = result[x_col].to_numpy() if x_col else np.arange(len(result))
        x_label = x_col if (x_col and str(x_col).isascii()) else "Time"

        plot_base = Path(args.plot_file)
        stem = plot_base.stem
        suffix = plot_base.suffix if plot_base.suffix else ".png"

        full_plot_path = plot_base.with_name(f"{stem}_all{suffix}")
        # 生成全量指标对比图，保留完整信息。
        save_comparison_plot(
            result=result,
            x_vals=x_vals,
            x_label=x_label if x_col else "Sample",
            feature_cols=feature_cols,
            title="All Raw Indicators vs Health Index",
            plot_path=full_plot_path,
        )

        # 生成漂移最明显 Top3 指标对比图，便于直观观察。
        top_n = min(3, len(feature_cols))
        top_idx = np.argsort(np.abs(drift))[-top_n:][::-1]
        top_cols = [feature_cols[int(i)] for i in top_idx]
        top_plot_path = plot_base.with_name(f"{stem}_top3{suffix}")
        # 使用 Top3 指标绘图，提升诊断可读性。
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

    # 输出简明运行摘要，便于批处理监控和日志采集。
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
