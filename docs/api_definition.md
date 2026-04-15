# 健康度评估接口定义 API 文档

## 1. 概览
当前实现为命令行接口（CLI），入口脚本：
- `health_assessment.py`

主要能力：
- 读取轴承 CI 指标 CSV
- 计算 `fault_risk_score` 与 `health_index`
- 可选生成对比图（全量与 Top3）

## 2. 命令行接口

### 2.1 命令格式
```bash
d:/code_python/vibecoding/.venv/Scripts/python.exe health_assessment.py \
  --input <输入CSV路径> \
  [--output <输出CSV路径>] \
  [--baseline-ratio <0.01~0.5>] \
  [--plot] \
  [--plot-file <图像基路径>]
```

### 2.2 参数定义

| 参数 | 必填 | 类型 | 默认值 | 说明 |
|---|---|---|---|---|
| `--input` | 是 | string(path) | 无 | 输入 CSV 文件路径 |
| `--output` | 否 | string(path) | `data/health_assessment_result.csv` | 输出结果 CSV 路径 |
| `--baseline-ratio` | 否 | float | `0.2` | 基线窗口比例，范围 `[0.01, 0.5]` |
| `--plot` | 否 | flag | `False` | 是否生成对比图 |
| `--plot-file` | 否 | string(path) | `data/health_index_curve.png` | 图像输出基路径，实际会生成 `*_all.png` 与 `*_top3.png` |

## 3. 返回与标准输出

### 3.1 退出码
- `0`：执行成功
- 非 `0`：执行失败

### 3.2 标准输出字段
成功时打印：
- `rows=<样本数>`
- `start_health=<首样本健康度>`
- `end_health=<末样本健康度>`
- `max_health=<全局最大健康度>`
- `output=<输出CSV绝对路径>`
- 启用 `--plot` 时额外打印：
  - `plot_all=<全量图绝对路径>`
  - `plot_top3=<Top3图绝对路径>`

## 4. 输出文件结构

### 4.1 结果 CSV
在输入 CSV 原有字段后新增：
- `fault_risk_score`（float）
- `health_index`（float，范围 `[0,1]`，0 表示健康，1 表示接近损坏）

### 4.2 图像文件
当 `--plot` 启用时：
- `<plot-file基名>_all.png`
- `<plot-file基名>_top3.png`

示例：`--plot-file data/health_index_curve.png` 将生成
- `data/health_index_curve_all.png`
- `data/health_index_curve_top3.png`

## 5. 异常定义

| 异常类型 | 触发条件 |
|---|---|
| `FileNotFoundError` | `--input` 文件不存在 |
| `ValueError` | `--baseline-ratio` 不在 `[0.01, 0.5]` |
| `ValueError` | 数值列不足（少于 2 列） |
| `RuntimeError` | CSV 编码回退读取全部失败 |

## 6. 调用示例

### 6.1 仅生成结果 CSV
```bash
d:/code_python/vibecoding/.venv/Scripts/python.exe health_assessment.py \
  --input "D:\\path\\to\\input.csv"
```

### 6.2 生成 CSV + 对比图
```bash
d:/code_python/vibecoding/.venv/Scripts/python.exe health_assessment.py \
  --input "D:\\path\\to\\input.csv" \
  --output "data/health_assessment_result_custom.csv" \
  --plot \
  --plot-file "data/health_curve_custom.png"
```

### 6.3 辛辛那提数据集实测示例
```bash
d:/code_python/vibecoding/.venv/Scripts/python.exe health_assessment.py \
  --input "D:\\code_python\\Project\\data\\25117DT故障数据CI指标\\辛辛那提数据集\\1st_test-allBearingCI-channel6.csv" \
  --output "data/health_assessment_result_1st_test_channel6.csv" \
  --plot \
  --plot-file "data/health_index_curve_1st_test_channel6.png"
```

对应实测输出：

- `rows=2156`
- `start_health=0.109271`
- `end_health=0.995483`
- `max_health=0.995483`
- `output=D:\code_python\vibecoding\data\health_assessment_result_1st_test_channel6.csv`
- `plot_all=D:\code_python\vibecoding\data\health_index_curve_1st_test_channel6_all.png`
- `plot_top3=D:\code_python\vibecoding\data\health_index_curve_1st_test_channel6_top3.png`

## 7. Python 函数级接口（内部）

| 函数 | 签名 | 说明 |
|---|---|---|
| `read_csv_with_fallback` | `(csv_path: Path) -> pd.DataFrame` | 多编码回退读取 CSV |
| `robust_mad` | `(values: np.ndarray) -> float` | 计算鲁棒尺度 |
| `compute_health_index` | `(df: pd.DataFrame, baseline_ratio: float=0.2) -> tuple[pd.DataFrame, list[str], np.ndarray]` | 计算健康度并返回结果、特征名、漂移量 |
| `save_comparison_plot` | `(result, x_vals, x_label, feature_cols, title, plot_path) -> None` | 生成双轴对比图 |
| `main` | `() -> None` | CLI 入口 |
