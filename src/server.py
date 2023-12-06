import sys
import os
import logging
import gettext

import httpx
import orjson
import sanic_ext
import sanic.response
from sanic import Sanic
import babel.numbers
import babel.dates
from npf_renderer import VERSION as NPF_RENDERER_VERSION, format_npf

from . import routes, priviblur_extractor
from . import priviblur_extractor

from .config import load_config
from .helpers import setup_logging, helpers, error_handlers
from .version import VERSION, CURRENT_COMMIT


# Load configuration file 

config = load_config(os.environ.get("PRIVIBLUR_CONFIG_LOCATION", "./config.toml"))

LOG_CONFIG = setup_logging.setup_logging(config.logging)
app = Sanic("Priviblur", loads=orjson.loads, dumps=orjson.dumps, env_prefix="PRIVIBLUR_", log_config=LOG_CONFIG)


if config.deployment.forwarded_secret and not app.config.FORWARDED_SECRET:
    app.config.FORWARDED_SECRET = config.deployment.forwarded_secret


if config.deployment.real_ip_header and not app.config.REAL_IP_HEADER:
    app.config.REAL_IP_HEADER = config.deployment.real_ip_header


if config.deployment.proxies_count and not app.config.PROXIES_COUNT:
    app.config.PROXIES_COUNT = config.deployment.proxies_count

# Constants

app.config.TEMPLATING_PATH_TO_TEMPLATES = "src/templates"

app.ctx.LOGGER = logging.getLogger("priviblur")

app.ctx.CURRENT_COMMIT = CURRENT_COMMIT  # Used for cache busting
app.ctx.NPF_RENDERER_VERSION = NPF_RENDERER_VERSION
app.ctx.VERSION = VERSION

app.ctx.URL_HANDLER = helpers.url_handler
app.ctx.BLACKLIST_RESPONSE_HEADERS = ("access-control-allow-origin", "alt-svc", "server")

app.ctx.PRIVIBLUR_CONFIG = config
app.ctx.translate = helpers.translate

@app.listener("before_server_start")
async def initialize(app):
    priviblur_backend = app.ctx.PRIVIBLUR_CONFIG.backend

    app.ctx.TumblrAPI = await priviblur_extractor.TumblrAPI.create(
        main_request_timeout=priviblur_backend.main_response_timeout, json_loads=orjson.loads
    )

    # We'll also have a separate HTTP client for images
    media_request_headers = priviblur_extractor.TumblrAPI.DEFAULT_HEADERS
    del media_request_headers["authorization"]

    # TODO set pool size for image requests

    def create_image_client(url, timeout):
        return httpx.AsyncClient(base_url=url, headers=media_request_headers, http2=True, timeout=timeout)

    app.ctx.Media64Client = create_image_client(
        "https://64.media.tumblr.com", priviblur_backend.image_response_timeout
    )

    app.ctx.Media49Client = create_image_client(
        "https://49.media.tumblr.com", priviblur_backend.image_response_timeout
    )

    app.ctx.Media44Client = create_image_client(
        "https://44.media.tumblr.com", priviblur_backend.image_response_timeout
    )

    app.ctx.TumblrAssetClient = create_image_client(
        "https://assets.tumblr.com", priviblur_backend.image_response_timeout
    )

    app.ctx.TumblrStaticClient = create_image_client(
        "https://static.tumblr.com", priviblur_backend.image_response_timeout
    )

    # Add additional jinja filters and functions

    app.ext.environment.filters["update_query_params"] = helpers.update_query_params
    app.ext.environment.filters["remove_query_params"] = helpers.remove_query_params
    app.ext.environment.filters["deseq_urlencode"] = helpers.deseq_urlencode

    app.ext.environment.filters["format_decimal"] = babel.numbers.format_decimal
    app.ext.environment.filters["format_date"] = babel.dates.format_date
    app.ext.environment.filters["format_datetime"] = babel.dates.format_datetime

    app.ext.environment.globals["translate"] = helpers.translate
    app.ext.environment.globals["url_handler"] = helpers.url_handler
    app.ext.environment.globals["format_npf"] = format_npf

    # Initialize locales
    gettext_instances = {"en": gettext.translation("priviblur", localedir="locales", languages=["en"])}
    app.ctx.GETTEXT_INSTANCES = gettext_instances


@app.listener("main_process_start")
async def main_startup_listener(app):
    """Startup listener to notify of priviblur startup"""
    print(f"Starting up Priviblur version {VERSION}")


@app.get("/")
async def root(request):
    return sanic.redirect(request.app.url_for("explore._today"))


@app.middleware("response")
async def before_all_routes(request, response):
    # https://github.com/iv-org/invidious/blob/master/src/invidious/routes/before_all.cr
    response.headers["x-xss-protection"] = "1; mode=block"
    response.headers["x-content-type-options"] = "nosniff"
    response.headers["referrer-policy"] = "same-origin"

    response.headers["content-security-policy"] = "; ".join(
        [
            "default-src 'none'",
            "script-src 'self'",
            "style-src 'self' 'unsafe-inline'",
            "img-src 'self' data:",
            "font-src 'self' data:",
            "connect-src 'self'",
            "manifest-src 'self'",
            "media-src 'self'",
            "child-src 'self' blob:",
        ]
    )


app.error_handler.add(priviblur_extractor.priviblur_exceptions.TumblrLoginRequiredError, error_handlers.tumblr_error_login_walled)
app.error_handler.add(priviblur_extractor.priviblur_exceptions.TumblrRestrictedTagError, error_handlers.tumblr_error_restricted_tag)
app.error_handler.add(priviblur_extractor.priviblur_exceptions.TumblrBlogNotFoundError, error_handlers.tumblr_error_unknown_blog)
app.error_handler.add(sanic.exceptions.NotFound, error_handlers.error_404)

# Register all routes:
for route in routes.BLUEPRINTS:
    app.blueprint(route)


if __name__ == "__main__":
    app.run(
        host=config.deployment.host,
        port=config.deployment.port,
        workers=config.deployment.workers,
        dev=config.misc.dev_mode
    )
