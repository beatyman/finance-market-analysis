"""
CSVTrainingAPI — Custom data source for chan.py step_load().
Registers symbol → CSV path mapping, feeds data from CSV files.

Usage:
    from DataAPI.CSVTrainingAPI import CSVTrainingAPI, set_csv_override
    set_csv_override("000001", "/path/to/000001.csv")
    # Then in CChan: data_src="custom:CSVTrainingAPI.CSVTrainingAPI"
"""
import os
from typing import Dict, Optional

from Common.CEnum import DATA_FIELD, KL_TYPE
from Common.CTime import CTime
from Common.func_util import str2float
from KLine.KLine_Unit import CKLine_Unit

from .CommonStockAPI import CCommonStockApi

# Global registry: symbol → CSV file path
_csv_registry: Dict[str, str] = {}


def set_csv_override(symbol: str, csv_path: str):
    """Register a CSV file path for a symbol."""
    _csv_registry[symbol] = csv_path


def get_csv_path(symbol: str) -> Optional[str]:
    return _csv_registry.get(symbol)


def clear_registry():
    _csv_registry.clear()


class CSVTrainingAPI(CCommonStockApi):
    """Custom data source that feeds K-lines from registered CSV files."""

    def __init__(self, code, k_type=KL_TYPE.K_DAY, begin_date=None, end_date=None, autype=None):
        self.code = code
        self.k_type = k_type
        self.begin_date = begin_date
        self.end_date = end_date
        self.autype = autype
        
        self.columns = [
            DATA_FIELD.FIELD_TIME,
            DATA_FIELD.FIELD_OPEN,
            DATA_FIELD.FIELD_HIGH,
            DATA_FIELD.FIELD_LOW,
            DATA_FIELD.FIELD_CLOSE,
            DATA_FIELD.FIELD_VOLUME,
        ]
        self.time_column_idx = 0
        
        super().__init__(code, k_type, begin_date, end_date, autype)

    def get_kl_data(self):
        csv_path = _csv_registry.get(self.code)
        if not csv_path or not os.path.exists(csv_path):
            # Try looking in data/processed/
            alt_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                "data", "processed", f"{self.code}.csv"
            )
            if os.path.exists(alt_path):
                csv_path = alt_path
        
        if not csv_path or not os.path.exists(csv_path):
            return  # No data, empty generator
        
        with open(csv_path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                data = line.split(',')
                if len(data) < 5:
                    continue
                
                # Parse time
                time_str = data[0]
                if len(time_str) == 10:  # 2023-01-01
                    year = int(time_str[:4])
                    month = int(time_str[5:7])
                    day = int(time_str[8:10])
                    hour = minute = 0
                else:
                    continue  # Skip unknown formats
                
                ct = CTime(year, month, day, hour, minute)
                
                # Check date range
                date_str = f"{year:04d}-{month:02d}-{day:02d}"
                if self.begin_date and date_str < self.begin_date:
                    continue
                if self.end_date and date_str > self.end_date:
                    continue
                
                item = {
                    DATA_FIELD.FIELD_TIME: ct,
                    DATA_FIELD.FIELD_OPEN: str2float(data[1]),
                    DATA_FIELD.FIELD_HIGH: str2float(data[2]),
                    DATA_FIELD.FIELD_LOW: str2float(data[3]),
                    DATA_FIELD.FIELD_CLOSE: str2float(data[4]),
                    DATA_FIELD.FIELD_VOLUME: str2float(data[5]) if len(data) > 5 else 1.0,
                }
                yield CKLine_Unit(item)

    def SetBasciInfo(self):
        pass

    @classmethod
    def do_init(cls):
        pass

    @classmethod
    def do_close(cls):
        pass
