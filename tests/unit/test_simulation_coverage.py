from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from src.simulation.behavior import HumanSimulator
from src.simulation.mouse import MouseSimulator
from src.simulation.scroll import ScrollSimulator
from src.simulation.timing import (
    HumanActionType,
    get_optimal_delay,
    human_delay,
    randomize_session_timing,
    wait_human,
)


def fake_page() -> SimpleNamespace:
    return SimpleNamespace(
        viewport_size={"width": 1280, "height": 800},
        evaluate=AsyncMock(),
        wait_for_load_state=AsyncMock(),
        mouse=SimpleNamespace(move=AsyncMock(), click=AsyncMock()),
    )


@pytest.mark.asyncio
async def test_browse_and_view_job_exercise_optional_human_actions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = fake_page()
    human = HumanSimulator(page)
    human.scroll = SimpleNamespace(
        scroll_page_down=AsyncMock(),
        scroll_page_up=AsyncMock(),
        _smooth_scroll_by=AsyncMock(),
    )
    human.mouse = SimpleNamespace(random_movement=AsyncMock())
    monkeypatch.setattr("src.simulation.behavior.wait_human", AsyncMock())
    monkeypatch.setattr("src.simulation.behavior.asyncio.sleep", AsyncMock())
    monkeypatch.setattr("src.simulation.behavior.random.random", Mock(return_value=0.1))

    await human.browse_homepage(scroll_depth=1)
    await human.view_job_detail()

    assert human.scroll.scroll_page_down.await_count >= 2
    human.scroll.scroll_page_up.assert_awaited()
    human.mouse.random_movement.assert_awaited_once()
    page.evaluate.assert_awaited_with("window.scrollTo(0, 0)")


@pytest.mark.asyncio
async def test_click_fill_and_stability_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = fake_page()
    human = HumanSimulator(page)
    field = object()
    human.scroll = SimpleNamespace(scroll_to_element=AsyncMock())
    human.mouse = SimpleNamespace(click_element=AsyncMock())
    typing = SimpleNamespace(type_text=AsyncMock(), type_slowly=AsyncMock())
    human.typing = typing
    monkeypatch.setattr("src.simulation.behavior.wait_human", AsyncMock())

    await human.click_apply_button(field)
    await human.fill_form_field(field, "synthetic")
    await human.fill_form_field(field, "secret", is_password=True)
    await human.wait_for_page_stability()

    human.mouse.click_element.assert_awaited_once_with(field)
    typing.type_text.assert_awaited_once()
    typing.type_slowly.assert_awaited_once()
    page.wait_for_load_state.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "action",
    ["mouse_wander", "small_scroll", "pause", "tab_away"],
)
async def test_random_distractor_actions(
    monkeypatch: pytest.MonkeyPatch,
    action: str,
) -> None:
    human = HumanSimulator(fake_page())
    human.mouse = SimpleNamespace(random_movement=AsyncMock())
    human.scroll = SimpleNamespace(_smooth_scroll_by=AsyncMock())
    monkeypatch.setattr(
        "src.simulation.behavior.random.choices",
        Mock(return_value=[action]),
    )
    monkeypatch.setattr("src.simulation.behavior.wait_human", AsyncMock())

    await human.random_distractor()


@pytest.mark.asyncio
async def test_scroll_success_fallback_and_page_directions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = fake_page()
    scroll = ScrollSimulator(page)
    element = SimpleNamespace(scroll_into_view_if_needed=AsyncMock())
    monkeypatch.setattr("src.simulation.scroll.asyncio.sleep", AsyncMock())

    await scroll.scroll_to_element(element)
    await scroll.scroll_page_down()
    await scroll.scroll_page_up()

    page.evaluate.side_effect = RuntimeError("synthetic")
    await scroll.scroll_to_element(element)
    element.scroll_into_view_if_needed.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "action",
    ["down", "up", "pause", "small_down", "small_up"],
)
async def test_random_scroll_actions(
    monkeypatch: pytest.MonkeyPatch,
    action: str,
) -> None:
    scroll = ScrollSimulator(fake_page())
    scroll.scroll_page_down = AsyncMock()
    scroll.scroll_page_up = AsyncMock()
    scroll._smooth_scroll_by = AsyncMock()
    monkeypatch.setattr("src.simulation.scroll.asyncio.sleep", AsyncMock())
    monkeypatch.setattr(
        "src.simulation.scroll.random.choices",
        Mock(return_value=[action]),
    )

    await scroll.random_scroll_behavior()


@pytest.mark.asyncio
async def test_mouse_move_click_and_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = fake_page()
    mouse = MouseSimulator(page, bezier_points=3)
    element = SimpleNamespace(
        scroll_into_view_if_needed=AsyncMock(),
        bounding_box=AsyncMock(
            return_value={"x": 10, "y": 20, "width": 100, "height": 40}
        ),
        hover=AsyncMock(),
        click=AsyncMock(),
    )
    monkeypatch.setattr("src.simulation.mouse.asyncio.sleep", AsyncMock())
    monkeypatch.setattr("src.simulation.mouse.random.random", Mock(return_value=1.0))

    await mouse.move_to((50, 60))
    await mouse.move_to_element(element, hover_time=0)
    await mouse.click_element(element, move_first=False)
    await mouse.random_movement()

    assert page.mouse.move.await_count >= 3
    page.mouse.click.assert_awaited_once()

    element.bounding_box.side_effect = RuntimeError("detached")
    await mouse.move_to_element(element)
    element.hover.assert_awaited()


@pytest.mark.asyncio
async def test_timing_helpers_cover_overrides_and_wait(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("src.simulation.timing.np.random.normal", Mock(return_value=-1))
    monkeypatch.setattr("src.simulation.timing.random.random", Mock(return_value=1.0))
    assert human_delay(HumanActionType.CLICK, mean_override=2, std_override=0) == 0.05

    sleep = AsyncMock()
    monkeypatch.setattr("src.simulation.timing.asyncio.sleep", sleep)
    await wait_human(HumanActionType.CLICK)
    sleep.assert_awaited_once()

    monkeypatch.setattr("src.simulation.timing.random.random", Mock(return_value=0.01))
    monkeypatch.setattr("src.simulation.timing.random.uniform", Mock(return_value=300))
    assert randomize_session_timing(2) == [900]


def test_optimal_delay_uses_peak_and_non_peak_ranges(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uniform = Mock(side_effect=lambda low, _high: low)
    monkeypatch.setattr("src.simulation.timing.random.uniform", uniform)
    monkeypatch.setattr("src.simulation.timing.is_peak_hour", Mock(return_value=True))
    assert get_optimal_delay() == 240
    monkeypatch.setattr("src.simulation.timing.is_peak_hour", Mock(return_value=False))
    assert get_optimal_delay() == 180
