import contextlib
import functools

import jsonschema
from aidbox_python_sdk.sdk import validate_request
from aiohttp import web
from fhirpy.base.exceptions import OperationOutcome

from .fsm import FSMError, FSMImpossibleTransitionError, FSMPermissionError


def add_fsm_operations(sdk, fsm, resource_type, state_attribute):
    async def change_state(context, _source_state, target_state):
        resource = context["resource"]
        resource[state_attribute] = target_state
        await resource.save()

    @sdk.operation(
        ["POST"],
        [resource_type, {"name": "resource-id"}, "$apply-transition", {"name": "target-state"}],
    )
    async def apply_transition_op(_operation, request):
        resource = await sdk.client.reference(
            resource_type, request["route-params"]["resource-id"]
        ).to_resource()
        source_state = resource[state_attribute]
        target_state = request["route-params"]["target-state"]

        context = {"resource": resource, "request": request}

        try:
            await fsm.apply_transition(change_state, context, source_state, target_state)

            return web.json_response(resource)
        except FSMImpossibleTransitionError:
            raise OperationOutcome(
                reason=f"Impossible transition from {source_state} to {target_state}"
            )
        except FSMPermissionError:
            raise OperationOutcome(
                reason=f"You don't have permissions to make transition from {source_state} to {target_state}",
                code="security",
            )

    @sdk.operation(["GET"], [resource_type, {"name": "resource-id"}, "$get-transitions"])
    async def get_transitions_op(_operation, request):
        resource = await sdk.client.reference(
            resource_type, request["route-params"]["resource-id"]
        ).to_resource()
        source_state = resource[state_attribute]
        context = {"resource": resource, "request": request}

        transitions = [
            target_state for target_state in await fsm.get_transitions(context, source_state)
        ]

        return web.json_response({"sourceState": source_state, "transitions": transitions})


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
