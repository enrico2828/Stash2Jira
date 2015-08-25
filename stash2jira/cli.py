from six.moves.configparser import SafeConfigParser
import csv
import inspect
from itertools import chain
import json
import os
from six.moves.urllib.parse import urlencode, urljoin
from six.moves.urllib import urlparse
import webbrowser
from os.path import expanduser
from six.moves import reduce

import click as click
import requests
from requests.auth import HTTPBasicAuth

BASE_CONFIG_DIR = expanduser("~")

CONFIG_VARS = [
    {'var': "stash_url", 'error': 'URL to Stash was not provided'},
    {'var': "jira_url", 'error': 'URL to JIRA was not provided'},
    {'var': "project", 'error': 'Project not specified'},
    {'var': "repo", 'error': 'Repository not specified'},
    {'var': "since", 'error': 'Start date not specified'},
    {'var': "until", 'error': 'End date not specified'}
]


def load_from_config(config_file):
    load_config = os.path.join(BASE_CONFIG_DIR, config_file)
    if os.path.exists(load_config):
        parser = SafeConfigParser()
        parser.read(load_config)
        config = dict()
        for _var in CONFIG_VARS:
            config[_var['var']] = parser.get('settings', _var['var'])
            if not config[_var]:
                click.echo(_var['error'])
        return config


def save_to_config(config_file, args, values, verbose=False):
    save_config = os.path.join(BASE_CONFIG_DIR, config_file)
    parser = SafeConfigParser()
    parser.read(save_config)
    if not os.path.exists(save_config):
        parser.add_section('settings')
    for i in args:
        if i in [c['var'] for c in CONFIG_VARS]:
            parser.set('settings', i, values[i])
    with open(save_config, 'w') as f:
        parser.write(f)
        if verbose:
            click.echo("Config file written to {}".format(save_config))


def get_proxy(proxy_url):
    res = urlparse(proxy_url)
    return {res['scheme'] + '://': res.geturl()}


def get_jira_keys(include_merge, since, stash_password, stash_url, stash_username, until):
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
    return jira_keys


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


def export_to_csv(export_csv, jira_password, jira_url, jira_username, jql_query, proxy):
    with open(export_csv, 'w') as f:
        f_csv = csv.writer(f)
        # TODO: externalize field choice to cli parameter
        headers = ["key", "issuetype", "status", "fixVersions"]
        rows = []
        f_csv.writerow(headers)
        total = 0
        start_at = 0
        while start_at < total or total == 0:
            try:
                # TODO: Inject config file in retrieve_jira_fields
                # TODO: get method call out of export_to_csv
                response_data = retrieve_jira_fields(headers, jira_password, jira_url, jira_username, jql_query,
                                                         proxy, start_at)
                for i in response_data["issues"]:
                    # TODO: Clean lambda from row data selection
                    rows.append((i["key"], i["fields"]["issuetype"]["name"], i["fields"]["status"]["name"],
                                 reduce(lambda a, b: a + "," + b, [nx["name"] for nx in i["fields"]["fixVersions"]
                                                                   if len(i["fields"]["fixVersions"])])))

                f_csv.writerows(rows)
                total = int(response_data["total"])
                start_at += int(response_data["maxResults"])
            except KeyError:
                pass


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
    response_data = r.json()
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
@click.option('--project', help='Name of the project', required=True)
@click.option('--repo', help='Name of the repository', required=True)
@click.option('--since', help='Optional: Display all commits since this commit or tag')
@click.option('--until', help='Optional: Display all commits until this branch, commit or tag')
@click.option('--include-merge', default=False,
              help='Optional: Whether merge commits should be included or not. Defaults to false', type=bool)
@click.option('--save-config', help="Specifiy the configuration file the given command line parameters should be saved "
                                    "to in the user's home directory")
@click.option('--load-config', help='Specifying the name of the config file to save/read. Given parameters override the'
                                    ' config file.')
@click.option('--export-csv', help='Specify a csv-file to export to.')
@click.option('--skip-browser', default=False, help='Whether to open the JIRA dashboard with the '
                                                    'results in the browser. Defaults to true', type=bool)
@click.option('--proxy', help='Specify which proxy to connect through e.g. https://proxy.url')
def main(stash_url, stash_username, stash_password, jira_url, jira_username, jira_password, project, repo, since,
         until, include_merge, save_config, load_config, export_csv, skip_browser, proxy):
    frame = inspect.currentframe()
    args, _, _, values = inspect.getargvalues(frame)

    save_to_config(save_config, args, values)
    config_obj = load_from_config(load_config)

    stash_url = urljoin(stash_url, 'stash/rest/api/1.0/projects/' + project + '/repos/' + repo + '/commits')

    # TODO: Inject config file in get_jira_keys
    jira_keys = get_jira_keys(include_merge, since, stash_password, stash_url, stash_username, until)

    s = set(chain(*jira_keys))
    jql_query = 'issuekey in (' + reduce(lambda a, b: a + ", " + b, s) + ')'

    if not skip_browser:
        open_in_browser(jira_url, jql_query, s)

    if export_csv:
        export_to_csv(export_csv, jira_password, jira_url, jira_username, jql_query, proxy)


if __name__ == '__main__':
    main()
