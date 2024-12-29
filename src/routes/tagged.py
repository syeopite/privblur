import urllib.parse

import sanic

from ..cache import get_tag_browse_results

tagged = sanic.Blueprint("tagged", url_prefix="/tagged")


@tagged.get("/<tag:str>")
@tagged.get("/<tag:str>/rss", name="_main_rss", ctx_rss=True, ctx_template="timeline")
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

    return await request.app.ctx.render(
        "tagged",
        context={
            "app": request.app,
            "query_args": request.args,
            "timeline": timeline,
            "tag": tag,
            "sort_by": sort_by,
        },
    )