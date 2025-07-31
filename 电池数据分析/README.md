# 储能电池性能分析项目

## 项目概述

本项目提供了储能电池性能分析的完整解决方案，包括数据文件、分析脚本和MCP服务。项目重点围绕两个核心文件展开：`analyse.ipynb`（分析脚本）和`data.csv`（电池运行数据），同时提供了`battery.py`作为MCP服务封装。

## 核心文件说明

### 1. 数据文件: `data.csv`

位于 `/电池数据分析/储能电池处理方法/电池数据分析/data.csv`，是项目的核心数据来源。该CSV文件包含了储能电池系统的详细运行数据，记录了从2025-07-20到2025-07-28的电池运行状态，每小时一条记录，共183条数据。

**数据字段详细解释**:
- `时间戳`: 数据记录时间，格式为`YYYY-MM-DD HH:MM:SS`
- `外部环境温度(°C)`: 电池系统外部环境温度，单位为摄氏度
- `系统内部温度(°C)`: 电池系统内部温度，单位为摄氏度
- `充电功率(kW)`: 电池充电时的功率，单位为千瓦
- `放电功率(kW)`: 电池放电时的功率，单位为千瓦
- `输入总能量(kWh)`: 电池累计输入能量，单位为千瓦时
- `输出总能量(kWh)`: 电池累计输出能量，单位为千瓦时
- `当前SOC(%)`: 电池荷电状态，即电池剩余容量占总容量的百分比
- `瞬时电压(V)`: 电池系统的瞬时电压，单位为伏特
- `瞬时电流(A)`: 电池系统的瞬时电流，单位为安培
- `瞬时无功功率(kVar)`: 系统的瞬时无功功率，单位为千乏
- `控制指令功率(kW)`: 系统接收到的控制指令功率，单位为千瓦
- `实际输出功率(kW)`: 系统实际输出的功率，单位为千瓦
- `电网频率(Hz)`: 电网的频率，单位为赫兹
- `电网电压(V)`: 电网的电压，单位为伏特
- `系统总质量(kg)`: 电池系统的总质量，单位为千克
- `系统总体积(m³)`: 电池系统的总体积，单位为立方米

### 2. 分析脚本: `analyse.ipynb`

位于 `/电池数据分析/储能电池处理方法/电池数据分析/analyse.ipynb`，是一个Jupyter Notebook文件，提供了完整的电池性能分析流程。

**主要分析函数说明**:
1. `analyze_storage_data(csv_file_path)`: 加载CSV数据并计算基础统计量
   - 功能: 读取CSV文件，转换时间戳格式，计算各数值列的基础统计量
   - 返回: 数据框和统计量字典

2. `calculate_energy_capacity(df)`: 计算能量容量
   - 功能: 基于输出总能量计算电池系统的能量容量
   - 返回: 能量容量值(kWh)

3. `calculate_power_rating()`: 获取功率额定值
   - 功能: 返回系统设计的最大功率
   - 返回: 功率值(kW)

4. `calculate_round_trip_efficiency(df)`: 计算往返效率
   - 功能: 计算电池系统的能量转换效率
   - 返回: 效率值(%)

5. `calculate_energy_density(energy_capacity, total_mass, total_volume)`: 计算能量密度
   - 功能: 计算按质量和体积的能量密度
   - 返回: 质量能量密度(kWh/kg)和体积能量密度(kWh/m³)

6. `calculate_power_density(max_power, total_mass, total_volume)`: 计算功率密度
   - 功能: 计算按质量和体积的功率密度
   - 返回: 质量功率密度(kW/kg)和体积功率密度(kW/m³)

7. `calculate_power_throughput(cycle_energy_assumption_kwh, assumed_cycle_life)`: 计算功率吞吐量
   - 功能: 估算系统的总功率吞吐量
   - 返回: 功率吞吐量值(MWh)

8. `calculate_response_time(df)`: 计算响应时间
   - 功能: 计算系统对控制指令的响应时间
   - 返回: 平均响应时间(秒)或无法计算的说明

9. `calculate_cycle_life(final_capacity_ratio, degradation_rate_per_cycle)`: 计算循环寿命
   - 功能: 估算电池的循环寿命
   - 返回: 循环次数

10. `calculate_calendar_life(final_capacity_ratio, annual_degradation_rate)`: 计算日历寿命
    - 功能: 估算电池的日历寿命
    - 返回: 年数

11. `calculate_ramp_rate(df)`: 计算爬坡率
    - 功能: 计算系统功率变化的最大速率
    - 返回: 最大爬坡率(kW/s)

12. `calculate_soc_range(df)`: 计算SOC范围
    - 功能: 计算电池系统的SOC工作范围
    - 返回: SOC范围(%)

13. `calculate_self_discharge_rate(df)`: 计算自放电率
    - 功能: 估算电池的自放电率
    - 返回: 自放电率(%/天)或无法计算的说明

14. `analyze_temperature_characteristics(df)`: 分析温度特性
    - 功能: 分析系统内部温度变化特性
    - 返回: 包含平均、最低和最高内部温度的字典

15. `calculate_transient_overload_capability(df, rated_power)`: 计算瞬态过载能力
    - 功能: 评估系统的过载能力
    - 返回: 过载因子和说明

16. `calculate_c_rate(df, rated_capacity_kwh)`: 计算C倍率
    - 功能: 计算充放电C倍率
    - 返回: 充电C倍率和放电C倍率

17. `calculate_esr(df)`: 计算等效串联电阻
    - 功能: 粗略估算电池的等效串联电阻
    - 返回: 电阻值(Ω)或无法计算的说明

18. `analyze_thermal_degradation(df)`: 分析热衰减
    - 功能: 评估温度对电池衰减的影响
    - 返回: 热衰减评估说明

19. `calculate_insulation_resistance(df)`: 计算绝缘电阻
    - 功能: 提供绝缘电阻的估计值
    - 返回: 绝缘电阻说明

20. `analyze_transient_response_characteristics(df)`: 分析瞬态响应特性
    - 功能: 分析系统对控制指令的瞬态响应特性
    - 返回: 瞬态响应评估说明

21. `calculate_harmonic_content(df)`: 计算谐波含量
    - 功能: 说明谐波含量的计算需求
    - 返回: 谐波含量说明

22. `calculate_frequency_support_capability(df)`: 计算频率支持能力
    - 功能: 评估系统对电网频率的支持能力
    - 返回: 频率支持能力说明

23. `calculate_voltage_support_capability(df)`: 计算电压支持能力
    - 功能: 说明电压支持能力的计算需求
    - 返回: 电压支持能力说明

24. `analyze_ancillary_service_potential()`: 分析辅助服务潜力
    - 功能: 评估系统提供电网辅助服务的潜力
    - 返回: 辅助服务潜力说明

### 3. MCP服务: `battery.py`

位于 `/电池数据分析/battery/battery.py`，基于MCP框架实现了电池性能分析的API服务。主要功能是将`analyse.ipynb`中的分析逻辑封装为可调用的API接口，提供了`analyze_storage_battery_performance`异步函数，接收CSV文件路径，返回分析结果。

## 技术栈

- Python 3.8.20+
- pandas: 数据处理和分析
- numpy: 数值计算
- Jupyter Notebook: 交互式数据分析
- mcp[cli] 1.12.2+: 服务框架
- httpx 0.28.1+: HTTP客户端

## 使用方法

### 1. 使用Jupyter Notebook分析

1. 打开`analyse.ipynb`文件
2. 确保`data.csv`文件路径正确
3. 逐步运行Notebook中的代码块
4. 查看分析结果

### 2. 使用MCP服务

1. 安装依赖: `pip install mcp[cli] pandas numpy httpx`
2. 运行服务: `python battery.py`
3. 在相关客户端中配置服务地址

## 系统配置参数

在`battery.py`和`analyse.ipynb`中定义了以下可配置参数：

- `SYSTEM_DESIGN_CAPACITY_KWH = 2000`: 系统设计容量(kWh)
- `SYSTEM_MAX_POWER_KW = 500`: 系统最大功率(kW)
- `SYSTEM_TOTAL_MASS_KG = 10000`: 系统总质量(kg)
- `SYSTEM_TOTAL_VOLUME_M3 = 20`: 系统总体积(m³)

## 分析结果示例

分析结果包含以下关键指标（示例）：

- **能量容量**: 5558.00 kWh
- **往返效率**: 96.44%
- **能量密度**: 0.56 kWh/kg (按质量), 277.90 kWh/m³ (按体积)
- **功率密度**: 0.05 kW/kg (按质量), 25.00 kW/m³ (按体积)
- **平均响应时间**: 3857.14 秒
- **最大爬坡率**: 0.14 kW/s
- **SOC工作范围**: 65.00%
- **假设循环寿命**: 4000 次
- **假设日历寿命**: 10.0 年
- **充放电C倍率**: 充电 0.02 C, 放电 0.02 C
- **等效串联电阻**: 444.92 Ω (粗略估算)

## 注意事项

1. 确保`data.csv`文件格式正确且完整
2. 首次使用前请检查并配置系统参数以匹配实际电池系统
3. 对于大型数据集，分析可能需要一定时间
4. 分析结果仅供参考，实际电池性能可能受多种因素影响
5. 本项目使用的Python版本为3.8.20，建议使用相同或兼容版本以避免兼容性问题