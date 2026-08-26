#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
港股窝轮/牛熊证数据获取模块 (HK Warrant / CBBC Fetcher)

三种数据源 (按可用性排序):
  1. AASTOCKS 导出文件解析 (本地, 不受DNS劫持影响) ← 最可靠
  2. AASTOCKS API 直连 (getwarrantcbbcdata.ashx, 需环境可访问 aastocks)
  3. 港交所官方 (Securities List 数据产品, 需 ProductID)

用法:
    # 方式1: AASTOCKS 导出文件解析
    from hk_warrant import load_warrant_data, filter_by_underlying
    df = load_warrant_data('aastocks_warrant_list.csv')
    df_mt = filter_by_underlying(df, '03690')

    # 方式2: AASTOCKS API 直连
    from hk_warrant import AAStocksWarrantFetcher
    f = AAStocksWarrantFetcher()
    df_w = f.fetch_derivative_data('03690', data_type=1)  # 1=窝轮 2=牛熊证
"""

import logging
from pathlib import Path
from typing import Optional
import pandas as pd
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("HKWarrant")


# ═══════════════ 方式1: AASTOCKS 导出文件解析 (本地) ═══════════════

COLUMN_MAP = {
    "名称": "name", "代号": "code", "购/沽": "type", "牛/熊": "type",
    "相关资产": "underlying", "发行": "issuer", "现价": "last_price",
    "升跌": "change", "升跌(%)": "change_pct", "成交额": "turnover",
    "溢价(%)": "premium", "价内/外": "moneyness",
    "实际杠杆": "effective_gearing", "杠杆": "effective_gearing",
    "引伸波幅": "iv", "行使价": "strike", "收回价": "call_level",
    "换股比率": "ratio", "街货(%)": "outstanding_ratio",
    "街货量": "outstanding", "最后交易日": "expiry", "热门": "hot",
}


def load_warrant_data(file_path: str) -> pd.DataFrame:
    """读取并清洗 AASTOCKS 导出的窝轮/牛熊证数据 (CSV 或 Excel)。"""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"找不到文件: {file_path}")
    if path.suffix.lower() in (".xlsx", ".xls"):
        df = pd.read_excel(file_path)
    else:
        df = pd.read_csv(file_path, encoding="utf-8-sig")
    df = df.rename(columns={k: v for k, v in COLUMN_MAP.items() if k in df.columns})
    return df


def filter_by_underlying(df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
    """按正股过滤。AASTOCKS 导出的'相关资产'是正股名称(如'美团'), 支持代码或名称。

    用法: filter_by_underlying(df, '03690') 或 filter_by_underlying(df, '美团')
    """
    if "underlying_code" in df.columns:
        code = str(stock_code).zfill(5)
        mask = df["underlying_code"].astype(str).str.zfill(5) == code
    elif "underlying" in df.columns:
        # AASTOCKS '相关资产' 是名称; 也兼容代码匹配
        s = df["underlying"].astype(str)
        mask = s.str.contains(str(stock_code), na=False)
        if not mask.any() and str(stock_code).isdigit():
            mask = s.str.contains(str(stock_code).lstrip("0"), na=False)
    else:
        raise ValueError("未找到正股相关字段，请检查导出文件列名")
    return df[mask].copy()


# ═══════════════ 方式2: AASTOCKS API 直连 ═══════════════

class AAStocksWarrantFetcher:
    """AASTOCKS 窝轮/牛熊证 API 直连 (无Cookie, 关键在正确Referer)。"""

    BASE_URL = "https://www.aastocks.com/sc/resources/datafeed/getwarrantcbbcdata.ashx"
    REFERER = "https://www.aastocks.com/sc/stocks/warrantcbbc/search.aspx"

    def __init__(self, timeout: int = 15):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/151.0.0.0 Safari/537.36"),
            "Referer": self.REFERER,
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/javascript, */*; q=0.01",
        })

    def _build_filter_param(self, stock_code: str) -> str:
        clean_code = stock_code.zfill(5).lstrip("0")
        pipes = "|" * 79
        return f"{clean_code}{pipes}0|0|0|0|0"

    def fetch_derivative_data(self, stock_code: str, data_type: int = 1,
                              page_size: int = 500) -> Optional[pd.DataFrame]:
        """data_type: 1=窝轮(Warrant) 2=牛熊证(CBBC)。返回标准化 DataFrame。"""
        type_name = "窝轮" if data_type == 1 else "牛熊证"
        # co 列配置: 窝轮含14/15/16(价内外/实际杠杆/引伸波幅), 牛熊证含26/27/23(收回价/杠杆/换股比率)
        if data_type == 1:
            co = "|1|2|3|4|5|6|8|9|11|12|14|15|16|17|19|20|21|7|13|25|29|"
        else:
            co = "|1|2|3|4|5|6|8|9|11|12|17|26|27|23|19|20|21|7|13|25|29|"
        params = {
            "t": str(data_type),
            "co": co,
            "s": "", "o": "", "f": self._build_filter_param(stock_code),
            "pi": "1", "exp": "Y", "ps": str(page_size),
        }
        try:
            resp = self.session.get(self.BASE_URL, params=params, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            if not data or "list" not in data:
                logger.warning(f"未获取到 {stock_code} {type_name} 数据")
                return None
            df = pd.DataFrame(data["list"])
            # API 实际字段 → 标准字段
            df = df.rename(columns={
                "sym": "code", "udly": "underlying", "issuer": "issuer",
                "last": "last_price", "turn": "turnover", "strike": "strike",
                "efgear": "effective_gearing", "iv": "iv",
                "calllv": "call_level", "gear": "gearing", "enratio": "ratio",
                "pctout": "outstanding_ratio", "outq": "outstanding",
                "ldate": "expiry", "premi": "premium", "movalue": "moneyness",
                "desp": "name", "chg": "change", "pctchg": "change_pct",
            })
            # 类型映射: 窝轮 C=认购/P=认沽; 牛熊证 C=牛/P=熊
            if data_type == 1:
                df["type"] = df["type"].map({"C": "认购", "P": "认沽"})
            else:
                df["type"] = df["type"].map({"C": "牛", "P": "熊"})
            logger.info(f"成功抓取 {stock_code} {type_name} {len(df)} 条")
            return df
        except Exception as e:
            logger.error(f"AASTOCKS {type_name} 接口失败: {e}")
            return None


# ═══════════════ 方式3: 港交所官方 (修复版) ═══════════════

class HKEXOfficialFetcher:
    """港交所官方窝轮/牛熊证数据 (Securities List 数据产品, 需 ProductID)。

    注意: 港交所数据产品下载 URL 带动态 ProductID, 需从港交所数据产品页获取。
    证券列表 CSV 含: 行使价/收回价/到期日/换股比率/街货量 等字段。
    """

    # 港交所数据产品下载端点 (ProductID 动态, 需替换)
    HKEX_DATA_URL = ("https://hkex.com.hk/eng/ods/historicalDataProfile.aspx"
                     "?ProductID={product_id}&SchemeID={scheme_id}&isPrint=Y")

    def __init__(self, timeout: int = 15):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/120.0.0.0 Safari/537.36"),
            "Accept": "application/json, text/javascript, */*; q=0.01",
        })

    def fetch_full_list(self, product_id: str, scheme_id: str) -> Optional[pd.DataFrame]:
        """下载港交所证券列表 (窝轮/牛熊证) CSV。需传入数据产品的 ProductID/SchemeID。"""
        import io
        url = self.HKEX_DATA_URL.format(product_id=product_id, scheme_id=scheme_id)
        try:
            resp = self.session.get(url, timeout=self.timeout)
            resp.raise_for_status()
            df = pd.read_csv(io.StringIO(resp.text))
            logger.info(f"港交所证券列表 {len(df)} 条")
            return df
        except Exception as e:
            logger.error(f"港交所数据下载失败: {e}")
            return None


if __name__ == "__main__":
    # 方式1: AASTOCKS 导出文件解析 (本地, 最可靠)
    import sys
    if len(sys.argv) > 1:
        fpath = sys.argv[1]
        code = sys.argv[2] if len(sys.argv) > 2 else "03690"
        df_all = load_warrant_data(fpath)
        print(f"读取全部数据 {len(df_all)} 条")
        df_target = filter_by_underlying(df_all, code)
        print(f"正股 {code} 相关 {len(df_target)} 只:")
        print(df_target.head(20).to_string(index=False))
        out = f"warrant_{code}.csv"
        df_target.to_csv(out, index=False, encoding="utf-8-sig")
        print(f"\n已保存: {out}")
