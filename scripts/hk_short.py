#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
港股沽空数据分析模块 (HK Stock Short Selling Analyzer) — 重写版

双口径集成:
  1. 每日沽空流量 (Flow)  — 东财 RPT_HK_SHORTSELLING (沽空比率=当日沽空金额/成交金额)
  2. 未平仓淡仓存量 (Stock) — SFC 汇总可申报淡仓 CSV (淡仓市值/总市值 = 占市值%)

用法:
    from hk_short import HKShortAnalyzer
    a = HKShortAnalyzer()
    r = a.analyze_single_stock('03690', '美团-W', days=15)
    # r['summary'] 含: latest_short_ratio(流量) + open_short_pct(存量占市值%)
"""

from datetime import datetime
import json
import logging
import subprocess
import csv
import io
from typing import Dict, List, Optional
import pandas as pd
import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("HKShortAnalyzer")


class HKShortAnalyzer:
    """港股做空数据采集与分析器 (流量 + 存量双口径)"""

    BASE_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
    SFC_LATEST_CSV = ("https://www.sfc.hk/en/Regulatory-functions/Market/"
                      "Short-position-reporting/"
                      "Aggregated-reportable-short-positions-of-specified-shares/"
                      "Latest-CSV")
    QT_URL = "https://qt.gtimg.cn/q="

    # 预设常用股票代码映射
    DEFAULT_STOCKS = {
        "03690": "美团-W",
        "09988": "阿里巴巴-W",
        "01024": "快手-W",
        "00700": "腾讯控股",
        "01810": "小米集团-W",
    }

    def __init__(self, timeout: int = 15):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
        })

    @staticmethod
    def _safe_float(val, default: float = 0.0) -> float:
        try:
            if val is None or (isinstance(val, float) and pd.isna(val)):
                return default
            return float(val)
        except (ValueError, TypeError):
            return default

    # ------------------------------------------------------------------
    # 模块 1: 每日沽空流量 (Flow) — 东财
    # ------------------------------------------------------------------
    def fetch_daily_short_flow(self, stock_code: str, days: int = 15):
        """抓取日度沽空流量 (RPT_HK_SHORTSELLING)。

        :param stock_code: 5位港股代码 (如 '03690')
        :return: DataFrame 含 close_price/短期_shares/amount/ratio + delta/ma5
        """
        fetch_size = days + 10
        params = {
            "reportName": "RPT_HK_SHORTSELLING",
            "columns": "ALL",
            "filter": f'(SECURITY_CODE="{stock_code}")',
            "pageNumber": "1",
            "pageSize": str(fetch_size),
            "sortTypes": "-1",
            "sortColumns": "TRADE_DATE",
            "source": "WEB",
            "client": "WEB",
        }
        try:
            resp = self.session.get(self.BASE_URL, params=params, timeout=self.timeout)
            resp.raise_for_status()
            res_json = resp.json()
            if not res_json.get("result") or not res_json["result"].get("data"):
                logger.warning(f"未获取到 {stock_code} 每日沽空数据 (返回空)")
                return None
            raw_df = pd.DataFrame(res_json["result"]["data"])
            df = pd.DataFrame({
                "date": pd.to_datetime(raw_df["TRADE_DATE"]),
                "avg_price": pd.to_numeric(raw_df.get("AVG_PRICE"), errors="coerce"),
                "short_shares": pd.to_numeric(raw_df["SHORT_SELLING_SHARES"], errors="coerce"),
                "short_amount": pd.to_numeric(raw_df["SHORT_SELLING_AMT"], errors="coerce"),
                "short_ratio": pd.to_numeric(raw_df["SHORT_SELLING_RATIO"], errors="coerce"),
            })
            df = (df.dropna(subset=["date", "short_ratio"])
                    .sort_values("date").reset_index(drop=True))
            df["delta_ssr"] = df["short_ratio"].diff()
            df["delta2_ssr"] = df["delta_ssr"].diff()
            df["short_ratio_ma5"] = df["short_ratio"].rolling(5, min_periods=1).mean()
            return df.tail(days).reset_index(drop=True)
        except Exception as e:
            logger.error(f"抓取 {stock_code} 每日沽空流量失败: {e}")
            return None

    # ------------------------------------------------------------------
    # 模块 2: 未平仓淡仓存量 (Stock) — SFC 汇总可申报淡仓
    # ------------------------------------------------------------------
    def fetch_sfc_short_positions(self) -> Optional[pd.DataFrame]:
        """抓取 SFC 汇总可申报淡仓 CSV (每周公布, 最新一期)。

        返回 DataFrame 含: code/name/report_date/short_shares/short_market_val
        """
        try:
            r = subprocess.run(
                ['curl', '-sL', '--max-time', '20', self.SFC_LATEST_CSV],
                stdout=subprocess.PIPE, timeout=25)
            raw = r.stdout.decode('utf-8-sig', errors='replace')
            if not raw or 'Stock Code' not in raw:
                logger.warning("SFC 淡仓 CSV 下载失败")
                return None
            rows = list(csv.DictReader(io.StringIO(raw)))
            df = pd.DataFrame([{
                "code": row["Stock Code"].strip().zfill(5),
                "name": row["Stock Name"].strip(),
                "report_date": row["Date"].strip(),
                "short_shares": self._safe_float(
                    row["Aggregated Reportable Short Positions (Shares)"]),
                "short_market_val": self._safe_float(
                    row["Aggregated Reportable Short Positions (HK$)"].replace(",", "")),
            } for row in rows])
            return df
        except Exception as e:
            logger.error(f"抓取 SFC 淡仓存量失败: {e}")
            return None

    def fetch_market_cap(self, stock_codes: List[str]) -> Dict[str, float]:
        """拉港股总市值 (亿港元), 腾讯接口。返回 {code: market_cap_yi}"""
        caps = {}
        if not stock_codes:
            return caps
        q = ','.join(f'r_hk{c}' for c in stock_codes)
        try:
            r = subprocess.run(['curl', '-s', '--max-time', '12', self.QT_URL + q],
                               stdout=subprocess.PIPE, timeout=15)
            raw = r.stdout.decode('gbk', errors='replace')
            for line in raw.split(';'):
                if '=' not in line:
                    continue
                f = line.split('~')
                if len(f) < 50:
                    continue
                # 腾讯港股字段: [2]代码 [3]现价 [45]总市值(亿)
                code = f[2]
                mc = f[45] if len(f) > 45 and f[45] else f[44]
                if code and mc:
                    caps[code] = self._safe_float(mc)
        except Exception as e:
            logger.error(f"拉市值失败: {e}")
        return caps

    # ------------------------------------------------------------------
    # 模块 3: 综合分析 (流量 + 存量合并)
    # ------------------------------------------------------------------
    def analyze_single_stock(self, stock_code: str, stock_name: str = "",
                             days: int = 15) -> Dict:
        stock_name = stock_name or self.DEFAULT_STOCKS.get(stock_code, stock_code)
        logger.info(f"开始分析 {stock_name} ({stock_code})...")

        # 1. 每日沽空流量
        df_flow = self.fetch_daily_short_flow(stock_code, days=days)
        if df_flow is None or df_flow.empty:
            return {"code": stock_code, "name": stock_name,
                    "status": "failed", "message": "无法获取日流量数据"}

        # 2. 未平仓淡仓存量 (SFC) + 市值
        stock_meta = {}
        try:
            df_sfc = self.fetch_sfc_short_positions()
            if df_sfc is not None and not df_sfc.empty:
                row = df_sfc[df_sfc["code"] == stock_code]
                if not row.empty:
                    r = row.iloc[0]
                    caps = self.fetch_market_cap([stock_code])
                    mc = caps.get(stock_code, 0.0)
                    short_val = r["short_market_val"]
                    stock_meta = {
                        "open_short_report_date": r["report_date"],
                        "open_short_shares_wan": round(r["short_shares"] / 1e4, 2),
                        "open_short_market_val_yi": round(short_val / 1e8, 2),
                        "market_cap_yi": round(mc, 1),
                        # 淡仓市值 / 总市值 = 占市值百分比
                        "open_short_pct_mktcap": round(short_val / (mc * 1e8) * 100, 3)
                        if mc > 0 else None,
                    }
        except Exception as e:
            logger.warning(f"淡仓存量获取失败: {e}")

        # 3. 流量汇总
        latest_row = df_flow.iloc[-1]
        summary = {
            "total_short_shares_wan": round(df_flow["short_shares"].sum() / 1e4, 2),
            "total_short_amount_yi": round(df_flow["short_amount"].sum() / 1e8, 2),
            "avg_short_ratio": round(df_flow["short_ratio"].mean(), 2),
            "max_short_ratio": round(df_flow["short_ratio"].max(), 2),
            "max_short_ratio_date": df_flow.loc[
                df_flow["short_ratio"].idxmax(), "date"].strftime("%Y-%m-%d"),
            "latest_date": latest_row["date"].strftime("%Y-%m-%d"),
            "latest_avg_price": round(self._safe_float(latest_row["avg_price"]), 2),
            "latest_short_ratio": round(self._safe_float(latest_row["short_ratio"]), 2),
            "latest_short_amount_yi": round(
                self._safe_float(latest_row["short_amount"]) / 1e8, 2),
            **stock_meta,
        }

        # 4. 明细 (时间倒序)
        records = []
        for _, row in df_flow.sort_values("date", ascending=False).iterrows():
            records.append({
                "date": row["date"].strftime("%Y-%m-%d"),
                "avg_price": round(self._safe_float(row["avg_price"]), 2),
                "short_shares_wan": round(self._safe_float(row["short_shares"]) / 1e4, 1),
                "short_amount_yi": round(self._safe_float(row["short_amount"]) / 1e8, 2),
                "short_ratio": round(self._safe_float(row["short_ratio"]), 2),
                "delta_ssr": round(self._safe_float(row["delta_ssr"]), 2),
                "short_ratio_ma5": round(self._safe_float(row["short_ratio_ma5"]), 2),
            })

        return {
            "code": stock_code, "name": stock_name, "status": "success",
            "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "summary": summary, "records": records,
        }

    def analyze_batch(self, stock_dict: Optional[Dict[str, str]] = None,
                      days: int = 15) -> Dict[str, Dict]:
        target_stocks = stock_dict or self.DEFAULT_STOCKS
        batch_result = {}
        for code, name in target_stocks.items():
            batch_result[code] = self.analyze_single_stock(code, name, days=days)
        return batch_result


if __name__ == "__main__":
    a = HKShortAnalyzer()
    batch = a.analyze_batch(days=15)

    print("\n===== 港股科技五大龙头 沽空双口径对比 =====")
    print(f"{'名称':<10} {'流量(当日沽空率)':<16} {'存量(淡仓占市值%)':<16} {'淡仓市值(亿)':<12}")
    print("-" * 60)
    for code, data in batch.items():
        if data.get("status") != "success":
            print(f"{data['name']}: 失败")
            continue
        s = data["summary"]
        print(f"{data['name']:<10} {s.get('latest_short_ratio', 0):>8}%       "
              f"{s.get('open_short_pct_mktcap', 'N/A'):>8}%       "
              f"{s.get('open_short_market_val_yi', 0):>8}")

    with open("hk_short_analysis_production.json", "w", encoding="utf-8") as f:
        json.dump(batch, f, ensure_ascii=False, indent=2)
    print(f"\n完整报告已写入: hk_short_analysis_production.json")
