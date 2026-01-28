import abc

from typing import List, Any

from dataclasses import dataclass


@dataclass
class DataPoint:
    # identify the type of the data
    typename: str
    # additional metadata about the data
    meta: dict
    # the actual data value
    value: Any

    def __repr__(self) -> str:
        return f"DataPoint(typename={self.typename}, meta={self.meta}, value={self.value})"


class DataModel(metaclass=abc.ABCMeta):
    """
    定义了数据被如何解析
    """
    # 模型的所属类型
    __typename__ = ""
    # 模型的标签定义，用于检索
    __tags__ = {}

    @property
    def typename(cls) -> str:
        return cls.__typename__

    @property
    def tags(cls) -> dict:
        return cls.__tags__

    @abc.abstractmethod
    def process(self, data: Any) -> List[DataPoint]:
        """
        输入任意类型的数据，返回处理后、符合当前数据流的数据点列表
        """
        raise NotImplementedError

    @abc.abstractmethod
    def post_process(self, data: List[DataPoint]) -> List[DataPoint]:
        """
        后处理，用户最终自己可以再解析一遍
        """
        return data


class DataModelRegistry(metaclass=abc.ABCMeta):
    """
    model集合，用于自动发现
    """
    def __init__(self):
        self.models : List[DataModel] = []

    def register(self, model: DataModel):
        self.models.append(model)

    def find_model(self, data: Any) -> DataModel:
        """
        输入数据，返回匹配的数据模型。需要实现，否则需要逐个匹配。
        """
        raise NotImplementedError

    def get_models(self) -> List[DataModel]:
        return self.models



class DataSink(metaclass=abc.ABCMeta):
    """
    Abstract base class for data sinks.
    """
    @abc.abstractmethod
    def write(self, data: List[DataPoint]) -> List[DataPoint]:
        raise NotImplementedError

    @abc.abstractmethod
    def finish(self, data: List[DataPoint]) -> List[DataPoint]:
        raise NotImplementedError


class DataSource(metaclass=abc.ABCMeta):
    """
    Abstract base class for data sources.
    """
    @abc.abstractmethod
    def add_sink(self, sink: DataSink):
        raise NotImplementedError

    @abc.abstractmethod
    def start(self):
        raise NotImplementedError


class DataLoader(DataSource, DataSink, metaclass=abc.ABCMeta):
    """
    数据加载类。
    可以每次输出一条，也可以批量输出多条数据。
    """
    def __init__(self):
        self.sinks: List[DataSink] = []
        self.model_registry: DataModelRegistry

    def set_model_registry(self, model_registry: DataModelRegistry):
        self.model_registry = model_registry

    def add_sink(self, sink: DataSink):
        self.sinks.append(sink)

    def start(self):
        pass

    def write(self, data: List[DataPoint]) -> List[DataPoint]:
        for sink in self.sinks:
            data = sink.write(data)
        return data

    def finish(self, data: List[DataPoint]) -> List[DataPoint]:
        for sink in self.sinks:
            data = sink.finish(data)
        return data
