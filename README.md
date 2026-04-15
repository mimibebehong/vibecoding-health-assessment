# vibecoding-health-assessment

轴承部件故障诊断健康度评估工具。

## 项目说明

本项目基于多维 CI 指标计算部件健康度，输出：

- `fault_risk_score`：退化风险分数
- `health_index`：健康度指标，范围 `[0,1]`

其中：

- `0` 表示最健康
- `1` 表示最接近完全损坏

脚本支持：

- 读取多编码 CSV 数据
- 生成健康度结果 CSV
- 生成全量指标对比图与 Top3 指标对比图

## 快速使用

```bash
d:/code_python/vibecoding/.venv/Scripts/python.exe health_assessment.py \
	--input "D:\\code_python\\Project\\data\\25117DT故障数据CI指标\\辛辛那提数据集\\1st_test-allBearingCI-channel6.csv" \
	--output "data/health_assessment_result_1st_test_channel6.csv" \
	--plot \
	--plot-file "data/health_index_curve_1st_test_channel6.png"
```

## 标准测试示例

测试数据：

- `D:\code_python\Project\data\25117DT故障数据CI指标\辛辛那提数据集\1st_test-allBearingCI-channel6.csv`

实测输出：

- `rows = 2156`
- `start_health = 0.109271`
- `end_health = 0.995483`
- `max_health = 0.995483`

生成文件：

- `data/health_assessment_result_1st_test_channel6.csv`
- `data/health_index_curve_1st_test_channel6_all.png`
- `data/health_index_curve_1st_test_channel6_top3.png`

## 文档

- `docs/algorithm_implementation_logic.md`：算法实现逻辑说明
- `docs/api_definition.md`：接口定义与调用示例
