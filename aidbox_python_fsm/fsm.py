import typing
from contextlib import AsyncExitStack

import typing_extensions


class FSMError(Exception):
    source_state = None
    target_state = None

    def __init__(self, source_state, target_state) -> None:
        self.source_state = source_state
        self.target_state = target_state
        super().__init__()

class FSMImpossibleTransitionError(FSMError):
    pass


class FSMPermissionError(FSMError):
    pass


class TransitionType(typing.TypedDict):
    context: typing_extensions.NotRequired[typing.Any]
    permissions: typing_extensions.NotRequired[
        typing.List[typing.Callable[[typing.Any], typing.Coroutine[typing.Any, typing.Any, bool]]]
    ]
    middlewares: typing_extensions.NotRequired[
        typing.List[typing.Callable[[typing.Any], typing.AsyncContextManager]]
    ]


class FSM:
    transitions = {}

    def __init__(self, transitions: dict[str, dict[str, TransitionType]]):
        self.transitions = transitions

    async def _check_permissions(self, transition: TransitionType, context: typing.Any):
        for permission in transition.get("permissions", []):
            if not await permission(context):
                return False

        return True

    async def get_transitions(
        self, context: typing.Any, source_state: str, *, ignore_permissions=False
    ):
        available_transitions = []

        for target_state, transition in self.transitions.get(source_state, {}).items():
            if not ignore_permissions:
                extended_context = {**context, **transition.get("context", {})}
                if not await self._check_permissions(transition, extended_context):
                    continue

            available_transitions.append(target_state)
        return available_transitions

    async def apply_transition(
        self,
        change_state: typing.Callable[[typing.Any, str, str], typing.Coroutine],
        context: typing.Any,
        source_state: str,
        target_state: str,
        *,
        ignore_permissions=False,
    ):
        available_transitions = self.transitions.get(source_state, {})

        try:
            transition = available_transitions[target_state]
        except KeyError:
            raise FSMImpossibleTransitionError()

        extended_context = {**context, **transition.get("context", {})}

        if not ignore_permissions:
            if not await self._check_permissions(transition, extended_context):
                raise FSMPermissionError()

        async with AsyncExitStack() as stack:
            for middleware in transition.get("middlewares", []):
                await stack.enter_async_context(middleware(extended_context))
            await change_state(extended_context, source_state, target_state)
