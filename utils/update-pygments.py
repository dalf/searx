#!/usr/bin/env python

# set path
from os.path import realpath, dirname, join
from pygments.formatters import HtmlFormatter


CSSCLASS = '.highlight'
RULE_CODE_LINENO = """{
    -webkit-touch-callout: none;
    -webkit-user-select: none;
    -khtml-user-select: none;
    -moz-user-select: none;
    -ms-user-select: none;
    user-select: none;
    cursor: default;
    
    &::selection {
        background: transparent; /* WebKit/Blink Browsers */
    }
    &::-moz-selection {
        background: transparent; /* Gecko Browsers */
    }
}"""


def get_output_filename(relative_name):
    return join(dirname(dirname(realpath(__file__))), relative_name)


def get_css(cssclass, style):
    result = ""
    css_text = HtmlFormatter(style=style).get_style_defs(cssclass)
    result += cssclass + ' .lineno ' + RULE_CODE_LINENO + '\n'
    for line in css_text.splitlines():
        element = line.split(' ', maxsplit=1)
        if len(element) != 2:
            result += element + '\n'
        else:
            selector, rules = element[0], element[1]
            if selector == 'pre':
                # skip pre definition
                continue
            if not selector.startswith(cssclass):
                selector = cssclass + ' ' + selector

            result += selector + ' ' + rules + '\n'
    return result

with open(get_output_filename('searx/static/less/pygments.less'), 'w') as f:
    f.write(get_css(CSSCLASS, 'default'))

with open(get_output_filename('searx/static/less/pygments-dark.less'), 'w') as f:
    f.write(get_css(CSSCLASS, 'monokai'))
