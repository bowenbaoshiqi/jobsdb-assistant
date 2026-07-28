"""
特征化测试: simulation/mouse.py + typing.py

锁定行为模拟的数学属性:Bezier 路径(连续/有界/非直线)、打字延迟分布。
用 mock page 构造 simulator,只测纯计算方法,不起浏览器。
"""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.simulation.mouse import MouseSimulator
from src.simulation.typing import TypingSimulator


def make_mouse():
    """构造 MouseSimulator(mock page),只用于测纯计算方法"""
    return MouseSimulator(page=MagicMock(), bezier_points=25)


def make_typing():
    return TypingSimulator(page=MagicMock())


# ═══════════════════════════════════════════════════════
#  Bezier 路径属性
# ═══════════════════════════════════════════════════════

class TestBezierPathProperties:
    def test_path_starts_at_start_point(self):
        """路径起点 = start"""
        mouse = make_mouse()
        path = mouse._generate_bezier_path((0, 0), (100, 100), num_points=25)
        assert path[0] == pytest.approx((0, 0), abs=0.01)

    def test_path_ends_at_end_point(self):
        """路径终点 = end"""
        mouse = make_mouse()
        path = mouse._generate_bezier_path((0, 0), (100, 100), num_points=25)
        assert path[-1] == pytest.approx((100, 100), abs=0.01)

    def test_path_has_requested_number_of_points(self):
        """点数 = num_points"""
        mouse = make_mouse()
        path = mouse._generate_bezier_path((0, 0), (100, 100), num_points=30)
        assert len(path) == 30

    def test_path_is_continuous_no_large_gaps(self):
        """相邻点距离有界(连续,无突变)"""
        mouse = make_mouse()
        path = mouse._generate_bezier_path((100, 100), (500, 300), num_points=25)
        for i in range(1, len(path)):
            dx = path[i][0] - path[i-1][0]
            dy = path[i][1] - path[i-1][1]
            gap = np.sqrt(dx**2 + dy**2)
            # 总距离 ~400,25点,平均 ~16,最大不应超 50
            assert gap < 50, f"点 {i} 与 {i-1} 间距 {gap} 过大"

    def test_path_bounded_within_extended_bbox(self):
        """路径点不超出起点/终点的合理扩展范围(控制点偏移有界)"""
        mouse = make_mouse()
        start, end = (100, 100), (500, 300)
        path = mouse._generate_bezier_path(start, end, num_points=25)
        # 控制点偏移 ≤ distance*0.35,过冲 ≤ 0.1*distance
        # 总距离 ~447,扩展范围 ~447*0.45 ≈ 200
        for x, y in path:
            assert 100 - 200 < x < 500 + 200
            assert 100 - 200 < y < 300 + 200

    def test_path_not_straight_line(self):
        """路径通常不是直线(有弧度)— 多次采样验证"""
        mouse = make_mouse()
        has_curve = False
        for _ in range(20):  # 20 次采样
            path = mouse._generate_bezier_path((0, 0), (100, 100), num_points=25)
            # 检查中点是否偏离直线 y=x
            mid = path[12]
            if abs(mid[0] - mid[1]) > 2:  # 偏离直线 > 2px
                has_curve = True
                break
        assert has_curve, "20次采样路径全是直线,弧度逻辑失效"


# ═══════════════════════════════════════════════════════
#  cubic_bezier 纯函数
# ═══════════════════════════════════════════════════════

class TestCubicBezier:
    def test_t_zero_returns_p0(self):
        """t=0 返回起点"""
        assert MouseSimulator._cubic_bezier(0, (0, 0), (1, 1), (2, 2), (3, 3)) == pytest.approx((0, 0))  # noqa: E501

    def test_t_one_returns_p3(self):
        """t=1 返回终点"""
        assert MouseSimulator._cubic_bezier(1, (0, 0), (1, 1), (2, 2), (3, 3)) == pytest.approx((3, 3))  # noqa: E501

    def test_t_half_midpoint(self):
        """t=0.5 的标准值(四点共线时在直线上)"""
        result = MouseSimulator._cubic_bezier(0.5, (0, 0), (1, 1), (2, 2), (3, 3))
        # 共线时,贝塞尔点也在直线上
        assert result[0] == pytest.approx(result[1], abs=0.01)


# ═══════════════════════════════════════════════════════
#  Typing 延迟分布
# ═══════════════════════════════════════════════════════

class TestTypingDelay:
    def test_delay_within_reasonable_range(self):
        """延迟在合理范围(base_delay=0.08s ± variance)"""
        typing = make_typing()
        text = "abcdefghijklmnopqrstuvwxyz"
        delays = [typing._calculate_delay(text[i], i, text) for i in range(len(text))]
        # base_delay=0.08s, 延迟应在 0.01-1.5s 之间(标点会加 0.3-0.8,但本例无标点)
        for d in delays:
            assert 0.01 < d < 1.0, f"延迟 {d} 超出合理范围"

    def test_delays_vary_not_constant(self):
        """延迟有变化(非恒定)"""
        typing = make_typing()
        text = "abcdefghijklmnopqrstuvwxyz"
        delays = [typing._calculate_delay(text[i], i, text) for i in range(len(text))]
        assert len({round(d, 3) for d in delays}) > 5  # 至少 5 个不同值

    def test_delay_for_punctuation_has_extra_pause(self):
        """标点字符('.!?,')的延迟含额外停顿(>base_delay)"""
        typing = make_typing()
        # 句号字符:base + uniform(0.3,0.8),最小也 > 0.08
        text = "a.b"
        delays = [typing._calculate_delay(".", 1, text) for _ in range(20)]
        for d in delays:
            # 句号延迟 = base(~0.08) + (0.3~0.8) > 0.3
            assert d > 0.3, f"句号延迟 {d} 未含额外停顿"

    def test_punctuation_pause_survives_negative_base_sample(self):
        """基础高斯采样为负时,句尾仍保留完整额外停顿"""
        typing = make_typing()
        with (
            patch("src.simulation.typing.np.random.normal", return_value=-1.0),
            patch(
                "src.simulation.typing.random.uniform",
                side_effect=lambda lower, _upper: lower,
            ),
            patch("src.simulation.typing.random.random", return_value=1.0),
        ):
            delay = typing._calculate_delay(".", 1, "a.b")

        assert delay > 0.3

    def test_delay_min_floor_20ms(self):
        """延迟最小 20ms(下限保护)"""
        typing = make_typing()
        text = "abc"
        delays = [typing._calculate_delay("a", 0, text) for _ in range(50)]
        assert all(d >= 0.02 for d in delays)

    def test_typo_decision_is_boolean(self):
        """_should_make_typo 返回 bool"""
        typing = make_typing()
        results = [typing._should_make_typo("a") for _ in range(20)]
        assert all(isinstance(r, bool) for r in results)

    def test_typo_char_is_different_or_same(self):
        """_get_typo_char 返回单个字符"""
        typing = make_typing()
        typo = typing._get_typo_char("a")
        assert isinstance(typo, str)
        assert len(typo) == 1
