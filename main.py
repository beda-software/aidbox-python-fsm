import logging

import coloredlogs
from aidbox_python_sdk.main import create_app as _create_app
from aidbox_python_sdk.sdk import SDK
from aidbox_python_sdk.settings import Settings

coloredlogs.install(level="DEBUG", fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.DEBUG
)
logging.getLogger("aidbox_sdk").setLevel(logging.INFO)
logging.getLogger("urllib3").setLevel(logging.INFO)

sdk_settings = Settings(**{})

meta_resources = {}
sdk = SDK(sdk_settings, resources=meta_resources)

async def create_app():
    return await _create_app(sdk_settings, sdk, debug=True)
