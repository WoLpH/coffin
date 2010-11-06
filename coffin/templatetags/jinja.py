from django import template as django_template
from jinja2 import nodes, contextfunction, ext
from coffin.template import Library, Template

register = Library()


class JinjaInclude(django_template.Node):

    def __init__(self, filename):
        self.filename = filename

    def render(self, context):
        from coffin import shortcuts
        return shortcuts.render_to_string(self.filename, context)


class Jinja(django_template.Node):

    def __init__(self, template):
        self.template = template

    def render(self, context):
        return self.template.render(context)


class DjangoNoop(django_template.Node):

    def render(self, context):
        return ''


@register.tag
def jinja_include(parser, token):
    bits = token.contents.split()

    '''Check if a filename was given'''
    if len(bits) != 2:
        raise django_template.TemplateSyntaxError('%r tag requires the name'
            'of the template to be included included ' % bits[0])
    filename = bits[1]

    '''Remove quotes if used'''
    if filename[0] in ('"', "'") and filename[-1] == filename[0]:
        filename = bits[1:-1]

    return JinjaInclude(filename)


@register.tag
def jinja(parser, token):
    '''Create a Jinja template block

    Usage:
    {% jinja %}
    Although you're in a Django template, code here will be executed by Jinja
    {% end_jinja %}
    '''

    '''Generate the end tag from the currently used tag name'''
    end_tag = 'end_%s' % token.contents.split()[0]

    source_token = None

    tokens = []
    '''Convert all tokens to the string representation of them
    That way we can keep Django template debugging with Jinja and feed the
    entire string to Jinja'''
    while parser.tokens:
        token = parser.next_token()
        if not source_token and hasattr(token, 'source'):
            source_token = token

        if token.token_type == django_template.TOKEN_TEXT:
            tokens.append(token.contents)

        elif token.token_type == django_template.TOKEN_VAR:
            tokens.append(' '.join((
                django_template.VARIABLE_TAG_START,
                token.contents,
                django_template.VARIABLE_TAG_END,
            )))

        elif token.token_type == django_template.TOKEN_BLOCK:
            if token.contents == end_tag:
                break

            tokens.append(' '.join((
                django_template.BLOCK_TAG_START,
                token.contents,
                django_template.BLOCK_TAG_END,
            )))

        elif token.token_type == django_template.TOKEN_COMMENT:
            pass

        else:
            raise django_template.TemplateSyntaxError(
                'Unknown token type: "%s"' % token.token_type)

    '''If our token has a `source` attribute than template_debugging is
    enabled. If it's enabled create a valid source attribute for the Django
    template debugger'''
    if source_token:
        source = source_token.source[0], (source_token.source[1][0],
            source_token.source[1][1])
    else:
        source = None

    return Jinja(Template(''.join(tokens), source=source))


def django_noop(parser, token):
    return DjangoNoop()

register.tag('django', django_noop)
register.tag('end_django', django_noop)


class JinjaNoop(ext.Extension):
    tags = set(['jinja', 'end_jinja'])

    def parse(self, parser):
        while not parser.stream.current.type == 'block_end':
            parser.stream.next()
        return []

register.tag(JinjaNoop)


class Django(ext.Extension):
    tags = set(['django'])

    def preprocess(self, source, name, filename=None):
        source = source.replace('{% django %}', '{% django %}{% raw %}')
        source = source.replace('{% end_django %}',
            '{% endraw %}{% end_django %}')
        return source

    def parse(self, parser):
        lineno = parser.stream.next().lineno

        while not parser.stream.next().test('block_end'):
            pass

        body = nodes.Const(parser.stream.next().value)

        while not parser.stream.current.test('block_end'):
            parser.stream.next()

        return nodes.Output([
            self.call_method('_django', args=[body], kwargs=[]),
        ]).set_lineno(lineno=lineno)

    @contextfunction
    def _django(self, context, html):
        return django(context, html)

register.tag(Django)


@contextfunction
@register.object
def django(context, html):
    context = django_template.RequestContext(context['request'], context)
    return django_template.Template(html).render(context)

