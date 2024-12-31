"""Extensions to npf-renderer to allow asynchronous code and some other custom styling"""

import dominate
import npf_renderer

from .helpers import url_handler


class NPFParser(npf_renderer.parse.Parser):
    def __init__(self, content, poll_callback=None):
        super().__init__(content, poll_callback)

    async def _parse_poll_block(self):
        poll_id = self.current.get("clientId") or self.current.get("client_id")
        if poll_id is None:
            raise ValueError("Invalid poll ID")

        question = self.current["question"]

        answers = {}
        for raw_ans in self.current["answers"]:
            answer_id = raw_ans.get("clientId") or raw_ans.get("client_id")
            answer_text = raw_ans.get("answerText") or raw_ans.get("answer_text")

            if answer_id is None or answer_text is None:
                raise ValueError("Invalid poll answer")

            answers[answer_id] = answer_text

        creation_timestamp = self.current["timestamp"]
        expires_after = self.current["settings"]["expireAfter"]

        votes = None
        total_votes = None

        if self.poll_result_callback:
            callback_response = await self.poll_result_callback(poll_id, creation_timestamp + expires_after)

            #{answer_id: vote_count}
            raw_results = callback_response["results"].items()
            processed_results = sorted(raw_results, key=lambda item: -item[1])

            votes_dict = {}
            total_votes = 0

            for index, results in enumerate(processed_results):
                vote_count = results[1]
                total_votes += vote_count

                if index == 0:
                    votes_dict[results[0]] = npf_renderer.objects.poll_block.PollResult(is_winner=True, vote_count=vote_count)
                else:
                    votes_dict[results[0]] = npf_renderer.objects.poll_block.PollResult(is_winner=False, vote_count=vote_count)

            votes = npf_renderer.objects.poll_block.PollResults(
                timestamp=callback_response["timestamp"],
                results=votes_dict
            )

        return npf_renderer.objects.poll_block.PollBlock(
            poll_id=poll_id,
            question=question,
            answers=answers,

            creation_timestamp=int(creation_timestamp),
            expires_after=int(expires_after),

            votes=votes,
            total_votes=total_votes,
        )

    async def __parse_block(self):
        """Parses a content block and appends the result to self.parsed_result

        Works by routing specific content types to corresponding parse methods
        """

        match self.current["type"]:
            case "text":
                block = self._parse_text()
            case "image":
                block = self._parse_image_block()
            case "link":
                block = self._parse_link_block()
            case "audio":
                block = self._parse_audio_block()
            case "video":
                block = self._parse_video_block()
            case "poll":
                block = await self._parse_poll_block()
            case _:
                block = unsupported.Unsupported(self.current["type"])

        self.parsed_result.append(block)

    async def parse(self):
        """Begins the parsing chain and returns the final list of parsed objects"""
        while self.next():
            await self.__parse_block()

        return self.parsed_result


class NPFFormatter(npf_renderer.format.Formatter):
    def __init__(
        self,
        content,
        layout=None,
        *,
        blog_name=None,
        post_id=None,
        url_handler=None,
        forbid_external_iframes=False,
        request=None,
    ):
        initialization_arguments = {
            "content": content,
            "layout": layout,
            "url_handler": url_handler,
            "forbid_external_iframes": forbid_external_iframes
        }

        if request:
            # Asking to expand a post is the reverse of asking to truncate a post
            initialization_arguments["truncate"] = not request.ctx.preferences.expand_posts

        super().__init__(**initialization_arguments)

        # We store the blog and post ID as to be able to render a link to
        # fetch poll results for JS disabled users
        self.blog_name = blog_name
        self.post_id = post_id

    def _format_poll(self, block):
        poll_html = super()._format_poll(block)
        poll_html["data-poll-id"] = block.poll_id

        poll_choices = poll_html[1][0]
        for index, answer_id in enumerate(block.answers.keys()):
            poll_choices[index]["data-answer-id"] = answer_id

        if (self.blog_name and self.post_id) and not block.votes:
            poll_footer = poll_html[2]
            no_script_fallback = dominate.tags.noscript(
                    dominate.tags.a(
                        "See Results",
                        href=f"/{self.blog_name}/{self.post_id}?fetch_polls=true",
                        cls="toggle-poll-results"
                    )
                )

            poll_footer.children.insert(0, no_script_fallback)

        return poll_html

    def _format_image(self, block, row_length=1, override_padding=None):
        image_html = super()._format_image(block, row_length, override_padding)

        try:
            image_element = image_html.getElementsByTagName("img")
            image_container = image_html.get(cls="image-container")

            if not (image_container and image_element):
                return image_html

            image_container = image_container[0]
            image_element = image_element[0]

            self._add_alt_text_element(block, image_container)
            self._linkify_images(image_container, image_element)
        except (ValueError, IndexError):
            pass

        return image_html

    def _linkify_images(self, image_container, image_element):
        """Wraps the given image element in a link"""
        index_of_image = image_container.children.index(image_element)
        image_container[index_of_image] = dominate.tags.a(image_element, href=image_element.src)

    def _add_alt_text_element(self, block, image_container):
        """Adds widget to show image alt text on image blocks"""
        if block.alt_text and block.alt_text != "image":
            image_container.add(
                dominate.tags.div(
                    dominate.tags.details(
                        dominate.tags.summary("ALT", title=f"{block.alt_text}"),
                        dominate.tags.p(block.alt_text)
                    ),
                    cls="img-alt-text"
                )
            )


async def format_npf(
    contents,
    layouts=None,
    blog_name=None,
    post_id=None,*,
    poll_callback=None,
    request=None
):
    """Wrapper around npf_renderer.format_npf for extra functionalities

    - Replaces internal Parser and Formatter with the modified variants above
    - Accepts extra arguments to add additional details to formatted results
    - Automatically sets Priviblur-specific rendering arguments

    Arguments (new):
        blog_name:
            Name of the blog the post comes from. This is used to render links to the parent post
        post_id:
            Unique ID of the post. This is used to render links to the parent post
        request:
            Sanic request object. Used to check user preferences
    """
    try:
        contents = await NPFParser(contents, poll_callback=poll_callback).parse()
        if layouts:
            layouts = npf_renderer.parse.LayoutParser(layouts).parse()

        contains_render_errors = False

        formatted = NPFFormatter(
            contents, layouts,
            blog_name=blog_name,
            post_id=post_id,
            url_handler=url_handler,
            forbid_external_iframes=True,
            request=request
        ).format()

    except npf_renderer.exceptions.RenderErrorDisclaimerError as e:
        contains_render_errors = True
        formatted = e.rendered_result
        assert formatted is not None
    except Exception as e:
        formatted = dominate.tags.div(cls="post-body has-error")
        contains_render_errors = True

    return contains_render_errors, formatted.render(pretty=False)
