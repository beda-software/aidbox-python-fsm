import contextlib
import functools
import typing

import jsonschema
from aiohttp import web
from fhirpy.base.exceptions import OperationOutcome

from .fsm import FSM, FSMImpossibleTransitionError, FSMPermissionError


def init_aidbox_fsm(
    fsm: FSM,
    get_state: typing.Callable[[typing.Any], typing.Coroutine[typing.Any, typing.Any, str]],
    set_state: typing.Callable[[typing.Any, str], typing.Coroutine[typing.Any, typing.Any, typing.Any]],
):
    async def apply_transition(
        resource, data, target_state, *, context=None, check_permission=True
    ):
        context = {"resource": resource, "data": data, **(context or {})}
        source_state = await get_state(resource)

        await fsm.apply_transition(
            lambda *_args: set_state(resource, target_state),
            context,
            source_state,
            target_state,
            check_permission=check_permission,
        )

    async def get_transitions(resource, *, context={}, check_permission=True):
        context = {"resource": resource, **(context or {})}
        source_state = await get_state(resource)

        transitions = await fsm.get_transitions(
            context, source_state, check_permission=check_permission
        )

        return source_state, transitions

    return apply_transition, get_transitions


def add_aidbox_fsm_operations(sdk, resource_type, apply_transition, get_transitions):
    @sdk.operation(
        ["POST"],
        [resource_type, {"name": "resource-id"}, "$apply-transition", {"name": "target-state"}],
    )
    async def apply_transition_op(_operation, request):
        resource = await sdk.client.reference(
            resource_type, request["route-params"]["resource-id"]
        ).to_resource()
        data = request.get("resource") or {}

        target_state = request["route-params"]["target-state"]
        try:
            await apply_transition(resource, data, target_state, context={"request": request})
        except FSMImpossibleTransitionError as exc:
            raise OperationOutcome(
                reason=f"Impossible transition from {exc.source_state} to {exc.target_state}"
            )
        except FSMPermissionError as exc:
            raise OperationOutcome(
                reason=f"You don't have permissions to make transition from {exc.source_state} to {exc.target_state}",
                code="security",
            )

        return web.json_response({})

    @sdk.operation(["GET"], [resource_type, {"name": "resource-id"}, "$get-transitions"])
    async def get_transitions_op(_operation, request):
        resource = await sdk.client.reference(
            resource_type, request["route-params"]["resource-id"]
        ).to_resource()

        source_state, transitions = await get_transitions(resource, context={"request": request})

        return web.json_response({"sourceState": source_state, "transitions": transitions})


def aidbox_fsm_middleware(_fn=None, *, data_schema=None):
    data_validator = None
    if data_schema:
        data_validator = jsonschema.Draft202012Validator(schema=data_schema)

    def wrapper(fn):
        @functools.wraps(fn)
        def wrapped_middleware(context):
            context = context.copy()
            resource = context.pop("resource")
            data = context.pop("data")

            if data_validator:
                validate_data(data_validator, data)

            return contextlib.asynccontextmanager(fn)(resource, data, context)

        return wrapped_middleware

    if _fn is None:
        return wrapper
    else:
        return wrapper(_fn)


def aidbox_fsm_permission(fn):
    @functools.wraps(fn)
    async def wrapped_permission(context):
        context = context.copy()
        resource = context.pop("resource")
        return await fn(resource, context)

    return wrapped_permission


def validate_data(data_validator, data):
    errors = list(data_validator.iter_errors(data))

    if errors:
        raise OperationOutcome(
            resource={
                "resourceType": "OperationOutcome",
                "text": {"status": "generated", "div": "Invalid input data"},
                "issue": [
                    {
                        "severity": "fatal",
                        "code": "invalid",
                        "expression": [".".join([str(x) for x in ve.absolute_path])],
                        "diagnostics": ve.message,
                    }
                    for ve in errors
                ],
            }
        )
