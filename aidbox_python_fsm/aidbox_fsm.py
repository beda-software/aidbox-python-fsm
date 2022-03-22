from aiohttp import web

from .fsm import FSMError, FSMPermissionError


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
        user = await get_user_with_roles(sdk, request)

        resource = await sdk.client.reference(
            resource_type, request["route-params"]["resource-id"]
        ).to_resource()
        source_state = resource[state_attribute]
        target_state = request["route-params"]["target-state"]

        context = {"resource": resource, "user": user, "request": request}

        try:
            await fsm.apply_transition(change_state, context, source_state, target_state)

            await resource.refresh()

            return web.json_response(resource)
        except FSMPermissionError:
            return web.json_response({}, status=403)
        except FSMError:
            return web.json_response({}, status=422)

    @sdk.operation(["GET"], [resource_type, {"name": "resource-id"}, "$get-transitions"])
    async def get_transitions_op(_operation, request):
        user = await get_user_with_roles(sdk, request)

        resource = await sdk.client.reference(
            resource_type, request["route-params"]["resource-id"]
        ).to_resource()
        source_state = resource[state_attribute]
        context = {"resource": resource, "user": user}

        transitions = [
            target_state for target_state in await fsm.get_transitions(context, source_state)
        ]

        return web.json_response({"sourceState": source_state, "transitions": transitions})


async def get_user_with_roles(sdk, request):
    user = sdk.client.resource("User", **request["oauth/user"])
    roles = await sdk.client.resources("Role").search(user=user).fetch_all()
    user["role"] = roles

    return user
