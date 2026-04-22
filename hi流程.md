graph TD
    A([输入: 采集到的振动信号]) --> B[a. 计算子部件特征指标 CI]
    
    subgraph 1. 特征提取与归一化
        B --> |轴: om1, om2...<br>齿轮: rms, modx...<br>轴承: fop, fip...| C[b. 子部件 CI 归一化]
        C --> |依据黄/红阈值进行两段线性映射<br>如黄阈值=0.6, 红阈值=1.0| D{c. 归一化子部件CI 融合算法选择}
    end

    subgraph 2. 子部件评分 HI_Sub(i) 融合
        D -->|1. 超灵敏因子融合| E1[取归一化后的最大子部件 CI]
        D -->|2. 基于权重的融合| E2[加权融合 CI <br> 案例库/数据驱动设定权重]
        D -->|3. 基于机器学习融合| E3[PCA / 高斯混合分布+KL散度 / AE重构残差]
        
        E1 --> F[生成子部件评分 HI_Sub]
        E2 --> |重新制定黄/红阈值| F
        E3 --> |重新制定黄/红阈值| F
    end

    subgraph 3. 部件与整机级评分融合
        F --> G[d. 部件评分融合算法]
        G --> |基于木桶短板理论<br>取最大的 HI_Sub| H[生成部件评分 HI_Comp]
        
        H --> I[e. 整机评分融合算法]
        I --> |基于木桶短板理论<br>取最大的 HI_Comp| J[生成整机评分 HI]
    end
    
    J --> K([输出: 预警状态判定])
    K -.->|HI < 0.6| L1((健康))
    K -.->|0.6 <= HI < 1| L2((预警))
    K -.->|HI >= 1| L3((告警))
    
    classDef default fill:#f9f9f9,stroke:#333,stroke-width:2px;
    classDef output fill:#e1f5fe,stroke:#03a9f4,stroke-width:2px;
    class K output;
