#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试 DuckDBQuantDatabase 实现
"""
import unittest
import shutil
import time
from datetime import datetime
from pathlib import Path

import duckdb

from mos.data.database_duckdb import DuckDBQuantDatabase
from mos.core.types import Bar, BarType, Exchange, AdjustFactor, InstrumentInfo, InstrumentType
from datetime import date


class TestDuckDBQuantDatabase(unittest.TestCase):
    """测试 DuckDBQuantDatabase 类"""

    def setUp(self):
        """测试前的准备工作"""
        self.test_db_root = Path("test_duckdb_data")
        if self.test_db_root.exists():
            shutil.rmtree(self.test_db_root)
        self.db = DuckDBQuantDatabase(db_root_path=self.test_db_root)

    def tearDown(self):
        """测试后的清理工作"""
        if self.test_db_root.exists():
            shutil.rmtree(self.test_db_root)

    def _create_bar(self, symbol: str, exchange: str, time: datetime,
                    open: float, high: float, low: float, close: float,
                    volume: int, amount: float = None, pre_close: float = None) -> Bar:
        """辅助方法：创建 Bar 对象"""
        return Bar(
            symbol=symbol,
            exchange=exchange,
            time=time,
            open=open,
            high=high,
            low=low,
            close=close,
            volume=volume,
            amount=amount,
            pre_close=pre_close if pre_close is not None else close
        )

    def test_save_and_query_single_symbol_minute_bar(self):
        """测试单只股票分钟级K线的保存和查询"""
        # 准备数据：2025年1月1日的1分钟K线
        bars = [
            self._create_bar("600000.SH", "SH", datetime(2025, 1, 1, 9, 30, i), 10.0 + i*0.1, 10.5, 9.9, 10.2 + i*0.05, 1000*i, 10000*i)
            for i in range(10)
        ]

        # 保存
        self.db.save_bar(bars, BarType.MINUTE)

        # 查询
        result = self.db.query_bar("600000.SH", datetime(2025, 1, 1, 9, 30), datetime(2025, 1, 1, 10, 30), BarType.MINUTE)

        # 验证
        self.assertEqual(len(result), 10)
        self.assertEqual(result[0].symbol, "600000.SH")
        self.assertEqual(result[0].exchange, "SH")
        # 第10个bar (i=9): close = 10.2 + 9*0.05 = 10.65
        self.assertAlmostEqual(result[-1].close, 10.65, places=5)

    def test_save_and_query_multi_symbol_minute_bar(self):
        """测试多只股票分钟级K线的保存和查询"""
        bars = [
            self._create_bar("600000.SH", "SH", datetime(2025, 1, 1, 9, 30, i), 10.0, 10.5, 9.9, 10.2, 1000, 10000)
            for i in range(5)
        ] + [
            self._create_bar("000001.SZ", "SZ", datetime(2025, 1, 1, 9, 30, i), 20.0, 20.5, 19.9, 20.2, 2000, 20000)
            for i in range(5)
        ]

        # 保存
        self.db.save_bar(bars, BarType.MINUTE)

        # 查询 SH
        result_sh = self.db.query_bar("600000.SH", datetime(2025, 1, 1, 9, 30), datetime(2025, 1, 1, 10, 30), BarType.MINUTE)
        self.assertEqual(len(result_sh), 5)
        self.assertEqual(result_sh[0].symbol, "600000.SH")

        # 查询 SZ
        result_sz = self.db.query_bar("000001.SZ", datetime(2025, 1, 1, 9, 30), datetime(2025, 1, 1, 10, 30), BarType.MINUTE)
        self.assertEqual(len(result_sz), 5)
        self.assertEqual(result_sz[0].symbol, "000001.SZ")

    def test_save_and_query_cross_year_minute_bar(self):
        """测试跨年度分钟级K线的保存和查询（分钟级K线按年份分文件）"""
        # 准备跨年数据：2024年12月31日和2025年1月1日
        bars = [
            self._create_bar("600000.SH", "SH", datetime(2024, 12, 31, 14, 30, i), 10.0, 10.5, 9.9, 10.2, 1000, 10000)
            for i in range(5)
        ] + [
            self._create_bar("600000.SH", "SH", datetime(2025, 1, 1, 9, 30, i), 10.0, 10.5, 9.9, 10.2, 1000, 10000)
            for i in range(5)
        ]

        # 保存
        self.db.save_bar(bars, BarType.MINUTE)

        # 查询2024年
        result_2024 = self.db.query_bar("600000.SH", datetime(2024, 12, 31, 14, 0), datetime(2024, 12, 31, 15, 0), BarType.MINUTE)
        self.assertEqual(len(result_2024), 5)

        # 查询2025年
        result_2025 = self.db.query_bar("600000.SH", datetime(2025, 1, 1, 9, 0), datetime(2025, 1, 1, 10, 0), BarType.MINUTE)
        self.assertEqual(len(result_2025), 5)

        # 跨年查询
        result_all = self.db.query_bar("600000.SH", datetime(2024, 12, 31, 14, 0), datetime(2025, 1, 1, 10, 0), BarType.MINUTE)
        self.assertEqual(len(result_all), 10)

    def test_save_and_query_day_bar(self):
        """测试日线K线的保存和查询（日线为单个文件）"""
        bars = [
            self._create_bar("600000.SH", "SH", datetime(2025, 1, 1), 10.0, 10.5, 9.9, 10.2, 1000000, 10000000),
            self._create_bar("600000.SH", "SH", datetime(2025, 1, 2), 10.2, 10.7, 10.0, 10.5, 1100000, 11000000),
            self._create_bar("600000.SH", "SH", datetime(2025, 1, 3), 10.5, 10.8, 10.3, 10.6, 1200000, 12000000),
        ]

        # 保存
        self.db.save_bar(bars, BarType.DAY)

        # 查询
        result = self.db.query_bar("600000.SH", datetime(2025, 1, 1), datetime(2025, 1, 3), BarType.DAY)

        # 验证
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0].time, datetime(2025, 1, 1))
        self.assertEqual(result[1].close, 10.5)
        self.assertEqual(result[2].volume, 1200000)

    def test_save_and_query_week_bar(self):
        """测试周线K线的保存和查询"""
        bars = [
            self._create_bar("600000.SH", "SH", datetime(2025, 1, 6), 10.0, 10.5, 9.9, 10.2, 5000000, 50000000),
            self._create_bar("600000.SH", "SH", datetime(2025, 1, 13), 10.2, 10.7, 10.0, 10.5, 5500000, 55000000),
        ]
        self.db.save_bar(bars, BarType.WEEK)
        result = self.db.query_bar("600000.SH", datetime(2025, 1, 1), datetime(2025, 1, 31), BarType.WEEK)
        self.assertEqual(len(result), 2)

    def test_save_and_query_cross_year_day_bar(self):
        """测试跨年度日线K线的保存和查询"""
        bars = [
            self._create_bar("600000.SH", "SH", datetime(2024, 12, 31), 10.0, 10.5, 9.9, 10.2, 1000000, 10000000),
            self._create_bar("600000.SH", "SH", datetime(2025, 1, 2), 10.2, 10.7, 10.0, 10.5, 1100000, 11000000),
            self._create_bar("600000.SH", "SH", datetime(2025, 1, 3), 10.5, 10.8, 10.3, 10.6, 1200000, 12000000),
        ]

        # 保存
        self.db.save_bar(bars, BarType.DAY)

        # 跨年查询
        result = self.db.query_bar("600000.SH", datetime(2024, 12, 31), datetime(2025, 1, 3), BarType.DAY)
        self.assertEqual(len(result), 3)

    def test_save_and_query_5min_bar(self):
        """测试5分钟K线的保存和查询"""
        bars = [
            self._create_bar("600000.SH", "SH", datetime(2025, 1, 1, 9, 30), 10.0, 10.5, 9.9, 10.2, 10000, 100000),
            self._create_bar("600000.SH", "SH", datetime(2025, 1, 1, 9, 35), 10.2, 10.6, 10.0, 10.3, 11000, 110000),
        ]

        # 保存
        self.db.save_bar(bars, BarType.FIVE_MINUTE)

        # 查询
        result = self.db.query_bar("600000.SH", datetime(2025, 1, 1, 9, 30), datetime(2025, 1, 1, 10, 0), BarType.FIVE_MINUTE)

        # 验证
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].time, datetime(2025, 1, 1, 9, 30))

    def test_query_bar_as_dataframe(self):
        """测试query_bar返回DataFrame格式"""
        bars = [
            self._create_bar("600000.SH", "SH", datetime(2025, 1, 1), 10.0, 10.5, 9.9, 10.2, 1000000, 10000000),
            self._create_bar("600000.SH", "SH", datetime(2025, 1, 2), 10.2, 10.7, 10.0, 10.5, 1100000, 11000000),
        ]
        self.db.save_bar(bars, BarType.DAY)

        # 测试返回DataFrame
        df = self.db.query_bar("600000.SH", datetime(2025, 1, 1), datetime(2025, 1, 3), BarType.DAY, as_dataframe=True)
        self.assertEqual(len(df), 2)
        self.assertIn('symbol', df.columns)
        self.assertIn('close', df.columns)

        # 测试返回List[Bar]
        bars_result = self.db.query_bar("600000.SH", datetime(2025, 1, 1), datetime(2025, 1, 3), BarType.DAY, as_dataframe=False)
        self.assertEqual(len(bars_result), 2)
        self.assertIsInstance(bars_result[0], Bar)

    def test_query_nonexistent_data(self):
        """测试查询不存在的数据"""
        # 查询一个从未保存过的 symbol
        result = self.db.query_bar("999999.SH", datetime(2025, 1, 1), datetime(2025, 1, 3), BarType.DAY)
        self.assertEqual(len(result), 0)

    def test_query_out_of_range(self):
        """测试查询超出保存范围的数据"""
        bars = [
            self._create_bar("600000.SH", "SH", datetime(2025, 1, 1), 10.0, 10.5, 9.9, 10.2, 1000000, 10000000),
        ]
        self.db.save_bar(bars, BarType.DAY)

        # 查询2024年的数据（应该为空）
        result = self.db.query_bar("600000.SH", datetime(2024, 1, 1), datetime(2024, 12, 31), BarType.DAY)
        self.assertEqual(len(result), 0)

    def test_get_db_file_path_minute(self):
        """测试分钟级K线的数据库文件路径生成"""
        paths = self.db._get_bar_db_path(
            BarType.MINUTE, "600000.SH",
            datetime(2024, 1, 1), datetime(2025, 12, 31)
        )
        # 2024和2025两年
        self.assertEqual(len(paths), 2, f"Expected 2 paths but got {len(paths)}: {paths}")
        self.assertTrue("2024.db" in paths[0])
        self.assertTrue("2025.db" in paths[1])

    def test_get_db_file_path_day(self):
        """测试日线K线的数据库文件路径生成"""
        paths = self.db._get_bar_db_path(
            BarType.DAY, "600000.SH",
            datetime(2024, 1, 1), datetime(2025, 12, 31)
        )
        # 日线只有单个文件
        self.assertEqual(len(paths), 1)
        self.assertTrue("1d.db" in paths[0])

    def test_save_and_query_adjust_factor(self):
        """测试复权因子的保存和查询"""
        factors = [
            AdjustFactor(symbol="600000.SH", date=datetime(2025, 1, 1).date(), factor=1.0),
            AdjustFactor(symbol="600000.SH", date=datetime(2025, 1, 2).date(), factor=1.05),
            AdjustFactor(symbol="600000.SH", date=datetime(2025, 1, 3).date(), factor=1.08),
        ]
        self.db.save_adjust_factor(factors)

        # 查询复权因子
        result = self.db.query_adjust_factor("600000.SH")
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0].factor, 1.0)
        self.assertEqual(result[-1].factor, 1.08)

    def test_resource_management(self):
        """测试资源管理接口（connect/close/with语句）"""
        # 测试 connect 和 close
        self.db.connect()
        self.assertTrue(self.db.is_connected())
        self.db.close()
        self.assertFalse(self.db.is_connected())

        # 测试 with 语句
        with DuckDBQuantDatabase(self.test_db_root) as db:
            bars = [self._create_bar("600000.SH", "SH", datetime(2025, 1, 1), 10.0, 10.5, 9.9, 10.2, 1000000, 10000000)]
            db.save_bar(bars, BarType.DAY)
            result = db.query_bar("600000.SH", datetime(2025, 1, 1), datetime(2025, 1, 3), BarType.DAY)
            self.assertEqual(len(result), 1)

    def test_query_tick_unimplemented(self):
        """测试Tick数据查询（未实现）"""
        result = self.db.query_tick("600000.SH", datetime(2025, 1, 1), datetime(2025, 1, 3))
        self.assertEqual(result, [])

        df = self.db.query_tick("600000.SH", datetime(2025, 1, 1), datetime(2025, 1, 3), as_dataframe=True)
        self.assertTrue(df.empty)

    def test_query_bars_batch(self):
        """测试批量查询多个股票的K线数据"""
        bars = [
            self._create_bar("600000.SH", "SH", datetime(2025, 1, 1), 10.0, 10.5, 9.9, 10.2, 1000000, 10000000),
            self._create_bar("600000.SH", "SH", datetime(2025, 1, 2), 10.2, 10.7, 10.0, 10.5, 1100000, 11000000),
            self._create_bar("000001.SZ", "SZ", datetime(2025, 1, 1), 20.0, 20.5, 19.9, 20.2, 2000000, 20000000),
            self._create_bar("000001.SZ", "SZ", datetime(2025, 1, 2), 20.2, 20.7, 20.0, 20.5, 2100000, 21000000),
        ]
        self.db.save_bar(bars, BarType.DAY)

        # 批量查询
        symbols = ["600000.SH", "000001.SZ"]
        results = self.db.query_bars(symbols, datetime(2025, 1, 1), datetime(2025, 1, 3), BarType.DAY)

        # 验证结果
        self.assertEqual(len(results), 2)
        self.assertIn("600000.SH", results)
        self.assertIn("000001.SZ", results)
        self.assertEqual(len(results["600000.SH"]), 2)
        self.assertEqual(len(results["000001.SZ"]), 2)

        # 验证数据正确性
        self.assertEqual(results["600000.SH"][0].close, 10.2)
        self.assertEqual(results["600000.SH"][1].close, 10.5)
        self.assertEqual(results["000001.SZ"][0].close, 20.2)
        self.assertEqual(results["000001.SZ"][1].close, 20.5)

    def test_query_bars_as_dataframe(self):
        """测试批量查询返回DataFrame格式"""
        bars = [
            self._create_bar("600000.SH", "SH", datetime(2025, 1, 1), 10.0, 10.5, 9.9, 10.2, 1000000, 10000000),
            self._create_bar("000001.SZ", "SZ", datetime(2025, 1, 1), 20.0, 20.5, 19.9, 20.2, 2000000, 20000000),
        ]
        self.db.save_bar(bars, BarType.DAY)

        # 批量查询返回DataFrame
        symbols = ["600000.SH", "000001.SZ"]
        results = self.db.query_bars(symbols, datetime(2025, 1, 1), datetime(2025, 1, 3), BarType.DAY, as_dataframe=True)

        # 验证结果
        self.assertEqual(len(results), 2)
        self.assertIn("600000.SH", results)
        self.assertIn("000001.SZ", results)
        self.assertEqual(len(results["600000.SH"]), 1)
        self.assertEqual(len(results["000001.SZ"]), 1)
        self.assertTrue(hasattr(results["600000.SH"], 'columns'))

    def test_query_bars_with_nonexistent_symbol(self):
        """测试批量查询包含不存在的股票"""
        bars = [
            self._create_bar("600000.SH", "SH", datetime(2025, 1, 1), 10.0, 10.5, 9.9, 10.2, 1000000, 10000000),
        ]
        self.db.save_bar(bars, BarType.DAY)

        # 批量查询包含不存在的股票
        symbols = ["600000.SH", "999999.SH"]
        results = self.db.query_bars(symbols, datetime(2025, 1, 1), datetime(2025, 1, 3), BarType.DAY)

        # 验证结果
        self.assertEqual(len(results), 2)
        self.assertEqual(len(results["600000.SH"]), 1)
        self.assertEqual(len(results["999999.SH"]), 0)

    def test_save_and_query_instrument_info(self):
        """测试金融工具信息的保存和查询"""
        # 准备测试数据
        test_info_list = [
            InstrumentInfo(
                symbol="600000.SH",
                exchange=Exchange.SH,
                type=InstrumentType.STOCK,
                name="浦发银行",
                list_date=date(1999, 11, 10),
                status="L",
                price_tick=1,
                delist_date=None,
                industry="银行",
                area="上海",
                is_t0=False
            ),
            InstrumentInfo(
                symbol="000001.SZ",
                exchange=Exchange.SZ,
                type=InstrumentType.STOCK,
                name="平安银行",
                list_date=date(1991, 4, 3),
                status="L",
                price_tick=1,
                delist_date=None,
                industry="银行",
                area="广东",
                is_t0=False
            ),
            InstrumentInfo(
                symbol="510300.SH",
                exchange=Exchange.SH,
                type=InstrumentType.ETF,
                name="沪深300ETF",
                list_date=date(2012, 5, 28),
                status="L",
                price_tick=1,
                delist_date=None,
                industry="",
                area="",
                is_t0=False
            )
        ]

        # 保存
        self.db.save_instrument_info(test_info_list)

        # 查询所有信息
        all_info = self.db.query_instrument_info()
        self.assertEqual(len(all_info), 3)

        # 查询单个 symbol
        query1 = InstrumentInfo(
            symbol="600000.SH",
            exchange=Exchange.SH,
            type=InstrumentType.STOCK,
            name="",
            list_date=date.today(),
            status="",
            price_tick=1
        )
        result1 = self.db.query_instrument_info(query1)
        self.assertEqual(len(result1), 1)
        self.assertEqual(result1[0].symbol, "600000.SH")
        self.assertEqual(result1[0].name, "浦发银行")

        # 按交易所查询
        query2 = InstrumentInfo(
            symbol="",
            exchange=Exchange.SZ,
            type=InstrumentType.STOCK,
            name="",
            list_date=date.today(),
            status="",
            price_tick=1
        )
        result2 = self.db.query_instrument_info(query2)
        self.assertEqual(len(result2), 1)
        self.assertEqual(result2[0].symbol, "000001.SZ")

        # 按类型查询
        query3 = InstrumentInfo(
            symbol="",
            exchange=Exchange.SH,
            type=InstrumentType.ETF,
            name="",
            list_date=date.today(),
            status="",
            price_tick=1
        )
        result3 = self.db.query_instrument_info(query3)
        self.assertEqual(len(result3), 1)
        self.assertEqual(result3[0].symbol, "510300.SH")

    def test_save_empty_instrument_info(self):
        """测试保存空的金融工具信息列表"""
        self.db.save_instrument_info([])

        # 不应该有任何错误，查询应该返回空列表
        result = self.db.query_instrument_info()
        self.assertEqual(len(result), 0)

    def test_query_nonexistent_instrument_info(self):
        """测试查询不存在的金融工具信息"""
        query = InstrumentInfo(
            symbol="999999.SH",
            exchange=Exchange.SH,
            type=InstrumentType.STOCK,
            name="",
            list_date=date.today(),
            status="",
            price_tick=1
        )
        result = self.db.query_instrument_info(query)
        self.assertEqual(len(result), 0)


if __name__ == "__main__":
    unittest.main()


def generate_performance_test(num_records=10000):
    """
    生成性能测试数据

    Args:
        num_records: 生成的数据条数

    Returns:
        生成的Bar列表
    """
    bars = []
    for i in range(num_records):
        # 只生成1月3日内的数据，简化测试
        day = 1 + (i % 3)
        hour = (i // 3) % 24
        minute = (i // (3 * 24)) % 60
        bar = Bar(
            symbol="600000.SH",
            exchange="SH",
            time=datetime(2025, 1, day, hour, minute),
            open=10.0 + i * 0.01,
            high=10.5 + i * 0.01,
            low=9.5 + i * 0.01,
            close=10.2 + i * 0.01,
            pre_close=10.1 + i * 0.01,
            volume=1000 * (i + 1),
            amount=10000 * (i + 1),
        )
        bars.append(bar)
    return bars


class TestPerformance(unittest.TestCase):
    """性能测试"""

    def setUp(self):
        """测试前的准备工作"""
        self.test_db_root = Path("test_performance_duckdb")
        if self.test_db_root.exists():
            shutil.rmtree(self.test_db_root)
        self.db = DuckDBQuantDatabase(db_root_path=self.test_db_root)

    def tearDown(self):
        """测试后的清理工作"""
        if self.test_db_root.exists():
            shutil.rmtree(self.test_db_root)

    def test_performance_small_dataset(self):
        """测试小数据集（1000条）"""

        bars = generate_performance_test(1000)

        start = time.time()
        self.db.save_bar(bars, BarType.DAY)
        elapsed = time.time() - start

        print(f"\n[性能测试] 小数据集（1000条）: {elapsed:.3f}s")
        self.assertLess(elapsed, 5.0)

        # 验证数据已写入（不检查数量，因为有重复时间戳）
        result = self.db.query_bar("600000.SH", datetime(2025, 1, 1), datetime(2025, 1, 3), BarType.DAY)
        self.assertGreater(len(result), 0)

    def test_performance_medium_dataset(self):
        """测试中等数据集（10000条）"""

        bars = generate_performance_test(10000)

        start = time.time()
        self.db.save_bar(bars, BarType.DAY)
        elapsed = time.time() - start

        print(f"\n[性能测试] 中等数据集（10000条）: {elapsed:.3f}s")
        self.assertLess(elapsed, 10.0)

        # 验证数据已写入（不检查数量，因为有重复时间戳）
        result = self.db.query_bar("600000.SH", datetime(2025, 1, 1), datetime(2025, 1, 3), BarType.DAY)
        self.assertGreater(len(result), 0)

    def test_performance_large_dataset(self):
        """测试大数据集（100000条） - 已禁用，避免耗时太长"""
        # 禁用大数据集测试，避免测试运行时间太长
        self.skipTest("大数据集测试已禁用")

        # bars = generate_performance_test(100000)
        #
        # start = time.time()
        # self.db.save_bar(bars, BarType.DAY)
        # elapsed = time.time() - start
        #
        # print(f"\n[性能测试] 大数据集（100000条）: {elapsed:.3f}s")
        # self.assertLess(elapsed, 60.0)
        #
        # result = self.db.query_bar("600000.SH", datetime(2025, 1, 1), datetime(2025, 1, 3), BarType.DAY)
        # self.assertEqual(len(result), 100000)

    def test_index_creation(self):
        """测试索引创建"""
        bars = generate_performance_test(1000)
        self.db.save_bar(bars, BarType.DAY)

        db_path = self.test_db_root / "bars" / "1d.db"
        conn = duckdb.connect(database=str(db_path))
        try:
            indexes = conn.execute("SELECT index_name FROM duckdb_indexes() WHERE table_name = 'bar_1d'").fetchall()
            print(f"\n[索引测试] 索引列表: {[idx[0] for idx in indexes]}")
            self.assertTrue(len(indexes) > 0, "应该至少有一个索引")
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
