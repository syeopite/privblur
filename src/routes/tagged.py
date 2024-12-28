import urllib.parse

import sanic
import sanic_ext

from ..cache import get_tag_browse_results
from ..helpers import helpers

tagged = sanic.Blueprint("tagged", url_prefix="/tagged")


@tagged.get("/<tag:str>")
@tagged.get("/<tag:str>/rss", name="_main_rss", ctx_rss=True)
async def _main(request: sanic.Request, tag: str):
    tag = urllib.parse.unquote(tag)
    sort_by = request.args.get("sort")

    if continuation := request.args.get("continuation"):
        continuation = urllib.parse.unquote(continuation)

    latest = False
    if sort_by == "recent":
        latest = True
    else:
        sort_by = "top"

    timeline = await get_tag_browse_results(request.app.ctx, tag, latest=latest, continuation=continuation)

    # We remove the continuation parameter used to fetch this page as to ensure the current continuation parameter isn't 
    # added when applying a search filter
    if request.args.get("continuation"):
        del request.args["continuation"]

    if hasattr(request.route.ctx, "rss"):
        template_path = "rss/timeline.xml.jinja"
        render_args : dict = {
            "content_type": "application/rss+xml",
        }
        page_url = f"{request.app.ctx.PRIVIBLUR_CONFIG.deployment.domain or ''}/tagged/{urllib.parse.quote(tag)}"
        if request.query_string:
            page_url += f"?{request.query_string}"

        context_args : dict = {
            "page_url": page_url
        }
        if last_post := timeline.elements[-1]:
            context_args["updated"] = last_post.date
        else:
            context_args["updated"] = datetime.datetime.now(tz=datetime.timezone.utc)
    else:
        template_path = "tagged.jinja"
        context_args : dict = {}
        render_args : dict = {}

    return await sanic_ext.render(
        template_path,
        context={
            "app": request.app,
            "query_args": request.args,
            "timeline": timeline,
            "tag": tag,
            "sort_by": sort_by,
            **context_args
        },
        **render_args
    )