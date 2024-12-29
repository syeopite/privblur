import urllib.parse

import sanic

from ...cache import get_blog_posts, get_blog_search_results

blogs = sanic.Blueprint("blogs", url_prefix="/")


@blogs.get("/")
@blogs.get("rss", name="_blog_posts_rss", ctx_rss=True)
async def _blog_posts(request: sanic.Request, blog: str):
    blog = urllib.parse.unquote(blog)

    if continuation := request.args.get("continuation"):
        continuation = urllib.parse.unquote(continuation)

    if before_id := request.args.get("before_id"):
        before_id = urllib.parse.unquote(before_id)

    blog = await get_blog_posts(request.app.ctx, blog, continuation=continuation, before_id=before_id)

    return await request.app.ctx.render(
        "blog/blog",
        context={
            "app": request.app,
            "blog": blog,
        },
    )


# Tags

@blogs.get("/tagged/<tag:str>")
@blogs.get("/tagged/<tag:str>/rss", name="_blog_tags_rss", ctx_rss=True)
async def _blog_tags(request: sanic.Request, blog: str, tag: str):
    blog = urllib.parse.unquote(blog)
    tag = urllib.parse.unquote(tag)

    if continuation := request.args.get("continuation"):
        continuation = urllib.parse.unquote(continuation)

    blog = await get_blog_posts(request.app.ctx, blog, continuation=continuation, tag=tag)

    return await request.app.ctx.render(
        "blog/blog",
        context={
            "app": request.app,
            "blog": blog,
            "tag": tag,
        },
    )


# Search

@blogs.get("/search/<query:str>")
@blogs.get("/search/<query:str>/rss", name="_blog_search_rss", ctx_rss=True)
async def _blog_search(request: sanic.Request, blog: str, query: str):
    blog = urllib.parse.unquote(blog)
    query = urllib.parse.unquote(query)

    if continuation := request.args.get("continuation"):
        continuation = urllib.parse.unquote(continuation)

    blog = (await get_blog_search_results(request.app.ctx, blog, query, continuation=continuation))

    return await request.app.ctx.render(
        "blog/blog_search",
        context={
            "app": request.app,
            "blog": blog,
            "blog_search_query": query,
        },
    )


@blogs.get("/search")
async def query_param_redirect(request: sanic.Request, blog: str):
    """Endpoint for /search to redirect q= queries to /search/<query>"""
    if query := request.args.get("q"):
        return sanic.redirect(request.app.url_for("blogs._blog_search", blog=blog, query=urllib.parse.quote(query, safe="")))
    else:
        return sanic.redirect(request.app.url_for("blogs._blog_posts", blog=blog))


# Redirects for /post/...

@blogs.get("/post/<post_id:int>")
async def redirect_slash_post_no_slug(request: sanic.Request, blog: str, post_id: str):
    return sanic.redirect(request.app.url_for("blog_post._blog_post", blog=blog, post_id=post_id))


@blogs.get("/post/<post_id:int>/<slug:str>")
async def redirect_slash_post(request: sanic.Request, blog: str, post_id: str, slug: str):
    return sanic.redirect(request.app.url_for("blog_post._blog_post_with_slug", blog=blog, post_id=post_id, slug=slug))
