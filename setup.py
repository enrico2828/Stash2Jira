from distutils.core import setup

setup(
    name='Stash2JiraCLI',
    version='0.1',
    packages=[''],
    url='http://github.com/praetore/stash2jiracli',
    license='GPLv3',
    author='darryl',
    author_email='d.amatsetam@gmail.com',
    description='A command-line interface to get your repo data from Stash into Jira into a CSV',
    packages=['click', 'requests', 'six'],
)
