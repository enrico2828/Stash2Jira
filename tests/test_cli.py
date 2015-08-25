import pytest
from click.testing import CliRunner
from stash2jira import cli


# TODO: write mock jira connection result
# TODO: write mock stash connection result
# TODO: create tests for config
# TODO: create test for csv export

@pytest.fixture
def runner():
    return CliRunner()


def test_cli(runner):
    result = runner.invoke(cli.main)
    assert result.exit_code == 0
    assert not result.exception
    assert result.output.strip() == 'Hello, world.'


def test_cli_with_option(runner):
    result = runner.invoke(cli.main, ['--as-cowboy'])
    assert not result.exception
    assert result.exit_code == 0
    assert result.output.strip() == 'Howdy, world.'


def test_cli_with_arg(runner):
    result = runner.invoke(cli.main, ['Darryl'])
    assert result.exit_code == 0
    assert not result.exception
    assert result.output.strip() == 'Hello, Darryl.'


def test_load_config(runner):
    pass


def test_save_config(runner):
    pass


def test_export_to_csv(runner):
    pass