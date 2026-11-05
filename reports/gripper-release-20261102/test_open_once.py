import importlib.util
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location("gripper_open_probe", Path(__file__).with_name("open_once.py"))
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class FakeController:
    def __init__(self, fail_at=None):
        self.calls = []
        self.fail_at = fail_at
    def SetToolDO(self, *args):
        self.calls.append(args)
        return 14 if len(self.calls) == self.fail_at else 0


def test_one_open_no_close_and_both_off():
    fake = FakeController()
    waits = []
    probe.pulse_open_once(fake, [], sleep=waits.append)
    assert fake.calls == [(0,0,0,0),(1,0,0,0),(1,1,0,0),(0,0,0,0),(1,0,0,0)]
    assert waits == [.1, .3]


def test_initial_off_failure_prevents_on():
    fake = FakeController(1)
    with pytest.raises(RuntimeError):
        probe.pulse_open_once(fake, [], sleep=lambda _: None)
    assert not any(c[1] == 1 for c in fake.calls)
    assert fake.calls == [(0,0,0,0),(1,0,0,0)]


def test_on_failure_still_turns_both_off_without_on_retry():
    fake = FakeController(3)
    with pytest.raises(RuntimeError):
        probe.pulse_open_once(fake, [], sleep=lambda _: None)
    assert fake.calls[-2:] == [(0,0,0,0),(1,0,0,0)]
    assert sum(c[1] == 1 for c in fake.calls) == 1


def test_one_off_failure_still_attempts_other_off():
    fake = FakeController(4)
    with pytest.raises(RuntimeError, match="OFF not confirmed"):
        probe.pulse_open_once(fake, [], sleep=lambda _: None)
    assert fake.calls[-1] == (1,0,0,0)


@pytest.mark.parametrize("channel", [0, 1])
def test_selected_channel_only_and_always_idle_afterward(channel):
    fake = FakeController()
    probe.pulse_channel_once(fake, channel, [], sleep=lambda _: None)
    assert [c for c in fake.calls if c[1] == 1] == [(channel,1,0,0)]
    assert fake.calls[-2:] == [(0,0,0,0),(1,0,0,0)]


def test_invalid_channel_cannot_write_any_output():
    fake = FakeController()
    with pytest.raises(ValueError):
        probe.pulse_channel_once(fake, 2, [], sleep=lambda _: None)
    assert fake.calls == []
