"""Authenticate protected endpoints before FastAPI parses their JSON bodies."""

from fastapi import Request
from fastapi.routing import APIRoute

from backend.app.modules.users.dependencies import get_current_user, require_admin, require_login


class CourseRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()

        def contains(dependant, dependency):
            return dependant.call is dependency or any(
                contains(child, dependency) for child in dependant.dependencies
            )

        admin_only = contains(self.dependant, require_admin)
        authenticated = contains(self.dependant, require_login)

        async def handler(request: Request):
            if authenticated:
                user = await get_current_user(request, request.app.state.auth_service)
                user = await require_login(user)
                if admin_only:
                    await require_admin(user)
            return await original(request)

        return handler
