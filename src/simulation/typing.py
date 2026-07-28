"""
打字模拟 — 拟人化键盘输入

核心：
- 可变按键间隔（高斯分布，不是均匀随机）
- 3-5% 概率故意打错再回退
- 标点符号后停顿更长
- 偶尔按键连击（模拟手抖）
- 不使用 page.fill()（它是瞬时设置的）
"""

import asyncio
import random
import string

import numpy as np
from loguru import logger
from playwright.async_api import ElementHandle, Page


class TypingSimulator:
    """打字模拟器"""

    def __init__(self, page: Page,
                 typo_probability: float = 0.04,
                 base_delay_ms: float = 80.0,
                 delay_variance_ms: float = 40.0):
        self.page = page
        self.typo_probability = typo_probability
        self.base_delay = base_delay_ms / 1000.0  # 转换为秒
        self.delay_std = delay_variance_ms / 1000.0

    async def type_text(self, element: ElementHandle, text: str,
                        clear_first: bool = True) -> None:
        """
        模拟人类输入文本

        Args:
            element: 输入框元素
            text: 要输入的文本
            clear_first: 是否先清空已有内容
        """
        try:
            # 先聚焦到元素
            await element.click()
            await asyncio.sleep(random.uniform(0.1, 0.3))

            if clear_first:
                # 选中所有内容再删除（模拟人类清空的动作）
                await self.page.keyboard.press("Control+a")
                await asyncio.sleep(0.1)
                await self.page.keyboard.press("Delete")
                await asyncio.sleep(random.uniform(0.1, 0.2))

            # 逐字符输入
            for i, char in enumerate(text):
                # 判断是否需要故意打错
                if (self._should_make_typo(char) and
                        i < len(text) - 1 and  # 最后一个字符不打错
                        char.isalpha()):  # 只对字母打错

                    await self._type_with_typo(char)
                else:
                    await self.page.keyboard.press(char)

                    # 计算按键间隔
                    delay = self._calculate_delay(char, i, text)
                    await asyncio.sleep(delay)

        except Exception as e:
            logger.warning(f"Typing simulation failed: {e}")
            # 降级：直接设置值
            await element.fill(text)

    async def type_slowly(self, element: ElementHandle, text: str) -> None:
        """更慢的打字模式（用于密码等需要谨慎输入的场景）"""
        original_base = self.base_delay
        original_std = self.delay_std

        self.base_delay = 150 / 1000.0  # 150ms
        self.delay_std = 50 / 1000.0

        try:
            await self.type_text(element, text)
        finally:
            self.base_delay = original_base
            self.delay_std = original_std

    async def _type_with_typo(self, correct_char: str) -> None:
        """
        模拟打错再修正
        """
        # 选择一个相近的错误字符（键盘上相邻的键）
        typo_char = self._get_typo_char(correct_char)

        # 输入错误字符
        await self.page.keyboard.press(typo_char)
        await asyncio.sleep(random.uniform(0.08, 0.25))

        # 回退
        await self.page.keyboard.press("Backspace")
        await asyncio.sleep(random.uniform(0.1, 0.3))

        # 输入正确字符
        await self.page.keyboard.press(correct_char)

    def _should_make_typo(self, char: str) -> bool:
        """判断是否制造 typo"""
        return random.random() < self.typo_probability

    def _get_typo_char(self, char: str) -> str:
        """
        获取一个相邻键盘键位作为错误字符
        """
        # 简化：随机选择一个字母
        if char.islower():
            return random.choice(string.ascii_lowercase)
        else:
            return random.choice(string.ascii_uppercase)

    def _calculate_delay(self, char: str, index: int, full_text: str) -> float:
        """
        计算按键间隔时间

        策略：
        - 基础间隔：高斯分布
        - 标点后停顿更长（思考下一句）
        - 空格后稍微停顿（确认单词）
        - 偶尔按键连击（手抖）
        """
        # 基础高斯分布
        delay = np.random.normal(self.base_delay, self.delay_std)

        # 边界检查（画江湖的上限是 4 倍平均延迟）
        max_delay = self.base_delay * 4
        # 先保护基础延迟下限,再叠加标点停顿。否则负高斯采样会抵消
        # 句尾 0.3-0.8 秒的额外停顿,造成特征测试偶发失败。
        delay = max(0.02, min(delay, max_delay))

        # 标点和格式字符的额外停顿
        if char in ".!?":
            # 句尾停顿（思考下一句）
            delay += random.uniform(0.3, 0.8)
        elif char == ",":
            # 逗号停顿
            delay += random.uniform(0.1, 0.3)
        elif char == " ":
            # 空格后确认单词
            delay += random.uniform(0.05, 0.15)
        elif char == "\n":
            # 换行停顿
            delay += random.uniform(0.2, 0.5)

        # 检查前一个字符是否是标点（如果是，当前字符需要更长思考时间）
        if index > 0 and full_text[index - 1] in ".!?":
            delay += random.uniform(0.2, 0.5)

        # 极少数情况：按键连击（手抖按了两次）
        if random.random() < 0.005:  # 0.5%
            delay += delay * 2  # 停顿更久

        return max(0.02, delay)  # 最小 20ms
