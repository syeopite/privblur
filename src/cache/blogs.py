import orjson

from .base import AccessCache
from .. import priviblur_extractor


class BlogPostsCache(AccessCache):
    def __init__(self, ctx, blog, continuation, **kwargs):
        super().__init__(
            ctx=ctx,
            prefix=f"blog:{blog}",
            cache_ttl=ctx.PRIVIBLUR_CONFIG.cache.cache_blog_feed_for,
            continuation=continuation,
            **kwargs
        )

        self.blog = blog

    async def fetch(self):
        """Fetches blog posts from Tumblr"""
        return await self.ctx.TumblrAPI.blog_posts(self.blog, continuation=self.continuation, **self.kwargs)

    def parse(self, initial_results):
        return priviblur_extractor.parse_blog_timeline(initial_results)

    def parse_cached_json(self, json):
        return priviblur_extractor.models.timelines.BlogTimeline.from_json(json)

    def build_key(self):
        # blog:<blog_name>:<kwargs>
        path_to_cached_results = [self.prefix, ]
        for k,v in self.kwargs.items():
            if v:
                path_to_cached_results.append(f"{k}:{v}")

        return ':'.join(path_to_cached_results)


class BlogPostCache(AccessCache):
    def __init__(self, ctx, blog, post_id, **kwargs):
        super().__init__(
            ctx=ctx,
            prefix=f"blog:{blog}:post:{post_id}",
            cache_ttl=ctx.PRIVIBLUR_CONFIG.cache.cache_blog_post_for,
            **kwargs
        )

        self.blog = blog
        self.post_id = post_id

    async def fetch(self):
        return await self.ctx.TumblrAPI.blog_post(self.blog, self.post_id, **self.kwargs)

    def parse(self, initial_results):
        return priviblur_extractor.parse_timeline(initial_results)

    def build_key(self):
        # blog:<blog_name>:post:<post_id>:<kwargs>
        path_to_cached_results = [self.prefix, ]
        for k,v in self.kwargs.items():
            if v:
                path_to_cached_results.append(f"{k}:{v}")

        return ':'.join(path_to_cached_results)


class BlogSearchCache(BlogPostsCache):
    def __init__(self, ctx, blog, query, continuation, **kwargs):
        AccessCache.__init__(
            self,
            ctx=ctx,
            prefix=f"blog:{blog}:search:{query}",
            cache_ttl=ctx.PRIVIBLUR_CONFIG.cache.cache_blog_feed_for,
            continuation=continuation,
            **kwargs
        )

        self.blog = blog
        self.query = query

    async def fetch(self):
        return await self.ctx.TumblrAPI.blog_search(self.blog, self.query, continuation=self.continuation, **self.kwargs)

    def parse(self, initial_results):
        return priviblur_extractor.parse_blog_timeline(initial_results, is_search=True)

async def get_blog_posts(ctx, blog, continuation=None, **kwargs):
    blog_posts_cache = BlogPostsCache(ctx, blog, continuation, **kwargs)
    return await blog_posts_cache.get()


async def get_blog_search_results(ctx, blog, query, continuation=None, **kwargs):
    """Gets search results from a blog

    Returns a cached version when available, otherwise requests Tumblr.
    """
    blog_posts_cache = BlogSearchCache(ctx, blog, query, continuation, **kwargs)
    return await blog_posts_cache.get()


async def get_blog_post(ctx, blog, post_id, **kwargs):
    blog_post_cache = BlogPostCache(ctx, blog, post_id, **kwargs)
    return await blog_post_cache.get()
