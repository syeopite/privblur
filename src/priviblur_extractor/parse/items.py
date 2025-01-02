
"""Parses individual items from Tumblr's JSON API into an object"""


import datetime

from .. import helpers, models

logger = helpers.LOGGER.getChild("parse")


class BlogParser:
    def __init__(self, target) -> None:
        self.target = target

    @classmethod
    def process(cls, initial_data):
        if initial_data.get("objectType") == "blog":
            return cls(initial_data["resources"][0]).parse()
        else:
            return None

    def parse_theme(self):
        """Parses theming information for the blog into a BlogTheme object"""
        target = self.target.get("theme")

        avatar_shape = target["avatarShape"]

        # Try to find one additional info. If not present then
        # `blog[fields]` was not passed, or did not include "theme" as a field.
        if header_image := target.get("headerImage"):
            header_info = models.blog.HeaderInfo(
                header_image,
                target["headerImageFocused"],
                target["headerImageScaled"],
            )

            return models.blog.BlogTheme(
                avatar_shape=avatar_shape,
                background_color=target["backgroundColor"],
                body_font=target["bodyFont"],
                header_info=header_info
            )
        else:
            # Return limited information otherwise
            return models.blog.BlogTheme(
                avatar_shape=avatar_shape,
                background_color=None,
                body_font=None,
                header_info=None
            )

    def parse(self):
        return models.blog.Blog(
            name=self.target["name"],
            avatar=self.target["avatar"],
            title=self.target["title"],
            url=self.target["url"],
            is_adult=self.target["isAdult"],
            description_npf=self.target["descriptionNpf"],
            uuid=self.target["uuid"],
            theme=self.parse_theme(),
            is_paywall_on=self.target["isPaywallOn"],
            active=self.target.get("active", True)
        )

    def parse_limited(self):
        """Parses a blog with only limited information

        This method is used when the field[blogs] parameter is set to only a couple attributes
        meaning that the resulting JSON is lacking many of the fields we use to parse.

        This is most noticeably seen in the blog attributes of various note types whom due to the
        set field[blogs] lacks many of the information we use to parse a Blog object.

        For now as this method will only be used to parse the blog information from notes
        we will assume that the blog name, avatar, and theming information is always present.

        TODO: Make models.blog.Blog and all related logic handle None instead of using default values here.
        TODO: Add tests for when field[blogs] lack attributes
        TODO: Discuss and figure out how to handle arbitrary values for (or don't) field[blogs]
        """
        return models.blog.Blog(
            name=self.target["name"],
            avatar=self.target["avatar"],
            title=self.target.get("title", ""),
            url=self.target.get("url", ""),
            is_adult=self.target.get("isAdult", False),
            description_npf=self.target.get("descriptionNpf", ""),
            uuid=self.target.get("uuid"),
            theme=self.parse_theme(),
            is_paywall_on=self.target.get("isPaywallOn", False),
            active=self.target.get("active", True)
        )


class PostParser:
    def __init__(self, target) -> None:
        self.target = target

    @classmethod
    def process(cls, initial_data):
        if initial_data.get("objectType") == "post":
            return cls(initial_data).parse()
        else:
            return None


    @staticmethod
    def parse_community_label(initial_data):
        community_labels = []
        if raw_labels := initial_data.get("communityLabels"):
            if raw_labels["hasCommunityLabel"]:
                for category in raw_labels["categories"]:
                    label = getattr(models.post.CommunityLabel, category.upper(), None)
                    if label:
                        community_labels.append(label)

                if not community_labels:
                    community_labels.append(models.post.CommunityLabel.MATURE)

        return community_labels

    def parse(self):
        # When we know that the target is a blog object there is no need to
        # pass it to .process to identify it
        blog = BlogParser(self.target["blog"]).parse()

        id = self.target["id"]

        note_count = self.target.get("noteCount")
        reply_count = self.target.get("replyCount")
        reblog_count = self.target.get("reblogCount")
        like_count = self.target.get("likeCount")

        note_type_counts = {
            "replies": reply_count,
            "reblogs": reblog_count,
            "likes": like_count
        }

        note_viewer_tabs = ("replies", "reblogs", "likes")
        default_note_viewer_tab = "replies"

        # Calculate default tab
        # If replies is empty fallback to the next tab and continue forth
        # until we find an not empty tab. If everything is empty then we default to replies

        for tab, counts in zip(("replies", "reblogs", "likes"), (reply_count, reblog_count, like_count)):
            if counts > 0:
                default_note_viewer_tab = tab
                break

        # We check multiple keys as a precautionary measure.
        if self.target.get("advertiserId") or self.target.get("adId") or self.target.get("adProviderId"):
            is_advertisement = True
        else:
            is_advertisement = False

        content = self.target["content"]
        layout = self.target["layout"]
        trail = self.target["trail"]

        trails = []
        for trail_post in trail:
            is_broken_trail = False

            if raw_trail_blog := trail_post.get("blog"):
                trail_blog = BlogParser(raw_trail_blog).parse()
            else:
                trail_blog = models.blog.BrokenBlog(
                    name=trail_post["brokenBlog"]["name"],
                    avatar=trail_post["brokenBlog"]["avatar"],
                )

                is_broken_trail = True

            trail_content = trail_post["content"]
            trail_layout = trail_post["layout"]

            if (trail_post_data := trail_post.get("post")) and not is_broken_trail:
                trail_post_id = trail_post_data["id"]
                trail_post_creation_date = datetime.datetime.fromtimestamp(trail_post_data["timestamp"], tz=datetime.timezone.utc)
            else:
                trail_post_id = None
                trail_post_creation_date = None

            trails.append(models.post.PostTrail(
                id=trail_post_id,
                blog=trail_blog,
                date=trail_post_creation_date,
                content=trail_content,
                layout=trail_layout,
            ))


        # Reblogged from data
        reblog_from_information = None
        reblog_root_information = None

        if reblogged_from_id := self.target.get("rebloggedFromId"):
            reblog_from_information = models.post.ReblogAttribution(
                post_id=reblogged_from_id,
                post_url=self.target["rebloggedFromUrl"],
                blog_name=self.target["rebloggedFromName"],
                blog_title=self.target["rebloggedFromTitle"],
            )

            if root_reblogged_from_id := self.target.get("rebloggedRootId"):
                reblog_root_information = models.post.ReblogAttribution(
                    post_id=root_reblogged_from_id,
                    post_url=self.target["rebloggedRootUrl"],
                    blog_name=self.target["rebloggedRootName"],
                    blog_title=self.target["rebloggedRootTitle"],
                )

        # Community label
        community_labels = self.parse_community_label(self.target)

        return models.post.Post(
            blog=blog,
            id=id,
            is_nsfw=self.target["isNsfw"],
            is_advertisement=is_advertisement,
            post_url=self.target["postUrl"],
            slug=self.target["slug"],
            date=datetime.datetime.fromtimestamp(self.target["timestamp"], tz=datetime.timezone.utc),
            tags=self.target["tags"],
            summary=self.target["summary"],

            content=content,
            layout=layout,
            trail=trails,

            display_avatar=self.target["displayAvatar"],

            reply_count=reply_count,
            reblog_count=reblog_count,
            like_count=like_count,
            note_count=note_count,

            default_note_viewer_tab=default_note_viewer_tab,

            reblog_from=reblog_from_information,
            reblog_root=reblog_root_information,

            community_labels=community_labels
        )


class ReplyNoteParser:
    def __init__(self, target) -> None:
            self.target = target

    @classmethod
    def process(cls, initial_data):
        if initial_data.get("type") == "reply":
            return cls(initial_data).parse()

    def parse(self):
        return models.post.ReplyNote(
            uuid=self.target["id"],
            reply_id=self.target["replyId"],
            date=datetime.datetime.fromtimestamp(self.target["timestamp"], tz=datetime.timezone.utc),

            content=self.target["content"],
            layout=self.target["layout"],

            blog=BlogParser(self.target["blog"]).parse_limited()
        )


class ReblogNoteParser:
    def __init__(self, target) -> None:
        self.target = target

    @classmethod
    def process(cls, initial_data):
        if initial_data.get("type") == "reblog":
            # If blog data isn't given under a blog object then
            # the note is likely a simple reblog note
            if initial_data.get("blogName"):
                return cls(initial_data).parse_simple()
            return cls(initial_data).parse()

    def parse(self) -> models.post.ReblogNote:
        return models.post.ReblogNote(
            uuid=self.target["id"],
            id=self.target["postId"],
            blog=BlogParser(self.target["blog"]).parse_limited(),

            content=self.target["content"],
            layout=self.target["content"],
            tags=self.target["tags"],

            reblogged_from=self.target["reblogParentBlogName"],
            date=datetime.datetime.fromtimestamp(self.target["timestamp"], tz=datetime.timezone.utc),
            community_labels=PostParser.parse_community_label(self.target),
        )

    def parse_simple(self):
        blog=models.blog.Blog(
            name=self.target["blogName"],
            avatar=[{"url": avatar_url} for avatar_url in list(self.target["avatarUrl"].values())],
            title=self.target["blogTitle"],
            url="",

            is_adult=False,
            description_npf="",
            uuid=self.target["blogUuid"],

            theme=models.blog.BlogTheme(self.target["avatarShape"]),
            is_paywall_on =False,
            active = True
        )

        return models.post.ReblogNote(
            uuid=self.target["blogUuid"],
            id=self.target["postId"],
            blog=blog,

            content=[],
            layout=[],
            tags=self.target["tags"],

            reblogged_from=self.target["reblogParentBlogName"],
            date=datetime.datetime.fromtimestamp(self.target["timestamp"], tz=datetime.timezone.utc),
            community_labels=[],
        )


class LikeNoteParser:
    def __init__(self, target) -> None:
        self.target = target

    @classmethod
    def process(cls, initial_data):
        if initial_data.get("type") == "like":
            return cls(initial_data).parse()

    def parse(self):
        return models.post.LikeNote(
            blog_name=self.target["blogName"],
            blog_uuid=self.target["blogUuid"],
            blog_title=self.target["blogTitle"],
            date=datetime.datetime.fromtimestamp(self.target["timestamp"], tz=datetime.timezone.utc),
            avatar=self.target["avatarUrl"],
        )


def parse_item(element, element_index=0, total_elements=1, use_parsers=None):
    """Parses an item from Tumblr API's JSON response into a more usable structure"""
    item_number = f"({element_index + 1}/{total_elements})"
    logger.debug(f"parse_item: Parsing item {item_number}")

    if not use_parsers:
        return PostParser.process(element)

    # use_parsers must be a iterable object
    for parser_index, parser in enumerate(use_parsers):
        logger.debug(f"parse_item: Attempting to match item {item_number} with `{parser.__name__}`"
                     f"({parser_index + 1}/{len(use_parsers)})...")

        if parsed_element := parser.process(element):
            return parsed_element

    return None
