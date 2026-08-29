"""数据源工厂——创建 AkShare 数据源实例。"""
from typing import Optional

from data_source.akshare_source import AkShareSource

DATA_SOURCE_CHOICES = [("akshare", "AkShare (A股)")]


def create_data_source(kind: Optional[str] = None) -> AkShareSource:
    return AkShareSource()
