import copy
import pandas as pd
import numpy as np
import numpy_financial as npf 
from typing import Any, Dict, Union
from mcp.server.fastmcp import FastMCP
from typing_extensions import Tuple

mcp = FastMCP("economy")

def _calculate_demand_response_revenue(params: Dict[str, Any]) -> float:
    """(新增) 计算需求侧响应年收益 (削峰填谷)"""
    market = params.get('market_and_policy', {})
    dr_params = market.get('demand_response', {})
    if not dr_params.get('is_participant', False):
        return 0.0
    
    # 收益主要来自于为大工业用户削减高峰负荷，从而降低其需量电费
    monthly_savings = dr_params.get('demand_charge_usd_per_kw_month', 0) * dr_params.get('peak_load_reduction_kw', 0)
    return round(monthly_savings * 12, 2)

def _calculate_grid_deferral_value(params: Dict[str, Any]) -> float:
    """(新增) 计算延缓电网投资的年化价值"""
    market = params.get('market_and_policy', {})
    deferral_params = market.get('grid_deferral', {})
    if not deferral_params.get('is_applicable', False):
        return 0.0

    # 将一次性的延缓投资价值，通过资本回收系数年金化
    deferred_investment = deferral_params.get('deferred_investment_usd', 0)
    deferral_period = deferral_params.get('deferral_period_years', 1)
    discount_rate = params['financial_assumptions']['discount_rate']
    
    if discount_rate > 0:
        # 资本回收系数 (CRF)
        crf = (discount_rate * (1 + discount_rate)**deferral_period) / ((1 + discount_rate)**deferral_period - 1)
        annualized_value = deferred_investment * crf
    else:
        annualized_value = deferred_investment / deferral_period if deferral_period > 0 else 0
        
    return round(annualized_value, 2)

# --- V3 细化的成本计算模块 ---

def _calculate_detailed_annual_costs(params: Dict[str, Any]) -> Dict[str, float]:
    """(重构) 计算更详细的年度运营成本"""
    cost = params['cost_structure']
    
    # 基础运维成本
    base_opex = cost['total_investment_usd'] * cost['annual_opex_rate_of_investment']
    # 新增成本项
    land_lease_cost = cost.get('annual_land_lease_usd', 0)
    insurance_cost = cost.get('annual_insurance_rate_of_investment', 0) * cost['total_investment_usd']
    
    total_fixed_opex = base_opex + land_lease_cost + insurance_cost
    return {
        "annual_base_opex_usd": round(base_opex, 2),
        "annual_land_lease_usd": round(land_lease_cost, 2),
        "annual_insurance_usd": round(insurance_cost, 2),
        "total_annual_fixed_opex_usd": round(total_fixed_opex, 2)
    }

# === 资本结构与融资模型 (新增) ===

def _calculate_debt_service_schedule(params: Dict[str, Any], loan_amount: float) -> pd.DataFrame:
    """计算债务还本付息表"""
    finance = params['financial_assumptions']['financing']
    loan_term = finance['loan_term_years']
    interest_rate = finance['loan_interest_rate']
    repayment_type = finance.get('repayment_type', 'equal_installment')  # equal_installment or equal_principal
    
    years = range(1, loan_term + 1)
    schedule = []
    remaining_principal = loan_amount
    
    if repayment_type == 'equal_installment':
        # 等额本息还款
        installment = npf.pmt(
            rate=interest_rate,
            nper=loan_term,
            pv=-loan_amount
        )
        for year in years:
            interest_payment = remaining_principal * interest_rate
            principal_payment = installment - interest_payment
            remaining_principal -= principal_payment
            schedule.append({
                'year': year,
                'beginning_balance': remaining_principal + principal_payment,
                'principal_payment': principal_payment,
                'interest_payment': interest_payment,
                'total_payment': principal_payment + interest_payment,
                'ending_balance': remaining_principal
            })
    
    elif repayment_type == 'equal_principal':
        # 等额本金还款
        principal_payment = loan_amount / loan_term
        for year in years:
            interest_payment = remaining_principal * interest_rate
            total_payment = principal_payment + interest_payment
            remaining_principal -= principal_payment
            schedule.append({
                'year': year,
                'beginning_balance': remaining_principal + principal_payment,
                'principal_payment': principal_payment,
                'interest_payment': interest_payment,
                'total_payment': total_payment,
                'ending_balance': remaining_principal
            })
    
    return pd.DataFrame(schedule)

# === 宏观政策与税务细节 (新增) ===

def _calculate_depreciation(
    params: Dict[str, Any], 
    net_investment: float,
    year: int,
    accumulated_depreciation: float
) -> Tuple[float, float]:
    """计算不同折旧方法下的折旧额"""
    finance = params['financial_assumptions']
    depreciation_method = finance.get('depreciation_method', 'straight_line')
    lifespan = params['technical_specs']['lifespan_years']
    
    if depreciation_method == 'double_declining':
        # 双倍余额递减法
        rate = 2 / lifespan
        depreciation = min(
            net_investment * rate,
            net_investment - accumulated_depreciation
        )
    else:  # 默认直线折旧法
        depreciation = net_investment / lifespan
        
    return depreciation

def _apply_tax_credits(params: Dict[str, Any], initial_investment_net_vat: float) -> float:
    """应用投资税收抵免(ITC)"""
    cost = params['cost_structure']
    itc_rate = cost.get('investment_tax_credit_rate', 0)
    return initial_investment_net_vat * itc_rate

# --- V3 核心：动态现金流量表与财务指标计算 (重构以包含融资和税务细节) ---

def _generate_dynamic_yearly_cashflow_statement(params: Dict[str, Any]) -> pd.DataFrame:
    """
    (重构) 生成考虑了税收、效率衰减、融资结构和税务政策的动态年度现金流量表
    """
    tech = params['technical_specs']
    cost = params['cost_structure']
    finance = params['financial_assumptions']
    
    lifespan = tech['lifespan_years']
    years = range(1, lifespan + 1)
    
    # 初始投资 (考虑增值税进项税抵扣)
    vat_rate = finance.get('vat_rate', 0.13)
    initial_investment_net_vat = cost['total_investment_usd'] / (1 + vat_rate)
    
    # 应用投资税收抵免(ITC)
    itc_credit = _apply_tax_credits(params, initial_investment_net_vat)
    
    # 融资结构计算
    financing = finance.get('financing', {})
    debt_ratio = financing.get('debt_ratio', 0)
    loan_amount = initial_investment_net_vat * debt_ratio
    equity_amount = initial_investment_net_vat - loan_amount
    
    # 生成债务还本付息表
    if debt_ratio > 0:
        debt_schedule = _calculate_debt_service_schedule(params, loan_amount)
    else:
        debt_schedule = pd.DataFrame(columns=[
            'year', 'beginning_balance', 'principal_payment', 
            'interest_payment', 'total_payment', 'ending_balance'
        ])
    
    # 初始化年度数据列表
    df_data = {
        '年份': years,
        '峰谷套利毛收入': [], '容量电价收入': [], '辅助服务收入': [], '需求响应收入': [],
        '电网延缓价值': [], '补贴收入': [], '年度总收入': [],
        '固定运维成本': [], '电池衰减成本': [], '年度总运营成本': [],
        '折旧摊销': [], '息税前利润(EBIT)': [], '可抵扣亏损累计': [],
        '税前利润': [], '所得税': [], '税后净利润': [],
        '电池更换成本': [], 
        '项目自由现金流': [],
        '债务本金偿还': [], '债务利息支付': [], 
        '股权自由现金流': []
    }
    
    # 固定年收入与成本
    capacity_revenue = _calculate_capacity_tariff_revenue(params)
    ancillary_revenue = _calculate_ancillary_services_revenue(params)
    demand_response_revenue = _calculate_demand_response_revenue(params)
    grid_deferral_value = _calculate_grid_deferral_value(params)
    fixed_opex = _calculate_detailed_annual_costs(params)['total_annual_fixed_opex_usd']
    
    # 税务相关累计变量
    accumulated_depreciation = 0
    accumulated_losses = 0
    
    for year in years:
        # 1. 计算动态收入 (受效率衰减影响)
        current_efficiency = tech['round_trip_efficiency'] * ((1 - tech.get('annual_efficiency_degradation', 0)) ** (year - 1))
        
        temp_params = copy.deepcopy(params)
        temp_params['technical_specs']['round_trip_efficiency'] = current_efficiency
        
        arbitrage = _calculate_peak_valley_arbitrage_v2(temp_params) # 使用V2版套利计算
        subsidy = _calculate_subsidy_revenue(temp_params)
        
        total_revenue = (arbitrage['annual_gross_revenue_usd'] + capacity_revenue + ancillary_revenue + 
                         demand_response_revenue + grid_deferral_value + subsidy)
        
        # 2. 计算年度成本
        degradation_cost = arbitrage['annual_battery_degradation_cost_usd']
        total_opex = fixed_opex + degradation_cost
        
        # 3. 计算折旧 (使用选择的折旧方法)
        depreciation = _calculate_depreciation(
            params, 
            initial_investment_net_vat,
            year,
            accumulated_depreciation
        )
        accumulated_depreciation += depreciation
        
        # 4. 计算息税前利润
        ebit = total_revenue - total_opex - depreciation
        
        # 5. 处理亏损弥补 (中国税法允许5年内结转亏损)
        if ebit < 0:
            # 发生亏损，累计亏损增加
            accumulated_losses += abs(ebit)
            taxable_income = 0
        else:
            # 有盈利时，先用累计亏损抵扣
            if accumulated_losses > 0:
                deductible_loss = min(ebit, accumulated_losses)
                taxable_income = ebit - deductible_loss
                accumulated_losses -= deductible_loss
            else:
                taxable_income = ebit
        
        # 6. 计算所得税
        income_tax_rate = finance.get('income_tax_rate', 0.25)
        income_tax = max(0, taxable_income * income_tax_rate)
        
        # 7. 计算税后净利润
        net_profit = ebit - income_tax
        
        # 8. 计算项目自由现金流
        battery_replacement_cost = cost['battery_replacement_cost_usd'] if year == cost.get('battery_replacement_year') else 0
        # 项目自由现金流 = 税后净利润 + 折旧摊销 - 资本性支出(电池更换)
        project_cashflow = net_profit + depreciation - battery_replacement_cost
        
        # 9. 计算融资相关现金流 (债务还本付息)
        if year <= len(debt_schedule):
            debt_row = debt_schedule[debt_schedule['year'] == year].iloc[0]
            principal_payment = debt_row['principal_payment']
            interest_payment = debt_row['interest_payment']
        else:
            principal_payment = 0
            interest_payment = 0
            
        # 10. 计算股权自由现金流
        equity_cashflow = project_cashflow - principal_payment - interest_payment
        
        # 填充数据
        df_data['峰谷套利毛收入'].append(round(arbitrage['annual_gross_revenue_usd'], 2))
        df_data['容量电价收入'].append(capacity_revenue)
        df_data['辅助服务收入'].append(ancillary_revenue)
        df_data['需求响应收入'].append(demand_response_revenue)
        df_data['电网延缓价值'].append(grid_deferral_value)
        df_data['补贴收入'].append(subsidy)
        df_data['年度总收入'].append(round(total_revenue, 2))
        df_data['固定运维成本'].append(fixed_opex)
        df_data['电池衰减成本'].append(round(degradation_cost, 2))
        df_data['年度总运营成本'].append(round(total_opex, 2))
        df_data['折旧摊销'].append(round(depreciation, 2))
        df_data['息税前利润(EBIT)'].append(round(ebit, 2))
        df_data['可抵扣亏损累计'].append(round(accumulated_losses, 2))
        df_data['税前利润'].append(round(taxable_income, 2))
        df_data['所得税'].append(round(income_tax, 2))
        df_data['税后净利润'].append(round(net_profit, 2))
        df_data['电池更换成本'].append(battery_replacement_cost)
        df_data['项目自由现金流'].append(round(project_cashflow, 2))
        df_data['债务本金偿还'].append(round(principal_payment, 2))
        df_data['债务利息支付'].append(round(interest_payment, 2))
        df_data['股权自由现金流'].append(round(equity_cashflow, 2))

    df = pd.DataFrame(df_data)
    df.set_index('年份', inplace=True)
    return df, loan_amount, equity_amount, itc_credit

def _calculate_financial_metrics_v3(params: Dict[str, Any], cashflow_df: pd.DataFrame, 
                                    loan_amount: float, equity_amount: float, itc_credit: float) -> Dict[str, Any]:
    """(重构) 基于动态现金流量表计算最终财务指标"""
    finance = params['financial_assumptions']
    tech = params['technical_specs']
    
    discount_rate = finance['discount_rate']
    equity_discount_rate = finance.get('equity_discount_rate', discount_rate + 0.02)

    # 项目自由现金流 (用于计算项目IRR)
    project_cash_flows = [-equity_amount - loan_amount + itc_credit] + cashflow_df['项目自由现金流'].tolist()
    
    # 股权自由现金流 (用于计算股权IRR)
    equity_cash_flows = [-equity_amount + itc_credit] + cashflow_df['股权自由现金流'].tolist()
    
    # 计算项目NPV和IRR
    project_npv = npf.npv(discount_rate, project_cash_flows)
    try:
        project_irr = npf.irr(project_cash_flows)
    except:
        project_irr = float('nan')
    
    # 计算股权NPV和IRR
    equity_npv = npf.npv(equity_discount_rate, equity_cash_flows)
    try:
        equity_irr = npf.irr(equity_cash_flows)
    except:
        equity_irr = float('nan')
    
    # 计算债务偿付覆盖率(DSCR)
    dscr_yearly = []
    for idx, row in cashflow_df.iterrows():
        if row['债务本金偿还'] + row['债务利息支付'] > 0:
            dscr = (row['息税前利润(EBIT)'] + row['折旧摊销']) / (row['债务本金偿还'] + row['债务利息支付'])
            dscr_yearly.append(round(dscr, 2))
        else:
            dscr_yearly.append(float('nan'))
    
    min_dscr = min(dscr_yearly) if dscr_yearly else float('nan')
    avg_dscr = sum(dscr_yearly)/len(dscr_yearly) if dscr_yearly else float('nan')
    
    # LCOE (基于折现成本和折现电量)
    total_lifecycle_cost_pv = abs(npf.npv(discount_rate, [-equity_amount - loan_amount + itc_credit] + 
                                      (cashflow_df['固定运维成本'] + cashflow_df['电池更换成本']).tolist()))
    
    total_energy_pv = 0
    for i, year in enumerate(cashflow_df.index):
        daily_energy_mwh = tech['capacity_mwh'] * tech['depth_of_discharge_dod']
        annual_energy_kwh = daily_energy_mwh * 1000 * 365 * finance['charge_cycles_per_day']
        total_energy_pv += annual_energy_kwh / ((1 + discount_rate) ** (i + 1))
    
    lcoe = total_lifecycle_cost_pv / total_energy_pv if total_energy_pv > 0 else 0

    return {
        "project_npv_usd": f"{project_npv:,.2f}",
        "project_irr_percent": f"{project_irr:.2%}" if not np.isnan(project_irr) else "N/A",
        "equity_npv_usd": f"{equity_npv:,.2f}",
        "equity_irr_percent": f"{equity_irr:.2%}" if not np.isnan(equity_irr) else "N/A",
        "min_dscr": min_dscr,
        "avg_dscr": avg_dscr,
        "levelized_cost_of_storage_usd_per_kwh": round(lcoe, 4),
        "financing_summary": {
            "debt_amount": loan_amount,
            "equity_amount": equity_amount,
            "debt_ratio": params['financial_assumptions']['financing'].get('debt_ratio', 0),
            "itc_credit": itc_credit
        }
    }

# --- V3 新增的风险与敏感性分析模块 ---

def _perform_monte_carlo_simulation(params: Dict[str, Any], num_simulations: int = 5000) -> Dict[str, Any]:
    """(新增) 执行蒙特卡洛模拟进行风险评估"""
    mc_params = params['financial_assumptions'].get('monte_carlo', {})
    if not mc_params:
        return {"status": "未配置蒙特卡洛模拟参数"}

    project_irr_results = []
    equity_irr_results = []
    min_dscr_results = []
    
    for _ in range(num_simulations):
        sim_params = copy.deepcopy(params)
        
        # 对不确定性变量进行抽样
        price_dist = mc_params['peak_valley_price_diff']
        sim_price = np.random.normal(price_dist['mean'], price_dist['std_dev'])
        sim_params['market_and_policy']['peak_valley_price_diff_usd_per_kwh'] = sim_price

        invest_dist = mc_params['initial_investment']
        sim_investment = np.random.normal(invest_dist['mean'], invest_dist['std_dev'])
        sim_params['cost_structure']['total_investment_usd'] = sim_investment
        
        # 对融资变量抽样
        if 'debt_ratio' in mc_params:
            debt_dist = mc_params['debt_ratio']
            sim_debt_ratio = np.random.normal(debt_dist['mean'], debt_dist['std_dev'])
            sim_params['financial_assumptions']['financing']['debt_ratio'] = max(0, min(sim_debt_ratio, 0.8))

        try:
            # 重新计算动态现金流
            cf_df, loan_amount, equity_amount, itc_credit = _generate_dynamic_yearly_cashflow_statement(sim_params)
            metrics = _calculate_financial_metrics_v3(sim_params, cf_df, loan_amount, equity_amount, itc_credit)
            
            # 收集结果
            try:
                project_irr = float(metrics['project_irr_percent'].strip('%'))/100
                project_irr_results.append(project_irr)
            except:
                pass
                
            try:
                equity_irr = float(metrics['equity_irr_percent'].strip('%'))/100
                equity_irr_results.append(equity_irr)
            except:
                pass
                
            if not np.isnan(metrics['min_dscr']):
                min_dscr_results.append(metrics['min_dscr'])
        except:
            continue

    results = {"status": "分析完成", "num_simulations": num_simulations}
    
    if project_irr_results:
        results.update({
            "mean_project_irr": f"{np.mean(project_irr_results):.2%}",
            "std_dev_project_irr": f"{np.std(project_irr_results):.2%}",
            "percentile_5th_project_irr": f"{np.percentile(project_irr_results, 5):.2%}",
            "percentile_95th_project_irr": f"{np.percentile(project_irr_results, 95):.2%}",
            "probability_project_irr_above_discount_rate": 
                f"{np.sum(np.array(project_irr_results) > params['financial_assumptions']['discount_rate']) / len(project_irr_results):.2%}"
        })
    
    if equity_irr_results:
        equity_discount_rate = params['financial_assumptions'].get('equity_discount_rate', 
                                                                  params['financial_assumptions']['discount_rate'] + 0.02)
        results.update({
            "mean_equity_irr": f"{np.mean(equity_irr_results):.2%}",
            "std_dev_equity_irr": f"{np.std(equity_irr_results):.2%}",
            "percentile_5th_equity_irr": f"{np.percentile(equity_irr_results, 5):.2%}",
            "percentile_95th_equity_irr": f"{np.percentile(equity_irr_results, 95):.2%}",
            "probability_equity_irr_above_discount_rate": 
                f"{np.sum(np.array(equity_irr_results) > equity_discount_rate) / len(equity_irr_results):.2%}"
        })
    
    if min_dscr_results:
        results.update({
            "mean_min_dscr": round(np.mean(min_dscr_results), 2),
            "probability_dscr_below_1.2": f"{np.sum(np.array(min_dscr_results) < 1.2) / len(min_dscr_results):.2%}",
            "probability_dscr_below_1.0": f"{np.sum(np.array(min_dscr_results) < 1.0) / len(min_dscr_results):.2%}"
        })
    
    return results

def _perform_expanded_sensitivity_analysis(params: Dict[str, Any]) -> Dict[str, Any]:
    """(重构) 执行扩展的敏感性分析"""
    results = {}
    variables_to_test = {
        "峰谷价差": ('market_and_policy', 'peak_valley_price_diff_usd_per_kwh'),
        "初始投资": ('cost_structure', 'total_investment_usd'),
        "债务比例": ('financial_assumptions', 'financing', 'debt_ratio'),
        "贷款利率": ('financial_assumptions', 'financing', 'loan_interest_rate'),
        "辅助服务价格": ('market_and_policy', 'ancillary_service_revenue_usd_per_mw_year'),
        "运维成本率": ('cost_structure', 'annual_opex_rate_of_investment')
    }

    for name, path in variables_to_test.items():
        sensitivities = {}
        for change in [-0.2, -0.1, 0.1, 0.2]:
            temp_params = copy.deepcopy(params)
            
            # 动态修改参数值
            current_level = temp_params
            for key in path[:-1]:
                current_level = current_level[key]
                
            original_value = current_level[path[-1]]
            current_level[path[-1]] = original_value * (1 + change)
            
            try:
                # 重新计算现金流和财务指标
                cf_df, loan_amount, equity_amount, itc_credit = _generate_dynamic_yearly_cashflow_statement(temp_params)
                metrics = _calculate_financial_metrics_v3(temp_params, cf_df, loan_amount, equity_amount, itc_credit)
                
                # 同时记录项目IRR和股权IRR
                sensitivities[f"变化 {change:+.0%}"] = {
                    "项目IRR": metrics['project_irr_percent'],
                    "股权IRR": metrics['equity_irr_percent'],
                    "最小DSCR": metrics.get('min_dscr', 'N/A')
                }
            except:
                sensitivities[f"变化 {change:+.0%}"] = "计算错误"
        results[f"{name}_sensitivity"] = sensitivities
        
    return results

# --- 主MCP工具函数 (V3 - 专家版) ---
@mcp.tool()
async def analyze_storage_station_economics_expert(project_parameters: Dict[str, Any]) -> Dict[str, Any]:
    """
    一个专家级的储能电站经济效益与风险评估工具。
    它整合了多种盈利模式、详细的成本与税务模型、动态效率衰减、
    全面的敏感性分析以及蒙特卡洛风险模拟。
    """
    try:
        # --- 1. 生成核心的动态现金流量表 ---
        cashflow_statement_df, loan_amount, equity_amount, itc_credit = _generate_dynamic_yearly_cashflow_statement(project_parameters)
        
        # --- 2. 计算基准情景下的财务指标 ---
        financial_summary = _calculate_financial_metrics_v3(
            project_parameters, 
            cashflow_statement_df,
            loan_amount,
            equity_amount,
            itc_credit
        )

        # --- 3. 执行扩展的敏感性分析 ---
        sensitivity_report = _perform_expanded_sensitivity_analysis(project_parameters)

        # --- 4. 执行蒙特卡洛风险模拟 ---
        monte_carlo_report = _perform_monte_carlo_simulation(project_parameters)

        # --- 5. 组装最终的专家报告 ---
        analysis_report = {
            "project": project_parameters.get("project_info", {}),
            "assessment_summary": {
                "verdict": "项目在基准情景下具备投资价值，且风险评估结果较为乐观。" 
                           if financial_summary.get('project_irr_percent', '0%') != 'N/A' and 
                              float(financial_summary['project_irr_percent'].strip('%')) > project_parameters['financial_assumptions']['discount_rate']*100 and
                              financial_summary.get('min_dscr', 0) > 1.2
                           else "项目在基准情景下盈利能力较弱或风险过高，建议谨慎投资。",
                **financial_summary
            },
            "risk_assessment_monte_carlo": monte_carlo_report,
            "sensitivity_analysis": sensitivity_report,
            "detailed_financials_statement": cashflow_statement_df.reset_index().round(2).to_dict(orient='records')
        }
        return analysis_report

    except KeyError as e:
        return {"error": f"输入参数缺失: 缺少关键字段 '{e}'。请检查 'project_parameters' 字典的完整性。"}
    except Exception as e:
        import traceback
        return {"error": f"计算过程中发生未知错误: {e}", "trace": traceback.format_exc()}

# ===== 辅助函数 (需要实现) =====
def _calculate_capacity_tariff_revenue(params: Dict[str, Any]) -> float:
    """计算容量电价收入 (示例实现)"""
    market = params['market_and_policy']
    capacity = params['technical_specs']['max_power_mw']
    capacity_price = market.get('capacity_price_usd_per_mw_year', 0)
    return capacity * capacity_price

def _calculate_ancillary_services_revenue(params: Dict[str, Any]) -> float:
    """计算辅助服务收入 (示例实现)"""
    market = params['market_and_policy']
    capacity = params['technical_specs']['max_power_mw']
    ancillary_price = market.get('ancillary_service_revenue_usd_per_mw_year', 0)
    return capacity * ancillary_price

def _calculate_subsidy_revenue(params: Dict[str, Any]) -> float:
    """计算补贴收入 (示例实现)"""
    market = params['market_and_policy']
    tech = params['technical_specs']
    daily_energy = tech['capacity_mwh'] * tech['depth_of_discharge_dod']
    annual_energy = daily_energy * 365 * params['financial_assumptions']['charge_cycles_per_day']
    subsidy_rate = market.get('subsidy_per_kwh_discharged_usd', 0)
    return annual_energy * 1000 * subsidy_rate

def _calculate_peak_valley_arbitrage_v2(params: Dict[str, Any]) -> Dict[str, float]:
    """峰谷套利计算 (示例实现)"""
    market = params['market_and_policy']
    tech = params['technical_specs']
    finance = params['financial_assumptions']
    
    # 简化计算
    daily_energy_kwh = tech['capacity_mwh'] * tech['depth_of_discharge_dod'] * 1000
    price_diff = market['peak_valley_price_diff_usd_per_kwh']
    efficiency = tech['round_trip_efficiency']
    
    daily_gross_revenue = daily_energy_kwh * price_diff * efficiency
    annual_gross_revenue = daily_gross_revenue * 365 * finance['charge_cycles_per_day']
    
    # 简化的电池衰减成本
    degradation_cost = daily_energy_kwh * finance.get('degradation_cost_per_kwh', 0.05) * 365 * finance['charge_cycles_per_day']
    
    return {
        'annual_gross_revenue_usd': annual_gross_revenue,
        'annual_battery_degradation_cost_usd': degradation_cost
    }

if __name__ == "__main__":
    mcp.run(transport='stdio')