"""Creates models that represents "packages" of Tumblr objects

Eg a regular timeline, or posts on a blog.

"""

from . import items
from .. import helpers, models

logger = helpers.LOGGER.getChild("parse")

class _CursorParser:
    def __init__(self, raw_cursor) -> None:
        self.target = raw_cursor

    @classmethod
    def process(cls, initial_data):
        if target := helpers.dig_dict(initial_data, ("links", "next")):
            return cls(target["queryParams"]).parse()
        else:
            return None

    def parse(self):
        return models.base.Cursor(
            cursor=self.target.get("cursor") or self.target.get("pageNumber"),
            limit=self.target.get("days"),
            days=self.target.get("query"),
            query=self.target.get("mode"),
            mode=self.target.get("timelineType"),
            skip_components=self.target.get("skipComponent"),
            reblog_info=self.target.get("reblogInfo"),
            post_type_filter=self.target.get("postTypeFilter")
        )


class TimelineParser:
    """Parses Tumblr's API response into a Timeline object"""
    def __init__(self, target) -> None:
        self.target = target

    @classmethod
    def process(cls, initial_data):
        if target := initial_data.get("timeline"):
            return cls(target).parse()
        else:
            return None

    def parse(self):
        # First let's begin with the cursor object
        cursor = _CursorParser.process(self.target)

        # Now the elements contained within
        elements = []
        total_raw_elements = len(self.target["elements"])
        for element_index, element in enumerate(self.target["elements"]):
            if result := items.parse_item(element, element_index, total_raw_elements):
                elements.append(result)

        return models.timelines.Timeline(
            elements=elements,
            next = cursor,
        )


class BlogTimelineParser:
    """Parses Tumblr's API response into a Blog object"""
    def __init__(self, target) -> None:
        self.target = target

    @classmethod
    def process(cls, initial_data):
        if initial_data.get("blog"):
            return cls(initial_data).parse()
        else:
            return None

    def parse(self):
        # First let's begin with the cursor object
        cursor = _CursorParser.process(self.target)

        # Then the blog info
        blog = items.BlogParser(self.target["blog"]).parse()

        # Now the posts contained within
        posts = []
        total_raw_posts = len(self.target["posts"])
        for post_index, post in enumerate(self.target["posts"]):
            if result := items.parse_item(post, post_index, total_raw_posts):
                posts.append(result)

        return models.timelines.BlogTimeline(
            blog_info=blog,
            posts=posts,
            total_posts = self.target.get("totalPosts"),
            next = cursor,
        )

    def parse_blog_search_timeline(self):
        cursor = _CursorParser.process(self.target)

        # Now the posts contained within
        posts = []
        total_raw_posts = len(self.target["posts"])
        for post_index, post in enumerate(self.target["posts"]):
            if result := items.parse_item(post, post_index, total_raw_posts):
                posts.append(result)

        return models.timelines.BlogTimeline(
            blog_info=posts[0].blog,
            posts=posts,
            total_posts = total_raw_posts,
            next = cursor,
        )

