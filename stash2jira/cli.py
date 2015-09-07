from collections import namedtuple
import csv
import inspect
from itertools import chain
import json
import os
import webbrowser
from os.path import expanduser

import click as click
import requests
from requests.auth import HTTPBasicAuth

from six import iteritems, viewitems

from six.moves import reduce
from six.moves.configparser import SafeConfigParser
from six.moves.urllib.parse import urlencode, urljoin, urlparse

BASE_CONFIG_DIR = expanduser("~")

CONFIG_VARS = [
    {'var': "stash_url", 'error': 'URL to Stash was not provided'},
    {'var': "jira_url", 'error': 'URL to JIRA was not provided'},
    {'var': "project", 'error': 'Project not specified'},
    {'var': "repo", 'error': 'Repository not specified'},
    {'var': "since", 'error': 'Start date not specified'},
    {'var': "until", 'error': 'End date not specified'}
]


def load_from_config(config_file, args, values):
    config = dict()
    if config_file:
        load_config = os.path.join(BASE_CONFIG_DIR, config_file)
        if os.path.exists(load_config):
            parser = SafeConfigParser()
            parser.read(load_config)
            for _var in CONFIG_VARS:
                config[_var['var']] = parser.get('settings', _var['var'])

    for _var in CONFIG_VARS:
        if _var['var'] in args:
            config[_var['var']] = values[_var['var']]
        if _var["var"] not in config:
            click.echo(_var['error'])
    return namedtuple('GenericDict', config.keys())(**config)


def save_to_config(config_file, config_obj, verbose=False):
    save_config = os.path.join(BASE_CONFIG_DIR, config_file)
    parser = SafeConfigParser()
    parser.read(save_config)
    if not os.path.exists(save_config):
        parser.add_section('settings')
    click.echo(config_obj)
    for k, v in viewitems(config_obj._asdict()):
        if v is not None:
            parser.set('settings', k, v)
    with open(save_config, 'w') as f:
        parser.write(f)
        if verbose:
            click.echo("Config file written to {}".format(save_config))


def get_proxy(proxy_url):
    res = urlparse(proxy_url)
    return {res.scheme: res.geturl()}


# TODO: Inject config file in get_jira_keys
def get_jira_keys(include_merge, since, stash_password, stash_url, stash_username, until, project, repo):
    stash_url = urljoin(stash_url, 'stash/rest/api/1.0/projects/' + project + '/repos/' + repo + '/commits')
    last_page = False
    start = 0
    jira_keys = list()
    while not last_page:
        params = {
            'since': since,
            'until': until,
            'start': start
        }

        r = requests.get(stash_url, params=params, auth=HTTPBasicAuth(username=stash_username, password=stash_password))
        response_data = json.loads(r.text)
        for c in response_data['values']:
            parents_num = len(c['parents'])
            if 'attributes' in c.keys() and (parents_num < 2 or include_merge):
                key_ = c['attributes']['jira-key']
                jira_keys.append(key_)
        last_page = response_data['isLastPage']
        if not last_page:
            start = response_data['nextPageStart']
    return set(chain(*jira_keys))


def open_in_browser(jira_url, jql_query, s, verbose=False):
    if len(s) < 500:
        params = {
            'jql': jql_query
        }
        b_url = urljoin(urljoin(jira_url, 'images'), '?' + urlencode(params))
        webbrowser.open(b_url)
    else:
        if verbose:
            click.echo("Too much data to handle in browser")


def export_to_csv(export_csv, rows):
    with open(export_csv, 'w') as f:
        f_csv = csv.writer(f)
        f_csv.writerows(rows)


def find(key, dictionary):
    for k, v in iteritems(dictionary):
        if k == key:
            click.echo(v)
            yield v
        elif isinstance(v, dict):
            for result in find(key, v):
                yield result
        elif isinstance(v, list):
            for d in v:
                for result in find(key, d):
                    yield result


# TODO: Inject config file in connect_to_jira
def connect_to_jira(jira_password, jira_url, jira_username, jql_query, proxy):
    total = 0
    start_at = 0
    # TODO: Use this: http://funcy.readthedocs.org/en/latest/colls.html#get_in
    headers = ("key", "issuetype", "status", "fixVersions", "issuelinks")
    rows = [headers]
    while start_at < total or total == 0:
        try:
            response_data = retrieve_jira_fields(headers, jira_password, jira_url, jira_username, jql_query,
                                                 proxy, start_at)
            for i in response_data["issues"]:
                delimiter = "/"
                row_data = [list(find(k, i)) for k in headers]
                click.echo(row_data)
                rows.append(row_data)

            total = int(response_data["total"])
            start_at += int(response_data["maxResults"])
        except KeyError:
            pass
    return tuple(rows)


# TODO: Inject config file in retrieve_jira_fields
def retrieve_jira_fields(headers, jira_password, jira_url, jira_username, jql_query, proxy, start_at):
    c_url = urljoin(jira_url, 'rest/api/2/search')
    data = {
        "jql": jql_query,
        "startAt": start_at,
        "fields": headers
    }
    headers = {
        "Content-type": "application/json"
    }
    r = requests.post(c_url, headers=headers, data=json.dumps(data),
                      auth=HTTPBasicAuth(jira_username, jira_password),
                      proxies=get_proxy(proxy))
    if r.ok:
        response_data = r.json()
    else:
        return {}
    return response_data


@click.command()
@click.option('--stash-url', help='URL to Stash REST API to connect to, e.g. http://stash.example.com/stash')
@click.option('--stash-username', help='Username to connect to Stash REST API', required=True)
@click.option('--stash-password', help='Password to connect to Stash REST API', prompt=True, hide_input=True,
              confirmation_prompt=False)
@click.option('--jira-url', help='Base URL for output link, e.g. https://jira.example.com')
@click.option('--jira-username', help='Username to connect to JIRA REST API')
@click.option('--jira-password', help='Password to connect to JIRA REST API', prompt=True, hide_input=True,
              confirmation_prompt=False)
@click.option('--project', help='Name of the project')
@click.option('--repo', help='Name of the repository')
@click.option('--since', help='Optional: Display all commits since this commit or tag')
@click.option('--until', help='Optional: Display all commits until this branch, commit or tag')
@click.option('--include-merge', default=False,
              help='Optional: Whether merge commits should be included or not. Defaults to false', type=bool)
@click.option('--save-config', help="Specifiy the configuration file the given command line parameters should be saved "
                                    "to in the user's home directory")
@click.option('--load-config', help='Specifying the name of the config file to save/read. Given parameters override the'
                                    ' config file.')
@click.option('--export-csv', help='Specify a csv-file to export to.')
@click.option('--skip-browser', default=True, help='Whether to open the JIRA dashboard with the '
                                                   'results in the browser. Defaults to true', type=bool)
@click.option('--proxy', help='Specify which proxy to connect through e.g. https://proxy.url')
def main(stash_url, stash_username, stash_password, jira_url, jira_username, jira_password, project, repo, since,
         until, include_merge, save_config, load_config, export_csv, skip_browser, proxy):
    frame = inspect.currentframe()
    args, _, _, values = inspect.getargvalues(frame)

    click.echo("Loading config file")
    config_obj = load_from_config(load_config, args, values)

    click.echo("Saving config file")
    save_to_config(save_config, config_obj)

    click.echo("Connecting to Stash API")
    jira_keys = get_jira_keys(include_merge, since, stash_password, stash_url, stash_username, until, project, repo)
    jql_query = 'issuekey in (' + reduce(lambda a, b: a + ", " + b, jira_keys) + ')'

    if not skip_browser:
        open_in_browser(jira_url, jql_query, jira_keys)

    click.echo("Connecting to Jira API")
    rows = connect_to_jira(jira_password, jira_url, jira_username, jql_query, proxy)

    if export_csv:
        click.echo("Exporting to csv")
        export_to_csv(export_csv, rows)


if __name__ == '__main__':
    main()
