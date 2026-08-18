import pytest
from unittest.mock import MagicMock
from src.agents.applicator import ApplicatorAgent

class _Button:
    """Playwright button locator: `.first` is the locator itself."""

    def __init__(self, is_visible, on_click=None):
        self._visible = is_visible
        self._on_click = on_click

    @property
    def first(self):
        return self

    def is_visible(self):
        return self._visible()

    def click(self):
        if self._on_click:
            self._on_click()
        return None

class FakePage:
    """Scripted fake of the subset of the Playwright page API the modal loop uses."""

    def __init__(self, submit_visible=False, next_visible=False, review_visible=False, alert_visible=False, reveal_submit_on_next=False):
        self.submit_visible = submit_visible
        self.next_visible = next_visible
        self.review_visible = review_visible
        self.alert_visible = alert_visible
        self.reveal_submit_on_next = reveal_submit_on_next
        self.wait_count = 0

    def _click_next(self):
        self.next_visible = False
        if self.reveal_submit_on_next:
            self.submit_visible = True

    def get_by_role(self, role, name=None, exact=False):
        if name == "Submit application":
            return _Button(lambda: self.submit_visible)
        if name == "Next":
            return _Button(lambda: self.next_visible, on_click=self._click_next)
        if name == "Review":
            return _Button(lambda: self.review_visible, on_click=self._click_next)
        if role == "alert":
            return _Button(lambda: self.alert_visible)
        raise AssertionError(f"unexpected get_by_role({role}, {name})")

    def wait_for_load_state(self, state, timeout=None):
        self.wait_count += 1

    def screenshot(self, path=None):
        return MagicMock()

def make_agent():
    agent = ApplicatorAgent()
    agent._random_sleep = MagicMock()
    return agent

def test_modal_loop_submits_without_waiting_when_submit_visible():
    page = FakePage(submit_visible=True)
    agent = make_agent()
    wait_calls = []

    result = agent._modal_loop(page, lambda msg: wait_calls.append(msg))

    assert result is True
    assert wait_calls == []

def test_modal_loop_calls_wait_fn_on_form_error():
    page = FakePage(next_visible=True, alert_visible=True)
    wait_calls = []

    def wait_fn(msg):
        wait_calls.append(msg)
        page.submit_visible = True
        page.alert_visible = False

    agent = make_agent()
    result = agent._modal_loop(page, wait_fn)

    assert result is True
    assert len(wait_calls) == 1
    assert "filled the field" in wait_calls[0]

def test_modal_loop_resumes_without_waiting_when_no_error():
    page = FakePage(next_visible=True, alert_visible=False, reveal_submit_on_next=True)
    wait_calls = []

    def wait_fn(msg):
        wait_calls.append(msg)

    agent = make_agent()
    result = agent._modal_loop(page, wait_fn)

    assert result is True
    assert wait_calls == []

def test_modal_loop_returns_false_when_stuck():
    page = FakePage()
    agent = make_agent()
    wait_calls = []

    result = agent._modal_loop(page, lambda msg: wait_calls.append(msg))

    assert result is False
    assert wait_calls == []
