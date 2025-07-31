import pandas as pd
import numpy as np
from io import StringIO
from typing import Any, Dict, Union
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("weather")

SYSTEM_DESIGN_CAPACITY_KWH = 2000
SYSTEM_MAX_POWER_KW = 500
SYSTEM_TOTAL_MASS_KG = 10000
SYSTEM_TOTAL_VOLUME_M3 = 20

def _convert_to_python_type(value):
    """内部辅助函数：将numpy/pandas类型转换为原生Python类型以便JSON序列化"""
    if pd.api.types.is_integer(value):
        return int(value)
    elif pd.api.types.is_float(value):
        return float(value)
    return value

def _calculate_energy_capacity(df: pd.DataFrame) -> Union[float, str]:
    """计算实际能量容量"""
    if '输出总能量(kWh)' in df.columns and not df['输出总能量(kWh)'].empty:
        return round(df['输出总能量(kWh)'].max() - df['输出总能量(kWh)'].min(), 2)
    return "无法计算 (缺少 '输出总能量(kWh)' 列)"

def _calculate_round_trip_efficiency(df: pd.DataFrame) -> Union[float, str]:
    """计算往返效率"""
    if '输入总能量(kWh)' in df.columns and '输出总能量(kWh)' in df.columns:
        total_input = df['输入总能量(kWh)'].iloc[-1] - df['输入总能量(kWh)'].iloc[0]
        total_output = df['输出总能量(kWh)'].iloc[-1] - df['输出总能量(kWh)'].iloc[0]
        if total_input > 0:
            return round((total_output / total_input) * 100, 2)
        return 0.0
    return "无法计算 (缺少 '输入总能量(kWh)' 或 '输出总能量(kWh)' 列)"

def _calculate_energy_density(energy_capacity: Union[float, str]) -> Dict[str, Union[float, str]]:
    """计算能量密度"""
    if isinstance(energy_capacity, str) or pd.isna(energy_capacity) or SYSTEM_TOTAL_MASS_KG == 0 or SYSTEM_TOTAL_VOLUME_M3 == 0:
        return {
            "mass_density_kwh_per_kg": "无法计算",
            "volume_density_kwh_per_m3": "无法计算"
        }
    return {
        "mass_density_kwh_per_kg": round(energy_capacity / SYSTEM_TOTAL_MASS_KG, 4),
        "volume_density_kwh_per_m3": round(energy_capacity / SYSTEM_TOTAL_VOLUME_M3, 4)
    }

def _calculate_power_density() -> Dict[str, Union[float, str]]:
    """计算功率密度"""
    max_power = SYSTEM_MAX_POWER_KW
    if max_power == 0 or SYSTEM_TOTAL_MASS_KG == 0 or SYSTEM_TOTAL_VOLUME_M3 == 0:
        return {
            "mass_density_kw_per_kg": "无法计算",
            "volume_density_kw_per_m3": "无法计算"
        }
    return {
        "mass_density_kw_per_kg": round(max_power / SYSTEM_TOTAL_MASS_KG, 4),
        "volume_density_kw_per_m3": round(max_power / SYSTEM_TOTAL_VOLUME_M3, 4)
    }

def _calculate_average_response_time(df: pd.DataFrame) -> Union[float, str]:
    """计算平均响应时间"""
    if '控制指令功率(kW)' not in df.columns or '实际输出功率(kW)' not in df.columns:
        return "无法计算 (缺少指令或实际功率列)"
    
    response_times = []
    # 寻找指令功率发生显著变化的点
    df['指令变化'] = (df['控制指令功率(kW)'].diff().abs() > 1) # 变化阈值设为1kW
    command_change_indices = df[df['指令变化']].index

    for i in command_change_indices:
        if i == 0: continue
        command_time = df.loc[i, '时间戳']
        command_power = df.loc[i, '控制指令功率(kW)']
        # 在指令变化后的一个短时间窗口内（例如5个数据点）寻找响应
        for j in range(i + 1, min(i + 6, len(df))):
            actual_power = df.loc[j, '实际输出功率(kW)']
            # 检查实际功率是否达到指令功率的90%
            if (command_power > 0 and actual_power >= command_power * 0.9) or \
               (command_power < 0 and actual_power <= command_power * 0.9): # 处理负功率（充电）
                response_delta = (df.loc[j, '时间戳'] - command_time).total_seconds()
                response_times.append(response_delta)
                break # 找到响应后即停止搜索
    
    return round(np.mean(response_times), 3) if response_times else "无法计算 (无明显指令响应)"

def _calculate_ramp_rate(df: pd.DataFrame) -> Union[float, str]:
    """计算最大爬坡率"""
    if '实际输出功率(kW)' not in df.columns:
        return "无法计算 (缺少 '实际输出功率(kW)' 列)"
    
    df['功率变化'] = df['实际输出功率(kW)'].diff().abs()
    df['时间间隔'] = df['时间戳'].diff().dt.total_seconds()
    # 过滤掉时间间隔为0或过大的异常点
    valid_intervals = df[(df['时间间隔'] > 0) & (df['时间间隔'] < 300)] # 假设数据点间隔不超过5分钟
    if valid_intervals.empty:
        return 0.0
        
    ramp_rates = valid_intervals['功率变化'] / valid_intervals['时间间隔']
    return round(ramp_rates.max(), 2) if not ramp_rates.empty else 0.0

def _calculate_c_rate(df: pd.DataFrame) -> Dict[str, Union[float, str]]:
    """计算平均充放电倍率C-rate"""
    if '充电功率(kW)' not in df.columns or '放电功率(kW)' not in df.columns:
        return {"charge_c_rate": "无法计算", "discharge_c_rate": "无法计算"}
    
    # 只在实际发生充/放电时计算平均功率
    avg_charge_power = df[df['充电功率(kW)'] > 0]['充电功率(kW)'].mean()
    avg_discharge_power = df[df['放电功率(kW)'] > 0]['放电功率(kW)'].mean()

    charge_c = avg_charge_power / SYSTEM_DESIGN_CAPACITY_KWH if SYSTEM_DESIGN_CAPACITY_KWH > 0 and not pd.isna(avg_charge_power) else 0
    discharge_c = avg_discharge_power / SYSTEM_DESIGN_CAPACITY_KWH if SYSTEM_DESIGN_CAPACITY_KWH > 0 and not pd.isna(avg_discharge_power) else 0

    return {
        "charge_c_rate": round(charge_c, 2),
        "discharge_c_rate": round(discharge_c, 2)
    }

@mcp.tool()
async def analyze_storage_battery_performance(file_path: str) -> Dict[str, Any]:
    """
    一个综合性的储能电池性能分析工具。
    它接收一个CSV文件的【路径】，执行一系列性能指标计算，并返回一个包含所有分析结果的JSON对象。

    Args:
        file_path: 指向要分析的CSV文件的本地路径 (例如: "C:/data/battery_log.csv" 或 "/home/user/data.csv")。

    Returns:
        一个包含所有分析指标的字典。如果文件未找到或数据加载失败，则返回一个包含错误信息的字典。
    """
    try:
        df = pd.read_csv(file_path)
        df['时间戳'] = pd.to_datetime(df['时间戳'])
    except FileNotFoundError:
        return {"error": f"文件未找到: '{file_path}'。请确保文件路径正确且程序有权限访问。"}
    except KeyError:
        return {"error": f"CSV文件缺少必需的 '时间戳' 列。"}
    except Exception as e:
        return {"error": f"从文件 '{file_path}' 加载或解析数据失败: {e}. 请检查文件格式是否为标准CSV。"}

    analysis_results = {}

    analysis_results["source_file"] = file_path    
    energy_capacity = _calculate_energy_capacity(df)
    analysis_results["energy_capacity_kwh"] = energy_capacity
    
    analysis_results["system_power_rating_kw"] = SYSTEM_MAX_POWER_KW
    analysis_results["round_trip_efficiency_percent"] = _calculate_round_trip_efficiency(df)
 
    analysis_results["energy_density"] = _calculate_energy_density(energy_capacity)
    analysis_results["power_density"] = _calculate_power_density()
  
    analysis_results["average_response_time_s"] = _calculate_average_response_time(df)
    analysis_results["max_ramp_rate_kw_per_s"] = _calculate_ramp_rate(df)
    analysis_results["c_rate"] = _calculate_c_rate(df)
    
    if '当前SOC(%)' in df.columns:
        analysis_results["soc_operating_range_percent"] = round(df['当前SOC(%)'].max() - df['当前SOC(%)'].min(), 2)
    else:
        analysis_results["soc_operating_range_percent"] = "无法计算 (缺少 '当前SOC(%)' 列)"

    assumed_cycle_life = int((1 - 0.8) / 0.00004) # 假设80%寿命终止，每圈衰减0.004%
    analysis_results["assumed_cycle_life"] = assumed_cycle_life
    analysis_results["assumed_calendar_life_years"] = round((1 - 0.8) / 0.025, 1) # 假设年衰减率2.5%
    analysis_results["lifetime_power_throughput_gwh"] = round(SYSTEM_DESIGN_CAPACITY_KWH * assumed_cycle_life / 1e6, 4)

    # --- 电气与热力学特性 ---
    if '系统内部温度(°C)' in df.columns:
        analysis_results["temperature_characteristics_celsius"] = {
            'average': round(df['系统内部温度(°C)'].mean(), 2),
            'min': round(df['系统内部温度(°C)'].min(), 2),
            'max': round(df['系统内部温度(°C)'].max(), 2)
        }
    else:
        analysis_results["temperature_characteristics_celsius"] = "无法分析 (缺少'系统内部温度(°C)'列)"

    # --- 辅助服务能力评估 (基于数据的简要判断) ---
    if '电网频率(Hz)' in df.columns and '充电功率(kW)' in df.columns and '放电功率(kW)' in df.columns:
        # 检查是否存在频率偏低时放电，或频率偏高时充电的情况
        responsive_instances = df[
            ((df['电网频率(Hz)'] < 49.95) & (df['放电功率(kW)'] > 10)) |
            ((df['电网频率(Hz)'] > 50.05) & (df['充电功率(kW)'] > 10))
        ]
        analysis_results["frequency_support_capability"] = "检测到潜在的频率响应行为" if not responsive_instances.empty else "未检测到明显频率响应"
    else:
        analysis_results["frequency_support_capability"] = "无法评估 (缺少频率或功率数据)"

    analysis_results["voltage_support_capability"] = "无法评估 (需要无功功率数据)"
    analysis_results["ancillary_service_potential"] = "取决于市场规则和系统的综合性能(功率、能量、响应时间等)"

    return analysis_results

if __name__ == "__main__":
    mcp.run(transport='stdio')

    