import html
import re

from markdown_it import MarkdownIt

WIKI = re.compile(r"\[\[([a-z0-9][a-z0-9-]{0,99})\]\]")


def wiki_rule(state, silent):
    match = WIKI.match(state.src, state.pos)
    if not match or state.linkLevel > 0:
        return False
    if not silent:
        token = state.push("link_open", "a", 1)
        token.attrSet("href", "/?page=" + match.group(1))
        token.attrSet("data-wiki", match.group(1))
        label = state.push("text", "", 0)
        label.content = match.group(1).replace("-", " ")
        state.push("link_close", "a", -1)
    state.pos = match.end()
    return True


def parser():
    md = MarkdownIt("js-default", {"html": False, "linkify": False, "typographer": False})
    md.inline.ruler.before("link", "wiki", wiki_rule)

    def image_rule(self, tokens, index, options, env):
        # No embedded images means content cannot make remote tracking requests.
        label = self.renderInlineAsText(tokens[index].children, options, env)
        return f'<span class="image-placeholder">[Image omitted: {html.escape(label)}]</span>'

    def link_open(self, tokens, index, options, env):
        token = tokens[index]
        token.attrSet("rel", "noopener noreferrer")
        return self.renderToken(tokens, index, options, env)

    md.add_render_rule("image", image_rule)
    md.add_render_rule("link_open", link_open)
    return md


def render(body):
    return parser().render(body)


def references(body):
    # Parse actual inline syntax; links inside code fences/backticks are not references.
    targets = set()
    for block in parser().parse(body):
        for token in block.children or []:
            if token.type == "link_open" and token.attrGet("data-wiki"):
                targets.add(token.attrGet("data-wiki"))
    return targets


def search_query(value):
    # User input is always plain text, never the FTS query language. Prefix-match each term.
    words = re.findall(r"[^\W_]+", value, re.UNICODE)[:12]
    return " AND ".join('"' + word.replace('"', '""') + '"*' for word in words)
