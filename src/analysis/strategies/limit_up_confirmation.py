import pandas as pd
from .base import BaseStrategy, SignalResult

class LimitUpConfirmationStrategy(BaseStrategy):
    """
    涨停确认策略
    1. 先找到近 40 天来首次出现涨停的票
    2. 然后再看它之后 3-5 天的表现：
       2.1 这 3-5 天回踩 5 日均线
       2.2 这 3-5 加个慢慢回落，但不能跌破涨停那天的低点，而且量能不能太大
    """

    @property
    def name(self) -> str:
        return "涨停确认"

    def analyze(self, data: pd.DataFrame) -> SignalResult:
        if len(data) < 50:
            return SignalResult(False, self.name, 0.0, {"reason": "数据不足50天"})

        df = data.copy()
        
        # 确保日期升序（基类通常已保证，但为安全起见）
        if 'date' in df.columns:
            df = df.sort_values('date').reset_index(drop=True)
            
        # 计算涨跌幅
        df['pct_change'] = df['close'] / df['close'].shift(1) - 1
        # 涨停判断：涨幅 >= 9.5%（适用于主板10%涨跌幅限制）
        df['is_limit_up'] = df['pct_change'] >= 0.095
        
        # 计算 5日均线
        df['ma5'] = df['close'].rolling(window=5).mean()
        
        current_idx = len(df) - 1
        
        # 1. 寻找前 3-5 天的涨停
        limit_up_idx = -1
        # 从近到远找（3天前，4天前，5天前）
        for i in range(3, 6):
            check_idx = current_idx - i
            if check_idx < 0:
                continue
            if df['is_limit_up'].iloc[check_idx]:
                limit_up_idx = check_idx
                break
                
        if limit_up_idx == -1:
            return SignalResult(False, self.name, 0.0, {"reason": "近3-5天内未出现涨停"})
            
        # 检查是否为近 40 天内首次涨停
        start_check_idx = max(0, limit_up_idx - 40)
        # limit_up_idx 之前的 40 天
        if df['is_limit_up'].iloc[start_check_idx : limit_up_idx].any():
            return SignalResult(False, self.name, 0.0, {"reason": "并非近40天内首次涨停"})
            
        # 取出涨停后到目前的 3-5 天数据
        after_limit_up_df = df.iloc[limit_up_idx + 1 : current_idx + 1]
        
        # 2.1 回踩 5 日均线 (最低价触及或跌破 5日均线的 1.015 倍，给予一点容错)
        touched_ma5 = (after_limit_up_df['low'] <= after_limit_up_df['ma5'] * 1.015).any()
        if not touched_ma5:
            return SignalResult(False, self.name, 0.0, {"reason": "未回踩5日均线"})
            
        # 2.2 不能跌破涨停那天的低点
        limit_up_low = df['low'].iloc[limit_up_idx]
        if (after_limit_up_df['low'] < limit_up_low).any():
            return SignalResult(False, self.name, 0.0, {"reason": "期间跌破涨停日低点"})
            
        # 2.2 慢慢回落：当前收盘价不能太高，定义为不超过涨停日收盘价的 1.03 倍
        limit_up_close = df['close'].iloc[limit_up_idx]
        current_close = df['close'].iloc[current_idx]
        if current_close > limit_up_close * 1.03:
             return SignalResult(False, self.name, 0.0, {"reason": "未见回落，价格偏高"})
             
        # 2.2 量能不能太大
        limit_up_vol = df['volume'].iloc[limit_up_idx]
        avg_vol_after = after_limit_up_df['volume'].mean()
        max_vol_after = after_limit_up_df['volume'].max()
        
        # 要求回落期间平均量能明显缩量，且无单日异常巨量
        if avg_vol_after >= limit_up_vol * 0.9:
             return SignalResult(False, self.name, 0.0, {"reason": "回落期间均量过大"})
             
        if max_vol_after >= limit_up_vol * 1.2:
             return SignalResult(False, self.name, 0.0, {"reason": "回落期间存在单日放量"})
             
        # 满足所有条件，返回信号
        # 日期格式化处理
        limit_up_date_val = df['date'].iloc[limit_up_idx] if 'date' in df.columns else limit_up_idx
        if isinstance(limit_up_date_val, pd.Timestamp):
            limit_up_date_str = limit_up_date_val.strftime('%Y-%m-%d')
        else:
            limit_up_date_str = str(limit_up_date_val)

        details = {
            "limit_up_date": limit_up_date_str,
            "days_since_limit_up": int(current_idx - limit_up_idx),
            "limit_up_close": float(round(limit_up_close, 2)),
            "current_close": float(round(current_close, 2))
        }
        
        return SignalResult(True, self.name, 0.85, details)
