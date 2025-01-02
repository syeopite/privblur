import enum
import urllib.parse

import sanic
from sanic import request
import sanic_ext

from ... import cache, priviblur_extractor

blog_post_bp = sanic.Blueprint("blog_post", url_prefix="/<post_id:int>")

class PostNoteTypes(enum.Enum):
    REPLIES = 0
    REBLOGS = 1
    LIKES = 2


def get_blog_post_path(request):
    """Returns the path to the user requested blog post endpoint"""
    post_path = f"/{'/'.join(str(path_component) for path_component in request.match_info.values())}"
    if request.query_string:
        post_path += f"?{request.query_string}"

    return post_path


@blog_post_bp.on_request
async def handle_post_slug(request):
    """Validates that the user requested endpoint contains a valid slug

    Redirects to a valid URL if otherwise
    """
    # Ensure that the slug is correct when present
    blog = urllib.parse.unquote(request.match_info["blog"])
    post_id = request.match_info["post_id"]

    post = (await cache.get_blog_post(request.app.ctx, blog, post_id)).elements[0]

    # Check if slug is passed
    if slug := request.match_info.get("slug"):
        slug = urllib.parse.unquote(slug)

        # Redirect to the correct slug if the given slug does not match the post's slug
        if slug != post.slug:
            # Unless of course the post doesn't have a slug in the first place in which
            # we'll redirect to the path without a slug
            if not post.slug:
                del request.match_info["slug"]
                return sanic.redirect(get_blog_post_path(request))
            else:
                # Correct post slug and redirect
                request.match_info["slug"] = post.slug
                return sanic.redirect(get_blog_post_path(request))
    elif post.slug:
        request.match_info["slug"] = post.slug
        return sanic.redirect(get_blog_post_path(request))

    request.ctx.post_path = request.path
    request.ctx.parsed_post = post


@blog_post_bp.on_request
async def handle_post_args(request):
    request.ctx.breq_jinja_context = jinja_context = {
        "post_url": request.ctx.post_path[1:]
    }

    args = request.args

    if (fetch_polls := args.get("fetch_polls")) and sanic.utils.str_to_bool(fetch_polls):
        jinja_context["request_poll_data"] = True
    else:
        jinja_context["request_poll_data"] = False

    if (rss_feed := args.get("rss_feed")) and sanic.utils.str_to_bool(rss_feed):
        request.ctx.rss = True
        request.ctx.page_url = f"{request.app.ctx.PRIVIBLUR_CONFIG.deployment.domain or ''}{request.ctx.post_path}"

    # Requesting post notes?
    if note_type := args.get("note_viewer"):
        note_type = getattr(PostNoteTypes, note_type.upper(), None)
        match note_type:
            case PostNoteTypes.REPLIES:
                return await _blog_post_replies(request, **request.match_info)
            case PostNoteTypes.REBLOGS:
                return await blog_post_reblog_notes(request, **request.match_info)
            case PostNoteTypes.LIKES:
                return await blog_post_like_notes(request, **request.match_info)


@blog_post_bp.get("/")
@blog_post_bp.get("/<slug:str>", name="_blog_post_with_slug")
async def _blog_post(request: sanic.Request, **kwargs):
    blog_info = priviblur_extractor.models.timelines.BlogTimeline(request.ctx.parsed_post.blog, (), None, None)

    if note_type := request.args.get("note_viewer"):
        note_type = getattr(PostNoteTypes, note_type.upper(), None)
        match note_type:
            case PostNoteTypes.REPLIES:
                return await _blog_post_replies(request, **kwargs)
            case PostNoteTypes.REBLOGS:
                return await blog_post_reblog_notes(request, **kwargs)
            case PostNoteTypes.LIKES:
                return await blog_post_like_notes(request, **kwargs)

    return await request.app.ctx.render(
        "blog/blog_post",
        context={
            "app": request.app,
            "blog": blog_info,
            "element": request.ctx.parsed_post,
        }
    )


async def _blog_post_replies(request: sanic.Request, blog: str, post_id: str, **kwargs):
    blog = urllib.parse.unquote(blog)
    if slug := kwargs.get("slug"):
        slug = urllib.parse.unquote(slug)

    args = request.get_args(keep_blank_values=True)

    latest = True if "latest" in args else False

    if after_id := args.get("after"):
        parsed_notes = await cache.get_post_notes(
            request.app.ctx,
            blog,
            post_id,
            "replies",
            request.app.ctx.TumblrAPI.blog_post_replies,
            after_id=after_id,
            latest=latest
        )
    else:
        parsed_notes = await cache.get_post_notes(
            request.app.ctx,
            blog,
            post_id,
            "replies",
            request.app.ctx.TumblrAPI.blog_post_replies,
            latest=latest
        )

    return await request.app.ctx.render(
        "post/notes/viewer/viewer_page",
        context={
            "app": request.app,
            "blog_info": request.ctx.parsed_post.blog,
            "post_id": str(post_id),
            "latest": latest,
            "note_type": "replies",
            "notes": parsed_notes
        }
    )


async def blog_post_reblog_notes(request: sanic.Request, blog: str, post_id: str, **kwargs):
    blog = urllib.parse.unquote(blog)
    if slug := kwargs.get("slug"):
        slug = urllib.parse.unquote(slug)

    args_to_tumblr_api_wrapper = {}

    args = request.get_args(keep_blank_values=True)

    reblog_note_types = request.app.ctx.TumblrAPI.config.ReblogNoteTypes

    match reblog_filter := args.get("reblog_filter"):
        case "reblogs_with_comments":
            mode = reblog_note_types.REBLOGS_WITH_COMMENTS
        case "reblogs_with_content_comments":
            mode = reblog_note_types.REBLOGS_WITH_CONTENT_COMMENTS
        case "reblogs_only":
            mode = reblog_note_types.REBLOGS_ONLY
        case _:
            reblog_filter = None
            mode = None

    if mode == reblog_note_types.REBLOGS_ONLY:
        args_to_tumblr_api_wrapper["return_likes"] = False
    else:
        if mode:
            args_to_tumblr_api_wrapper["mode"] = mode

    if before_timestamp := args.get("before_timestamp"):
        args_to_tumblr_api_wrapper["before_timestamp"] = before_timestamp

    if mode == reblog_note_types.REBLOGS_ONLY:
        parsed_notes = await cache.get_post_notes(
            request.app.ctx,
            blog,
            post_id,
            "reblogs",
            request.app.ctx.TumblrAPI.blog_notes,
            **args_to_tumblr_api_wrapper,
        )
    else:
        parsed_notes = await cache.get_post_notes(
            request.app.ctx,
            blog,
            post_id,
            "reblogs",
            request.app.ctx.TumblrAPI.blog_post_notes_timeline,
            **args_to_tumblr_api_wrapper,
        )


    return await request.app.ctx.render(
        "post/notes/viewer/viewer_page",
        context={
            "app": request.app,
            "blog_info": request.ctx.parsed_post.blog,
            "post_id": str(post_id),
            "note_type": "reblogs",
            "reblog_filter": reblog_filter,
            "notes": parsed_notes
        }
    )


async def blog_post_like_notes(request: sanic.Request, blog: str, post_id: str, **kwargs):
    blog = urllib.parse.unquote(blog)
    if slug := kwargs.get("slug"):
        slug = urllib.parse.unquote(slug)

    parsed_notes = await cache.get_post_notes(
        request.app.ctx,
        blog,
        post_id,
        "likes",
        request.app.ctx.TumblrAPI.blog_notes,
        before_timestamp=request.args.get("before_timestamp"),
    )

    return await request.app.ctx.render(
        "post/notes/viewer/viewer_page",
        context={
            "app": request.app,
            "blog_info": request.ctx.parsed_post.blog,
            "post_id": str(post_id),
            "note_type": "likes",
            "notes": parsed_notes
        }
    )
