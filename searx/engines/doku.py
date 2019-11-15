# Doku Wiki
#
# @website     https://www.dokuwiki.org/
# @provide-api yes
#              (https://www.dokuwiki.org/devel:xmlrpc)
#
# @using-api   no
# @results     HTML
# @stable      yes
# @parse       (general)    url, title, content

from urllib.parse import urlencode
from searx.engines.xpath import extract_text
from searx.utils import html_fromstring, eval_xpath

# engine dependent config
categories = ['general']  # TODO , 'images', 'music', 'videos', 'files'
paging = False
language_support = False
number_of_results = 5

# search-url
# Doku is OpenSearch compatible
base_url = 'http://localhost:8090'
search_url = '/?do=search'\
             '&{query}'
# TODO             '&startRecord={offset}'\
# TODO             '&maximumRecords={limit}'\


# do search-request
async def request(query, params):

    params['url'] = base_url +\
        search_url.format(query=urlencode({'id': query}))

    return params


# get response from search-request
async def response(resp):
    results = []

    doc = await html_fromstring(await resp.text())

    # parse results
    # Quickhits
    for r in eval_xpath(doc, '//div[@class="search_quickresult"]/ul/li'):
        try:
            res_url = eval_xpath(r, './/a[@class="wikilink1"]/@href')[-1]
        except:
            continue

        if not res_url:
            continue

        title = extract_text(eval_xpath(r, './/a[@class="wikilink1"]/@title'))

        # append result
        results.append({'title': title,
                        'content': "",
                        'url': base_url + res_url})

    # Search results
    for r in eval_xpath(doc, '//dl[@class="search_results"]/*'):
        try:
            if r.tag == "dt":
                res_url = eval_xpath(r, './/a[@class="wikilink1"]/@href')[-1]
                title = extract_text(eval_xpath(r, './/a[@class="wikilink1"]/@title'))
            elif r.tag == "dd":
                content = extract_text(eval_xpath(r, '.'))

                # append result
                results.append({'title': title,
                                'content': content,
                                'url': base_url + res_url})
        except:
            continue

        if not res_url:
            continue

    # return results
    return results
