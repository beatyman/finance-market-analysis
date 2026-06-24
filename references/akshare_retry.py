"""AKShare 东财API重试模板 — 频率限制超时自动重试"""
import akshare as ak,time,warnings
warnings.filterwarnings('ignore')

def retry_ak(fn, max_retries=3, base_wait=5):
    """调用AKShare函数，超时自动重试
    
    Args:
        fn: 无参数的lambda/函数
        max_retries: 最多尝试次数(含首次)
        base_wait: 基础等待秒数(每次递增)
    
    Returns:
        fn的返回值 或 None(全部失败)
    """
    for i in range(max_retries):
        try:
            return fn()
        except Exception as e:
            err=str(e)
            if 'RemoteDisconnected' in err or 'Connection aborted' in err:
                if i < max_retries - 1:
                    wait = base_wait * (i + 1)
                    print(f'  限流, {wait}s后重试({i+2}/{max_retries})...')
                    time.sleep(wait)
            else:
                raise  # 非限流错误直接抛出
    return None

if __name__ == '__main__':
    # 示例
    df = retry_ak(lambda: ak.stock_board_industry_name_em())
    if df is not None:
        print(f'行业板块: {len(df)}个')
        print(df.head(3)[['板块名称','涨跌幅']].to_string())
    
    df2 = retry_ak(lambda: ak.stock_board_concept_name_em())
    if df2 is not None:
        print(f'概念板块: {len(df2)}个')
    """
