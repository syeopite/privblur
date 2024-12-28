import datetime
import urllib.parse

import sanic
import sanic_ext

from .. import priviblur_extractor
from ..cache import get_explore_results

explore = sanic.Blueprint("explore", url_prefix="/explore")


async def _handle_explore(request, endpoint, post_type = None):
    app = request.app
    raw_endpoint = endpoint
    endpoint = request.app.url_for(endpoint)

    if continuation := request.args.get("continuation"):
        continuation = urllib.parse.unquote(continuation)

    match raw_endpoint:
        case "explore._trending":
            timeline = await get_explore_results(
                request.app.ctx,
                request.app.ctx.TumblrAPI.explore_trending,
                "trending",
                continuation,
            )

            title = request.app.ctx.translate(request.ctx.language, "explore_trending_page_title")
        case "explore._today":
            timeline = await get_explore_results(
                request.app.ctx,
                request.app.ctx.TumblrAPI.explore_today,
                "today",
                continuation,
            )
            title = request.app.ctx.translate(request.ctx.language, "explore_today_on_tumblr_page_title")
        case _:
            timeline = await get_explore_results(
                request.app.ctx,
                request.app.ctx.TumblrAPI.explore_post,
                post_type.name.lower(),
                continuation,
                post_type=post_type
            )
            title = request.app.ctx.translate(request.ctx.language, "explore_trending_page_title")

    if hasattr(request.route.ctx, "rss"):
        template_path = "rss/timeline.xml.jinja"
        render_args : dict = {
            "content_type": "application/rss+xml",
        }

        context_args : dict = {
            "page_url": f"{request.app.ctx.PRIVIBLUR_CONFIG.deployment.domain or ""}/{endpoint}"
        }
        if last_post := timeline.elements[-1]:
            context_args["updated"] = last_post.date
        else:
            context_args["updated"] = datetime.datetime.now(tz=datetime.timezone.utc)
    else:
        template_path = "timeline.jinja"
        context_args : dict = {}
        render_args : dict = {}

    return await sanic_ext.render(
        template_path,
        context={
            "app": app,
            "title": title,
            "timeline": timeline,
            **context_args
        },
        **render_args
    )


@explore.get("/")
async def _main(request):
    return sanic.redirect(request.app.url_for("explore._trending"))  # /explore/trending


@explore.get("/trending")
@explore.get("/trending/rss", ctx_rss=True, name="_trending_rss")
async def _trending(request):
    return await _handle_explore(request, "explore._trending")


@explore.get("/today")
@explore.get("/today/rss", ctx_rss=True, name="_today_rss")
async def _today(request):
    return await _handle_explore(request, "explore._today")


@explore.get("/text")
@explore.get("/text/rss", ctx_rss=True, name="_text_rss")
async def _text(request):
    return await _handle_explore(request, "explore._text", request.app.ctx.TumblrAPI.config.ExplorePostTypeFilters.TEXT)


@explore.get("/photos")
@explore.get("/photos/rss", ctx_rss=True, name="_photos_rss")
async def _photos(request):
    return await _handle_explore(request, "explore._photos", request.app.ctx.TumblrAPI.config.ExplorePostTypeFilters.PHOTOS)


@explore.get("/gifs")
@explore.get("/gifs/rss", ctx_rss=True, name="_gifs_rss")
async def _gifs(request):
    return await _handle_explore(request, "explore._gifs", request.app.ctx.TumblrAPI.config.ExplorePostTypeFilters.GIFS)


@explore.get("/quotes")
@explore.get("/quotes/rss", ctx_rss=True, name="_quotes_rss")
async def _quotes(request):
    return await _handle_explore(request, "explore._quotes", request.app.ctx.TumblrAPI.config.ExplorePostTypeFilters.QUOTES)


@explore.get("/chats")
@explore.get("/chats/rss", ctx_rss=True, name="_chats_rss")
async def _chats(request):
    return await _handle_explore(request, "explore._chats", request.app.ctx.TumblrAPI.config.ExplorePostTypeFilters.CHATS)


@explore.get("/audio")
@explore.get("/audio/rss", ctx_rss=True, name="_audio_rss")
async def _audio(request):
    return await _handle_explore(request, "explore._audio", request.app.ctx.TumblrAPI.config.ExplorePostTypeFilters.AUDIO)


@explore.get("/video")
@explore.get("/video/rss", ctx_rss=True, name="_video_rss")
async def _video(request):
    return await _handle_explore(request, "explore._video", request.app.ctx.TumblrAPI.config.ExplorePostTypeFilters.VIDEO)


@explore.get("/asks")
@explore.get("/asks/rss", ctx_rss=True, name="_asks_rss")
async def _asks(request):
    return await _handle_explore(request, "explore._asks", request.app.ctx.TumblrAPI.config.ExplorePostTypeFilters.ASKS)
