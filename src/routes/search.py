import datetime
import urllib.parse

import sanic
import sanic_ext

from ..cache import get_search_results
from .. import priviblur_extractor

search = sanic.Blueprint("search", url_prefix="/search")


@search.get("/")
async def query_param_redirect(request: sanic.Request):
    """Endpoint for /search to redirect q= queries to /search/<query>"""
    if query := request.args.get("q"):
        return sanic.redirect(request.app.url_for("search._main", query=urllib.parse.quote(query, safe="")))
    else:
        return sanic.redirect(request.app.url_for("explore._trending"))


@search.get("/<query:str>")
@search.get("/<query:str>/rss", name="_name_rss", ctx_rss=True)
async def _main(request: sanic.Request, query: str):
    query = urllib.parse.unquote(query)

    time_filter = request.args.get("t")
    if not time_filter or time_filter not in ("365", "180", "30", "7", "1"):
        time_filter = 0

    timeline = await _query_search(request, query, days=time_filter)

    return await _render(request, timeline, query, time_filter=time_filter, sort_by="popular", post_filter=None)


@search.get("/<query:str>/recent")
@search.get("/<query:str>/recent/rss", name="_sort_by_search_rss", ctx_rss=True)
async def _sort_by_search(request: sanic.Request, query: str):
    query = urllib.parse.unquote(query)
    time_filter = request.args.get("t")

    # Ignore time filter when its invalid
    if not time_filter or time_filter not in ("365", "180", "30", "7", "1"):
        time_filter = 0

    timeline = await _query_search(request, query, days=time_filter, latest=True)

    return await _render(request, timeline, query, time_filter=time_filter, sort_by="recent", post_filter=None)


@search.get("/<query:str>/<post_filter:str>")
@search.get("/<query:str>/<post_filter:str>/rss", name="_filter_by_search_rss", ctx_rss=True)
async def _filter_by_search(request: sanic.Request, query: str, post_filter: str):
    return await _request_search_filter_post(request, query, post_filter, latest=False)


@search.get("/<query:str>/recent/<post_filter:str>")
@search.get("/<query:str>/recent/<post_filter:str>/rss", name="_sort_by_and_filter_search_rss", ctx_rss=True)
async def _sort_by_and_filter_search(request: sanic.Request, query: str, post_filter: str):
    return await _request_search_filter_post(request, query, post_filter, latest=True)


async def _request_search_filter_post(request, query, post_filter, latest):
    query = urllib.parse.unquote(query)
    post_filter = urllib.parse.unquote(post_filter)
    time_filter = request.args.get("t")

    PostFiltersEnum = request.app.ctx.TumblrAPI.config.PostTypeFilters
    post_filter = post_filter.upper()

    # Tumblr internally uses "answer" to filter for ask posts but
    # displays "ask" on the UI and URL. We'll need to handle this and swap back to ask
    # once the search results are queried as so the correct localization and url is used.
    #
    # Note: due to the else branch, "answer" is (still) supported as a valid option. Should
    # this be kept, or removed for consistency with Tumblr?
    if post_filter == "ASK":
        post_filter = PostFiltersEnum.ANSWER
    else:
        post_filter = getattr(PostFiltersEnum.ANSWER, post_filter, None)

    # As to match Tumblr's behavior we redirect to the main /search endpoint when the
    # given post filter is invalid
    #
    # If we are sorting by the latest posts then we redirect to /search/recent 
    if not post_filter:
        if latest:
           url = request.app.url_for("search._sort_by_search", query=urllib.parse.quote(query))
        else:
            url = request.app.url_for("search._main", query=urllib.parse.quote(query))

        url += f"?{request.query_string}" if request.query_string else ""
        return sanic.redirect(url)

    # Ignore time filter when its invalid
    if not time_filter or time_filter not in ("365", "180", "30", "7", "1"):
        time_filter = 0

    timeline = await _query_search(request, query, days=time_filter, post_type_filter=post_filter, latest=latest)
    
    # Swap "answer" to "ask"
    # See above.
    post_filter = "ask" if post_filter == PostFiltersEnum.ANSWER else post_filter.name.lower()

    sort_by = "recent" if latest else "popular"

    return await _render(request, timeline, query, post_filter=post_filter, time_filter=time_filter, sort_by=sort_by)


async def _query_search(request, query, **kwargs):
    "Queries the search endpoint"
    if continuation := request.args.get("continuation"):
        continuation = urllib.parse.unquote(continuation)

    return await get_search_results(request.app.ctx, query, continuation, **kwargs)

async def _render(request, timeline, query, **kwargs):
    # We remove the continuation parameter used to fetch this page as to ensure the current continuation parameter isn't
    # added when applying a search filter
    if request.args.get("continuation"):
        del request.args["continuation"]

    context = {
        "app": request.app,
        "timeline": timeline,
        "query_args": request.args,
        "query": query
    }

    context.update(kwargs)

    if hasattr(request.route.ctx, "rss"):
        template_path = "rss/timeline.xml.jinja"
        render_args : dict = {
            "content_type": "application/rss+xml",
        }
        search_url = request.app.url_for(request.endpoint, query=urllib.parse.quote(query), **kwargs)
        page_url = f"{request.app.ctx.PRIVIBLUR_CONFIG.deployment.domain or ''}/{search_url}"
        if request.query_string:
            page_url += f"?{request.query_string}"

        context["page_url"] = page_url

        if last_post := timeline.elements[-1]:
            context["updated"] = last_post.date
        else:
            context["updated"] = datetime.datetime.now(tz=datetime.timezone.utc)
    else:
        template_path = "search.jinja"
        render_args : dict = {}

    return await sanic_ext.render(
        template_path,
        context=context,
        **render_args
    )