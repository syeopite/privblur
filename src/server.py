import os
import logging
import urllib.parse
import functools

import sanic
import aiohttp
import orjson
import babel.numbers
import babel.dates
import babel.lists
import redis.asyncio
from npf_renderer import VERSION as NPF_RENDERER_VERSION

from . import routes, priviblur_extractor, preferences, i18n
from .exceptions import error_handlers
from .config import load_config
from .helpers import setup_logging, helpers, ext_npf_renderer
from .version import VERSION, CURRENT_COMMIT


# Load configuration file 

config = load_config(os.environ.get("PRIVIBLUR_CONFIG_LOCATION", "./config.toml"))

LOG_CONFIG = setup_logging.setup_logging(config.logging)
app = sanic.Sanic("Priviblur", loads=orjson.loads, dumps=orjson.dumps, env_prefix="PRIVIBLUR_", log_config=LOG_CONFIG)


app.ctx.LANGUAGES = i18n.initialize_locales()
app.ctx.SUPPORTED_LANGUAGES = i18n.SUPPORTED_LANGUAGES

# Constants

app.config.TEMPLATING_PATH_TO_TEMPLATES = "src/templates"

app.ctx.LOGGER = logging.getLogger("priviblur")

app.ctx.CURRENT_COMMIT = CURRENT_COMMIT  # Used for cache busting
app.ctx.NPF_RENDERER_VERSION = NPF_RENDERER_VERSION
app.ctx.VERSION = VERSION

app.ctx.URL_HANDLER = helpers.url_handler
app.ctx.BLACKLIST_RESPONSE_HEADERS = ("access-control-allow-origin", "alt-svc", "server")

app.ctx.PRIVIBLUR_CONFIG = config
app.ctx.translate = i18n.translate

app.ctx.PRIVIBLUR_PARENT_DIR_PATH = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))


@app.listener("before_server_start")
async def initialize(app):
    priviblur_backend = app.ctx.PRIVIBLUR_CONFIG.backend

    app.ctx.TumblrAPI = await priviblur_extractor.TumblrAPI.create(
        main_request_timeout=priviblur_backend.main_response_timeout, json_loads=orjson.loads
    )

    media_request_headers = {
        "user-agent": priviblur_extractor.TumblrAPI.DEFAULT_HEADERS["user-agent"],
        "accept-encoding": "gzip, deflate, br",
        "accept": "image/avif,image/webp,*/*",
        "accept-language": "en-US,en;q=0.5",
        "te": "trailers",
        "referer": "https://www.tumblr.com",
    }

    # TODO set pool size for image requests

    def create_image_client(url, timeout):
        timeout = aiohttp.ClientTimeout(timeout)
        return aiohttp.ClientSession(url, headers=media_request_headers, timeout=timeout)

    app.ctx.Media64Client = create_image_client(
        "https://64.media.tumblr.com", priviblur_backend.image_response_timeout
    )

    app.ctx.Media49Client = create_image_client(
        "https://49.media.tumblr.com", priviblur_backend.image_response_timeout
    )

    app.ctx.Media44Client = create_image_client(
        "https://44.media.tumblr.com", priviblur_backend.image_response_timeout
    )

    app.ctx.MediaVeClient = create_image_client(
        "https://ve.media.tumblr.com", priviblur_backend.image_response_timeout
    )

    app.ctx.MediaVaClient = create_image_client(
        "https://va.media.tumblr.com", priviblur_backend.image_response_timeout
    )

    app.ctx.MediaGenericClient = aiohttp.ClientSession(
        headers=media_request_headers,
        timeout=aiohttp.ClientTimeout(priviblur_backend.image_response_timeout)
    )

    app.ctx.AudioClient = create_image_client(
        "https://a.tumblr.com", priviblur_backend.image_response_timeout
    )

    app.ctx.TumblrAssetClient = create_image_client(
        "https://assets.tumblr.com", priviblur_backend.image_response_timeout
    )

    app.ctx.TumblrStaticClient = create_image_client(
        "https://static.tumblr.com", priviblur_backend.image_response_timeout
    )

    app.ctx.TumblrAtClient = aiohttp.ClientSession(
        "https://at.tumblr.com",
        headers={"user-agent": priviblur_extractor.TumblrAPI.DEFAULT_HEADERS["user-agent"]},
        timeout=aiohttp.ClientTimeout(priviblur_backend.main_response_timeout)
    )

    # Initialize database
    if cache_url := app.ctx.PRIVIBLUR_CONFIG.cache.url:
        try:
            app.ctx.CacheDb = redis.asyncio.from_url(cache_url, protocol=3, decode_responses=True)
            await app.ctx.CacheDb.ping()
        except redis.exceptions.ConnectionError:
            app.ctx.LOGGER.error("Error: Unable to connect to Redis! Disabling cache until the problem can be fixed. Please check your configuration file and the Redis server.")
            app.ctx.CacheDb = None
    else:
        app.ctx.CacheDb = None

    # Add additional jinja filters and functions

    app.ext.environment.add_extension("jinja2.ext.do")

    app.ext.environment.filters["encodepathsegment"] = functools.partial(urllib.parse.quote, safe="")

    app.ext.environment.filters["update_query_params"] = helpers.update_query_params
    app.ext.environment.filters["remove_query_params"] = helpers.remove_query_params
    app.ext.environment.filters["deseq_urlencode"] = helpers.deseq_urlencode
    app.ext.environment.filters["ensure_single_prefix_slash"] = helpers.prefix_slash_in_url_if_missing

    app.ext.environment.filters["format_decimal"] = babel.numbers.format_decimal
    app.ext.environment.filters["format_date"] = babel.dates.format_date
    app.ext.environment.filters["format_datetime"] = babel.dates.format_datetime

    app.ext.environment.filters["format_list"] = babel.lists.format_list

    app.ext.environment.globals["translate"] = i18n.translate
    app.ext.environment.globals["url_handler"] = helpers.url_handler
    app.ext.environment.globals["format_npf"] = ext_npf_renderer.format_npf
    app.ext.environment.globals["create_poll_callback"] = helpers.create_poll_callback

    app.ext.environment.tests["a_post"] = lambda element : isinstance(element, priviblur_extractor.models.post.Post)


@app.listener("main_process_start")
async def main_startup_listener(app):
    """Startup listener to notify of priviblur startup"""
    print(f"Starting up Priviblur version {VERSION}")


@app.get("/")
async def root(request):
    return sanic.redirect(request.app.url_for("explore._trending"))


@app.route("/robots.txt")
async def robotstxt_route(request):
    return await sanic.file("./assets/robots.txt")


@app.middleware("request", priority=1)
async def before_all_routes(request):
    request.ctx.preferences = preferences.UserPreferences(
            **config.default_user_preferences._asdict()
    )

    request.ctx.language = request.ctx.preferences.language

    request.ctx.preferences = request.ctx.preferences.replace_from_cookie(request)


@app.middleware("response")
async def after_all_routes(request, response):
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

# Register all routes:
for route in routes.BLUEPRINTS:
    app.blueprint(route)

# Register error handlers into Priviblur
error_handlers.register(app)

if __name__ == "__main__":
    app.run(
        host=config.deployment.host,
        port=config.deployment.port,
        workers=config.deployment.workers,
        dev=config.misc.dev_mode
    )
