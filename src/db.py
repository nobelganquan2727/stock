import os
import pandas as pd
from sqlalchemy import create_engine, Column, Integer, String, Float, Date, BigInteger, UniqueConstraint, text
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.dialects.mysql import insert
from dotenv import load_dotenv

load_dotenv()

Base = declarative_base()


class DailyStockData(Base):
    __tablename__ = 'daily_stock_data'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(20), nullable=False)
    date = Column(Date, nullable=False)
    open = Column(Float)
    close = Column(Float)
    high = Column(Float)
    low = Column(Float)
    volume = Column(BigInteger)
    percentage = Column(Float)

    __table_args__ = (
        UniqueConstraint('date', 'code', name='uix_date_code'),
    )


def get_engine():
    db_user = os.getenv('DB_USER', 'root')
    db_password = os.getenv('DB_PASSWORD', '')
    db_host = os.getenv('DB_HOST', 'localhost')
    db_port = os.getenv('DB_PORT', '3306')
    db_name = os.getenv('DB_NAME', 'astock_data')
    
    # create database if not exists
    engine_temp = create_engine(f"mysql+pymysql://{db_user}:{db_password}@{db_host}:{db_port}")
    print(engine_temp)

    with engine_temp.connect() as conn:
        conn.execute(text(f"CREATE DATABASE IF NOT EXISTS {db_name}"))
        conn.commit()
    
    database_url = f"mysql+pymysql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    return create_engine(database_url)


def init_db(engine):
    Base.metadata.create_all(engine)


def get_latest_date(engine, code: str):
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        latest = session.query(DailyStockData).filter(DailyStockData.code==code).order_by(DailyStockData.date.desc()).first()
        return latest.date if latest else None
    finally:
        session.close()


def upsert_stock_data(engine, df: pd.DataFrame):
    """
    Upsert pandas DataFrame into daily_stock_data.
    df must have columns: date, code, open, close, high, low, volume, percentage
    """
    if df.empty:
        return
    
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        # handle nan values
        df = df.astype(object).where(pd.notna(df), None)
        records = df.to_dict(orient='records')
        stmt = insert(DailyStockData).values(records)
        
        # On duplicate key update
        update_dict = {
            'open': stmt.inserted.open,
            'close': stmt.inserted.close,
            'high': stmt.inserted.high,
            'low': stmt.inserted.low,
            'volume': stmt.inserted.volume,
            'percentage': stmt.inserted.percentage,
        }
        
        upsert_stmt = stmt.on_duplicate_key_update(**update_dict)
        session.execute(upsert_stmt)
        session.commit()
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()
