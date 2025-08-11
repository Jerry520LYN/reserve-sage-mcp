import pandas as pd
import numpy as np
import numpy_financial as npf 
from typing import Any, Dict, Union
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("economy")

def _calculate_peak_valley_arbitrage(params: Dict[str, Any]) -> Dict[str, float]:
    """计算峰谷价差套利年收益"""
    tech = params['technical_specs']
    market = params['market_and_policy']
    finance = params['financial_assumptions']

    # 每日循环的有效能量 = 额定容量 * 放电深度
    daily_energy_mwh = tech['capacity_mwh'] * tech['depth_of_discharge_dod']
    
    # 考虑往返效率的净收益
    # 收益 = 放电电价 * 电量, 成本 = 充电电价 * 电量, 充电电量 = 放电电量 / 效率
    # 净价差收益 = (P_peak - P_valley/efficiency) * Energy, 这里简化为使用净价差
    # 注意：更精确的模型会将充电成本基于效率折算，这里为简化直接用价差乘以放电量
    daily_revenue_usd = market['peak_valley_price_diff_usd_per_kwh'] * daily_energy_mwh * 1000 # MWh -> kWh
    
    annual_revenue_usd = daily_revenue_usd * 365 * finance['charge_cycles_per_day']
    
    # 计算电池的单位循环损耗成本
    cost = params['cost_structure']
    degradation_cost_per_cycle = cost['battery_replacement_cost_usd'] / tech['cycle_life']
    annual_degradation_cost = degradation_cost_per_cycle * 365 * finance['charge_cycles_per_day']

    net_annual_profit = annual_revenue_usd - annual_degradation_cost
    
    return {
        "annual_gross_revenue_usd": round(annual_revenue_usd, 2),
        "annual_battery_degradation_cost_usd": round(annual_degradation_cost, 2),
        "annual_net_profit_usd": round(net_annual_profit, 2)
    }

def _calculate_capacity_tariff_revenue(params: Dict[str, Any]) -> float:
    """计算容量电价年收益 (固定收益)"""
    tech = params['technical_specs']
    market = params['market_and_policy']
    annual_revenue = market['capacity_price_usd_per_mw_year'] * tech['max_power_mw']
    return round(annual_revenue, 2)

def _calculate_ancillary_services_revenue(params: Dict[str, Any]) -> float:
    """计算辅助服务年收益"""
    tech = params['technical_specs']
    market = params['market_and_policy']
    annual_revenue = market['ancillary_service_revenue_usd_per_mw_year'] * tech['max_power_mw']
    return round(annual_revenue, 2)

def _calculate_subsidy_revenue(params: Dict[str, Any]) -> float:
    """计算政府度电补贴年收益"""
    tech = params['technical_specs']
    market = params['market_and_policy']
    finance = params['financial_assumptions']
    
    daily_energy_mwh = tech['capacity_mwh'] * tech['depth_of_discharge_dod']
    annual_discharged_kwh = daily_energy_mwh * 1000 * 365 * finance['charge_cycles_per_day']
    annual_subsidy = annual_discharged_kwh * market['subsidy_per_kwh_discharged_usd']
    return round(annual_subsidy, 2)

def _calculate_annual_costs(params: Dict[str, Any]) -> float:
    """计算年度运营总成本 (不含电池折旧，已在套利模块计入)"""
    cost = params['cost_structure']
    annual_opex = cost['total_investment_usd'] * cost['annual_opex_rate_of_investment']
    return round(annual_opex, 2)

def _calculate_financial_metrics(params: Dict[str, Any], annual_net_cashflow: float) -> Dict[str, Any]:
    """计算核心财务指标：NPV, IRR, PBP, LCOE"""
    cost = params['cost_structure']
    tech = params['technical_specs']
    finance = params['financial_assumptions']
    
    initial_investment = cost['total_investment_usd']
    lifespan = tech['lifespan_years']
    discount_rate = finance['discount_rate']

    # 1. 静态投资回收期 (Simple Payback Period)
    pbp = initial_investment / annual_net_cashflow if annual_net_cashflow > 0 else "无法回收"
    pbp_str = f"{pbp:.2f} 年" if isinstance(pbp, float) else pbp

    # 2. 净现值 (Net Present Value - NPV) & 内部收益率 (Internal Rate of Return - IRR)
    cash_flows = [-initial_investment] + [annual_net_cashflow] * lifespan
    # 注：为简化，未考虑电池在中期更换的大额现金流出，实际模型应加入
    npv = npf.npv(discount_rate, cash_flows)
    irr = npf.irr(cash_flows)
    
    # 3. 度电成本 (Levelized Cost of Storage - LCOE)
    total_lifecycle_energy_discharged_kwh = tech['capacity_mwh'] * tech['depth_of_discharge_dod'] * 1000 * tech['cycle_life']
    
    # 全生命周期成本 = 初始投资 + (年运维成本的折现值总和) + (电池更换成本的折现值)
    # 此处简化计算：总成本 = 初始投资 + 总运维成本 + 总更换成本（不折现）
    total_opex = _calculate_annual_costs(params) * lifespan
    total_lifecycle_cost = initial_investment + total_opex + cost['battery_replacement_cost_usd']
    lcoe = total_lifecycle_cost / total_lifecycle_energy_discharged_kwh

    return {
        "payback_period_years": pbp_str,
        "net_present_value_usd": f"{npv:,.2f}",
        "internal_rate_of_return_percent": f"{irr:.2%}",
        "levelized_cost_of_storage_usd_per_kwh": round(lcoe, 4)
    }


# --- 主MCP工具函数 ---
@mcp.tool()
async def analyze_storage_station_economics(project_parameters: Dict[str, Any]) -> Dict[str, Any]:
    """
    一个综合性的储能电站经济效益分析工具。
    它接收一个包含项目所有参数的字典，执行多种盈利模式和成本分析，
    并返回一个包含关键经济指标 (NPV, IRR, PBP, LCOE) 的综合评估报告。

    Args:
        project_parameters: 一个包含项目详细信息的字典，
                           结构需符合 'project_info', 'cost_structure', 
                           'technical_specs', 'market_and_policy', 'financial_assumptions' 的规范。

    Returns:
        一个包含详细经济分析结果的字典。
    """
    try:
        # --- 1. 分项计算年收入 ---
        revenue = {}
        revenue['peak_valley_arbitrage'] = _calculate_peak_valley_arbitrage(project_parameters)
        revenue['capacity_tariff_usd'] = _calculate_capacity_tariff_revenue(project_parameters)
        revenue['ancillary_services_usd'] = _calculate_ancillary_services_revenue(project_parameters)
        revenue['subsidy_usd'] = _calculate_subsidy_revenue(project_parameters)
        
        total_annual_gross_revenue = sum([
            revenue['peak_valley_arbitrage']['annual_gross_revenue_usd'],
            revenue['capacity_tariff_usd'],
            revenue['ancillary_services_usd'],
            revenue['subsidy_usd']
        ])
        
        # --- 2. 分项计算年成本 ---
        costs = {}
        costs['annual_opex_usd'] = _calculate_annual_costs(project_parameters)
        # 电池损耗成本已在套利模块中计算
        costs['annual_battery_degradation_cost_usd'] = revenue['peak_valley_arbitrage']['annual_battery_degradation_cost_usd']
        
        total_annual_cost = costs['annual_opex_usd'] + costs['annual_battery_degradation_cost_usd']

        # --- 3. 计算年度净现金流 ---
        annual_net_cashflow = total_annual_gross_revenue - total_annual_cost

        # --- 4. 计算最终的财务评估指标 ---
        financial_summary = _calculate_financial_metrics(project_parameters, annual_net_cashflow)

        # --- 5. 组装最终的返回结果 ---
        analysis_report = {
            "project": project_parameters.get("project_info", {}),
            "assessment_summary": {
                "verdict": "项目在当前参数下具备投资可行性。" if financial_summary.get('net_present_value_usd', '0').startswith('-') is False and financial_summary.get('payback_period_years') != "无法回收" else "项目在当前参数下投资风险较高，难以回本。",
                **financial_summary
            },
            "detailed_analysis": {
                "annual_revenue_breakdown": {
                    "peak_valley_arbitrage_net_profit_usd": revenue['peak_valley_arbitrage']['annual_net_profit_usd'],
                    "capacity_tariff_usd": revenue['capacity_tariff_usd'],
                    "ancillary_services_usd": revenue['ancillary_services_usd'],
                    "subsidy_usd": revenue['subsidy_usd'],
                    "total_annual_gross_revenue_usd": round(total_annual_gross_revenue, 2)
                },
                "annual_cost_breakdown": {
                    "opex_usd": costs['annual_opex_usd'],
                    "battery_degradation_usd": costs['annual_battery_degradation_cost_usd'],
                    "total_annual_cost_usd": round(total_annual_cost, 2)
                },
                "annual_net_cash_flow_usd": round(annual_net_cashflow, 2)
            }
        }
        return analysis_report

    except KeyError as e:
        return {"error": f"输入参数缺失: 缺少关键字段 '{e}'。请检查 'project_parameters' 字典的完整性。"}
    except Exception as e:
        return {"error": f"计算过程中发生未知错误: {e}"}

if __name__ == "__main__":
    mcp.run(transport='stdio')