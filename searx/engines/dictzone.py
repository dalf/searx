"""
 Dictzone

 @website     https://dictzone.com/
 @provide-api no
 @using-api   no
 @results     HTML (using search portal)
 @stable      no (HTML can change)
 @parse       url, title, content
"""

import re
from urllib.parse import urljoin
from searx.utils import is_valid_lang, html_fromstring

categories = ['general']
url = 'https://dictzone.com/{from_lang}-{to_lang}-dictionary/{query}'
weight = 100

parser_re = re.compile(b'.*?([a-z]+)-([a-z]+) ([^ ]+)$', re.I)
results_xpath = './/table[@id="r"]/tr'


async def request(query, params):
    m = parser_re.match(query)
    if not m:
        return params

    from_lang, to_lang, query = m.groups()

    from_lang = is_valid_lang(from_lang)
    to_lang = is_valid_lang(to_lang)

    if not from_lang or not to_lang:
        return params

    params['url'] = url.format(from_lang=from_lang[2],
                               to_lang=to_lang[2],
                               query=query.decode('utf-8'))

    return params


async def response(resp):
    results = []

    dom = await html_fromstring(resp.text)

    for k, result in enumerate(eval_xpath(dom, results_xpath)[1:]):
        try:
            from_result, to_results_raw = eval_xpath(result, './td')
        except:
            continue

        to_results = []
        for to_result in eval_xpath(to_results_raw, './p/a'):
            t = to_result.text_content()
            if t.strip():
                to_results.append(to_result.text_content())

        results.append({
            'url': resp.url.join('?%d' % k),
            'title': from_result.text_content(),
            'content': '; '.join(to_results)
        })

    return results
