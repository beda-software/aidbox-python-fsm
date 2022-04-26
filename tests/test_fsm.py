import contextlib
import typing

import pytest

from aidbox_python_fsm import FSM, FSMImpossibleTransitionError, FSMPermissionError

state = {"current": {}}


def reset_state():
    state["current"] = {}


def update_state(new_state: typing.Any):
    state["current"] = merge(state["current"], new_state)


def merge(source, destination):
    """
    run me with nosetests --with-doctest file.py

    >>> a = { 'first' : { 'all_rows' : { 'pass' : 'dog', 'number' : '1' } } }
    >>> b = { 'first' : { 'all_rows' : { 'fail' : 'cat', 'number' : '5' } } }
    >>> merge(b, a) == { 'first' : { 'all_rows' : { 'pass' : 'dog', 'fail' : 'cat', 'number' : '5' } } }
    True
    """
    for key, value in source.items():
        if isinstance(value, dict):
            # get node or create one
            node = destination.setdefault(key, {})
            merge(value, node)
        else:
            destination[key] = value

    return destination


async def always_true(context):
    return True


async def always_false(context):
    return False


@contextlib.asynccontextmanager
async def completed_middleware(context):
    update_state({"middleware": {"before": True, "context": context}})
    yield
    update_state({"middleware": {"after": True, "context": context}})


class MyException(Exception):
    pass


@contextlib.asynccontextmanager
async def precheck_failed_middleware(context):
    update_state({"middleware": {"before": True, "context": context}})

    raise MyException()
    yield
    set_state({"middleware": {"after": True}})


state: dict[str, typing.Any] = {"current": None}


fsm = FSM(
    {
        "initial": {
            "completed": {
                "permission": always_true,
                "middlewares": [completed_middleware],
                "context": {"custom": "custom"},
            },
            "precheck-failed": {
                "middlewares": [precheck_failed_middleware],
            },
            "impossible": {"permission": always_false},
        },
        "precheck-failed": {},
        "impossible": {},
        "completed": {},
    }
)


async def test_get_transitions_without_cheking_permission():
    assert await fsm.get_transitions({}, "initial", check_permission=False) == [
        "completed",
        "precheck-failed",
        "impossible",
    ]
    assert await fsm.get_transitions({}, "impossible", check_permission=False) == []
    assert await fsm.get_transitions({}, "completed", check_permission=False) == []
    assert await fsm.get_transitions({}, "precheck-failed", check_permission=False) == []


async def test_get_transitions():
    assert await fsm.get_transitions({}, "initial") == ["completed", "precheck-failed"]
    assert await fsm.get_transitions({}, "impossible") == []
    assert await fsm.get_transitions({}, "completed") == []
    assert await fsm.get_transitions({}, "precheck-failed") == []


async def test_apply_transition_without_cheking_permission():
    async def change_state(context, source_state, target_state):
        update_state(
            {
                "change_state": {
                    "context": context,
                    "source_state": source_state,
                    "target_state": target_state,
                },
            }
        )

    reset_state()
    await fsm.apply_transition(change_state, {}, "initial", "impossible", check_permission=False)
    assert state["current"] == {
        "change_state": {
            "context": {},
            "source_state": "initial",
            "target_state": "impossible",
        }
    }


async def test_apply_transition():
    async def change_state(context, source_state, target_state):
        update_state(
            {
                "change_state": {
                    "context": context,
                    "source_state": source_state,
                    "target_state": target_state,
                },
            }
        )

    reset_state()
    with pytest.raises(FSMPermissionError):
        await fsm.apply_transition(change_state, {}, "initial", "impossible")
    assert state["current"] == {}

    reset_state()
    with pytest.raises(FSMImpossibleTransitionError):
        await fsm.apply_transition(change_state, {}, "competed", "precheck-failed")
    assert state["current"] == {}

    reset_state()
    with pytest.raises(MyException):
        await fsm.apply_transition(change_state, {"main": "main"}, "initial", "precheck-failed")
    assert state["current"] == {"middleware": {"before": True, "context": {"main": "main"}}}

    reset_state()
    await fsm.apply_transition(change_state, {"main": "main"}, "initial", "completed")
    assert state["current"] == {
        "change_state": {
            "context": {"custom": "custom", "main": "main"},
            "source_state": "initial",
            "target_state": "completed",
        },
        "middleware": {
            "before": True,
            "after": True,
            "context": {"custom": "custom", "main": "main"},
        },
    }
