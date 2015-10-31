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


# OS-independent location of home folder
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
    """
    Load config from user's home folder, and load into config object. If values are given during runtime that conflict
    with values in config file, the config file values are overwritten.

    :param config_file: Name of an existing config file
    :param args: Array of values containing argument names from main
    :param values: Array of values containing values from arguments from main
    :return: key/value pairs of args/values
    """
    # TODO: Handle args not existing in user config file and passed args
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
    """
    Write all the values in the config object to a given file in the user's home folder

    :param config_file: Name of config file to store in user's home folder
    :param config_obj: The config object to export to config file
    :param verbose: Specify if stdout should display a message
    :return:
    """
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
    """
    Parse the given url in a format that can be passed to the requests module's proxy parameter
    :param proxy_url: The proxy url to parse
    :return: The proxy dict object in a format that can be understood by requests
    """
    res = urlparse(proxy_url)
    return {res.scheme: res.geturl()}


# TODO: Inject config file in get_jira_keys
def get_jira_keys(include_merge, since, stash_password, stash_url, stash_username, until, project, repo):
    """
    Get the issue keys from JIRA that correspond with the passed args

    :param include_merge:
    :param since:
    :param stash_password:
    :param stash_url:
    :param stash_username:
    :param until:
    :param project:
    :param repo:
    :return:
    """
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


# TODO: Inject config object in open_in_browser
def open_in_browser(jira_url, jql_query, jira_keys, verbose=False):
    """
    Open browser in JIRA with the retrieved keys from Stash as url-params

    :param jira_url:
    :param jql_query:
    :param jira_keys:
    :param verbose:
    :return:
    """
    if len(jira_keys) < 500:
        params = {
            'jql': jql_query
        }
        b_url = urljoin(urljoin(jira_url, 'issues'), '?' + urlencode(params))
        webbrowser.open(b_url)
    else:
        if verbose:
            click.echo("Too much data to handle in browser")


# TODO: Inject config object in export_to_csv
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
def connect_to_jira(jira_password, jira_url, jira_username, jql_query, proxy, verbose=False):
    """
    Connect to JIRA's REST API and parse the given JQL-query

    :param jira_password:
    :param jira_url:
    :param jira_username:
    :param jql_query:
    :param proxy:
    :return:
    """
    # TODO: Seriously, implement the jira python package: https://pypi.python.org/pypi/jira
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
                if verbose:
                    click.echo(row_data)
                rows.append(row_data)

            total = int(response_data["total"])
            start_at += int(response_data["maxResults"])
        except KeyError:
            pass
    return tuple(rows)


# TODO: Inject config file in retrieve_jira_fields
def retrieve_jira_fields(headers, jira_password, jira_url, jira_username, jql_query, proxy, start_at):
    """


    :param headers:
    :param jira_password:
    :param jira_url:
    :param jira_username:
    :param jql_query:
    :param proxy:
    :param start_at:
    :return:
    """
    url = urljoin(jira_url, 'rest/api/2/search')
    data = {
        "jql": jql_query,
        "startAt": start_at,
        "fields": headers
    }
    headers = {
        "Content-type": "application/json"
    }
    r = requests.post(url, headers=headers, data=json.dumps(data),
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
@click.option('--save-config',
              help="Specifiy the configuration file the given command line parameters should be saved to in the user's home directory")
@click.option('--load-config',
              help="Specifying the name of the config file to save/read. Given parameters override the config file.")
@click.option('--export-csv', help='Specify a csv-file to export to')
@click.option('--skip-browser', default=True,
              help="Whether to open the JIRA dashboard with the results in the browser. Defaults to true", type=bool)
@click.option('--proxy', help='Specify which proxy to connect through e.g. https://proxy.url')
def main(stash_url, stash_username, stash_password, jira_url, jira_username, jira_password, project, repo, since,
         until, include_merge, save_config, load_config, export_csv, skip_browser, proxy):
    """
    :param stash_url: URL to Stash REST API to connect to, e.g. http://stash.example.com/stash
    :param stash_username: Username to connect to Stash REST API
    :param stash_password: Password to connect to Stash REST API
    :param jira_url: Base URL for output link, e.g. https://jira.example.com
    :param jira_username: Username to connect to JIRA REST API
    :param jira_password: Password to connect to JIRA REST API
    :param project: Name of the project
    :param repo: Name of the repository
    :param since: Optional: Display all commits since this commit or tag
    :param until: Optional: Display all commits until this branch, commit or tag
    :param include_merge: Optional: Whether merge commits should be included or not. Defaults to false
    :param save_config: Specifiy the configuration file the given command line parameters should be saved to in the user's home directory
    :param load_config: Specifiy the configuration file the given command line parameters should be saved to in the user's home directory
    :param export_csv: Specify a csv-file to export to
    :param skip_browser: Whether to open the JIRA dashboard with the results in the browser. Defaults to true
    :param proxy: Specify which proxy to connect through e.g. https://proxy.url
    """

    # get the arguments and values from main in arrays
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
