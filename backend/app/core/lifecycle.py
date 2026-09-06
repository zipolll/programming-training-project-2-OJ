"""Give reset exclusive access after in-flight HTTP requests have completed."""

import asyncio


class ResetIsolationMiddleware:
    def __init__(self, app, reset_path: str) -> None:
        self.app = app
        self.reset_path = reset_path
        self.condition = asyncio.Condition()
        self.active = 0
        self.resetting = False

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        exclusive = scope["method"] == "POST" and scope["path"] == self.reset_path
        async with self.condition:
            await self.condition.wait_for(
                lambda: not self.resetting and (not exclusive or self.active == 0)
            )
            if exclusive:
                self.resetting = True
            else:
                self.active += 1
        try:
            await self.app(scope, receive, send)
        finally:
            async with self.condition:
                if exclusive:
                    self.resetting = False
                else:
                    self.active -= 1
                self.condition.notify_all()
