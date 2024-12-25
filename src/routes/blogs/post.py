import enum
import urllib.parse

import sanic
import sanic_ext

from ... import cache, priviblur_extractor

blog_post_bp = sanic.Blueprint("blog_post", url_prefix="/<post_id:int>")

class PostNoteTypes(enum.Enum):
    REPLIES = 0
    REBLOGS = 1
    LIKES = 2


def get_blog_post_path(request):
    """Returns the path to the user requested blog post endpoint"""
    return f"/{'/'.join(str(path_component) for path_component in request.match_info.values())}"


def get_post_url(blog, post_id, slug = None):
    if slug:
        return urllib.parse.quote(f"{blog}/{post_id}/{slug}")
    else:
        return urllib.parse.quote(f"{blog}/{post_id}/")


@blog_post_bp.on_request
async def before_blog_post_request(request):
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
        # If the post has a slug but a slug is not given then we'll need to redirect
        # the user to a path with the slug due to how Tumblr works.

        current_path = [str(path_component) for path_component in request.match_info.values()]

        # Current path is `/<blog>/<post_id>/*`
        # as such the slug needs to be inserted at position 2
        current_path.insert(2, post.slug)

        return sanic.redirect(f"/{'/'.join(current_path)}")

    request.ctx.parsed_post = post


@blog_post_bp.get("/")
@blog_post_bp.get("/<slug:str>", name="_blog_post_with_slug")
async def _blog_post(request: sanic.Request, **kwargs):
    blog_info = priviblur_extractor.models.timelines.BlogTimeline(request.ctx.parsed_post.blog, (), None, None)

    if note_type := request.args.get("note_viewer"):
        note_type = getattr(PostNoteTypes, note_type.upper())
        match note_type:
            case PostNoteTypes.REPLIES:
                return await _blog_post_replies(request, **kwargs)
            case PostNoteTypes.REBLOGS:
                return await blog_post_reblog_notes(request, **kwargs)
            case PostNoteTypes.LIKES:
                return await blog_post_like_notes(request, **kwargs)

    post_url = get_post_url(**kwargs)

    if request.args.get("fetch_polls") in ("1", "true"):
        fetch_poll_results = True
    else:
        fetch_poll_results = False

    return await sanic_ext.render(
        "blog/blog_post.jinja",
        context={
            "app": request.app,
            "blog": blog_info,
            "post_url": post_url,
            "element": request.ctx.parsed_post,
            "request_poll_data" : fetch_poll_results,
        }
    )


async def _blog_post_replies(request: sanic.Request, blog: str, post_id: str, **kwargs):
    blog = urllib.parse.unquote(blog)
    if slug := kwargs.get("slug"):
        slug = urllib.parse.unquote(slug)

    post_url = get_post_url(blog, post_id, slug)

    args = request.get_args(keep_blank_values=True)

    latest = True if "latest" in args else False

    if after_id := args.get("after"):
        notes = await request.app.ctx.TumblrAPI.blog_post_replies(blog, post_id, after_id=after_id, latest=latest)
    else:
        notes = await request.app.ctx.TumblrAPI.blog_post_replies(blog, post_id, latest=latest)

    parsed_notes = priviblur_extractor.parse_note_timeline(notes)

    return await sanic_ext.render(
        "post/notes/viewer/viewer_page.jinja",
        context={
            "app": request.app,
            "path_of_viewer_component_to_use": "post/notes/viewer/replies.jinja",
            "blog_name": blog,
            "post_id": str(post_id),
            "latest": latest,
            "post_url": post_url,
            "notes": parsed_notes
        }
    )


async def blog_post_reblog_notes(request: sanic.Request, blog: str, post_id: str, **kwargs):
    blog = urllib.parse.unquote(blog)
    if slug := kwargs.get("slug"):
        slug = urllib.parse.unquote(slug)

    post_url = get_post_url(blog, post_id, slug)

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
        # The results for "reblogs only" filtering is fetched from a different endpoint
        notes = await request.app.ctx.TumblrAPI.blog_notes(blog, post_id, **args_to_tumblr_api_wrapper)
    else:
        notes = await request.app.ctx.TumblrAPI.blog_post_notes_timeline(blog, post_id, **args_to_tumblr_api_wrapper)

    parsed_notes = priviblur_extractor.parse_note_timeline(notes)

    return await sanic_ext.render(
        "post/notes/viewer/viewer_page.jinja",
        context={
            "app": request.app,
            "path_of_viewer_component_to_use": "post/notes/viewer/reblogs.jinja",
            "blog_name": blog,
            "post_id": str(post_id),
            "post_url": post_url,
            "reblog_filter": reblog_filter,
            "notes": parsed_notes
        }
    )


async def blog_post_like_notes(request: sanic.Request, blog: str, post_id: str, **kwargs):
    blog = urllib.parse.unquote(blog)
    if slug := kwargs.get("slug"):
        slug = urllib.parse.unquote(slug)

    post_url = get_post_url(blog, post_id, slug)

    notes = await request.app.ctx.TumblrAPI.blog_notes(
        blog,
        post_id,
        before_timestamp=request.args.get("before_timestamp")
    )
    parsed_notes = priviblur_extractor.parse_note_timeline(notes)

    return await sanic_ext.render(
        "post/notes/viewer/viewer_page.jinja",
        context={
            "app": request.app,
            "path_of_viewer_component_to_use": "post/notes/viewer/likes.jinja",
            "blog_name": blog,
            "post_id": str(post_id),
            "post_url": post_url,
            "notes": parsed_notes
        }
    )
