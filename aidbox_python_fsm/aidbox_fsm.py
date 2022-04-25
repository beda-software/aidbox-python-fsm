import contextlib
import functools

import jsonschema
from aidbox_python_sdk.sdk import validate_request
from aiohttp import web
from fhirpy.base.exceptions import OperationOutcome

from .fsm import FSMError, FSMImpossibleTransitionError, FSMPermissionError


def add_fsm_operations(sdk, fsm, resource_type, get_state, set_state):
    async def apply_transition(resource, target_state, request, ignore_permissions=False):
        context = {"resource": resource, "request": request}
        source_state = await get_state(context)

        try:
            await fsm.apply_transition(
                set_state,
                context,
                source_state,
                target_state,
                ignore_permissions=ignore_permissions,
            )
        except FSMImpossibleTransitionError:
            raise OperationOutcome(
                reason=f"Impossible transition from {source_state} to {target_state}"
            )
        except FSMPermissionError:
            raise OperationOutcome(
                reason=f"You don't have permissions to make transition from {source_state} to {target_state}",
                code="security",
            )

    async def get_transitions(resource, request, ignore_permissions=False):
        context = {"resource": resource, "request": request}
        source_state = await get_state(context)

        transitions = await fsm.get_transitions(
            context, source_state, ignore_permissions=ignore_permissions
        )
        return source_state, transitions

    @sdk.operation(
        ["POST"],
        [resource_type, {"name": "resource-id"}, "$apply-transition", {"name": "target-state"}],
    )
    async def apply_transition_op(_operation, request):
        resource = await sdk.client.reference(
            resource_type, request["route-params"]["resource-id"]
        ).to_resource()

        target_state = request["route-params"]["target-state"]

        await apply_transition(resource, target_state, request)

        return web.json_response({})

    @sdk.operation(["GET"], [resource_type, {"name": "resource-id"}, "$get-transitions"])
    async def get_transitions_op(_operation, request):
        resource = await sdk.client.reference(
            resource_type, request["route-params"]["resource-id"]
        ).to_resource()

        source_state, transitions = await get_transitions(resource, request)

        return web.json_response({"sourceState": source_state, "transitions": transitions})

    return apply_transition, get_transitions


def aidbox_fsm_middleware(_fn=None, *, request_schema=None):
    request_validator = None
    if request_schema:
        request_validator = jsonschema.Draft202012Validator(schema=request_schema)

    def wrapper(fn):
        @functools.wraps(fn)
        def wrapped_middleware(context):
            context = context.copy()
            request = context.pop("request")
            resource = context.pop("resource")

            if request_validator:
                validate_request(request_validator, request)

            return contextlib.asynccontextmanager(fn)(resource, request, context)

        return wrapped_middleware

    if _fn is None:
        return wrapper
    else:
        return wrapper(_fn)


def aidbox_fsm_permission(fn):
    @functools.wraps(fn)
    async def wrapped_permission(context):
        context = context.copy()
        request = context.pop("request")
        resource = context.pop("resource")
        return await fn(resource, request, context)

    return wrapped_permission
