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


FSMMiddleware = typing.Callable[[typing.Any], typing.AsyncContextManager]
FSMPermission = typing.Callable[[typing.Any], typing.Coroutine[typing.Any, typing.Any, bool]]

class TransitionType(typing.TypedDict):
    context: typing_extensions.NotRequired[typing.Any]
    permission: typing_extensions.NotRequired[FSMPermission]
    middlewares: typing_extensions.NotRequired[typing.List[FSMMiddleware]]


class FSM:
    transitions = {}

    def __init__(self, transitions: dict[str, dict[str, TransitionType]]):
        self.transitions = transitions

    async def _check_permission(self, transition: TransitionType, context: typing.Any):
        permission = transition.get("permission")
        if not permission:
            return True

        return await permission(context)

    async def get_transitions(
        self, context: typing.Any, source_state: str, *, check_permission=True
    ):
        all_transitions = self.transitions.get(source_state, {})

        if check_permission:
            available_states = []

            for target_state, transition in all_transitions.items():
                extended_context = {**context, **transition.get("context", {})}
                if not await self._check_permission(transition, extended_context):
                    continue

                available_states.append(target_state)
            return available_states
        else:
            return list(all_transitions.keys())

    async def apply_transition(
        self,
        change_state: typing.Callable[[typing.Any, str, str], typing.Coroutine],
        context: typing.Any,
        source_state: str,
        target_state: str,
        *,
        check_permission=True,
    ):
        all_transitions = self.transitions.get(source_state, {})

        try:
            transition = all_transitions[target_state]
        except KeyError:
            raise FSMImpossibleTransitionError(source_state=source_state, target_state=target_state)

        extended_context = {**context, **transition.get("context", {})}

        if check_permission:
            if not await self._check_permission(transition, extended_context):
                raise FSMPermissionError(source_state=source_state, target_state=target_state)

        async with AsyncExitStack() as stack:
            for middleware in transition.get("middlewares", []):
                await stack.enter_async_context(middleware(extended_context))
            await change_state(extended_context, source_state, target_state)
