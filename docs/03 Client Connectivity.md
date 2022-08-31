# Clients

## Python Embedded

Opteryx is an embeddable package into Python applications, scripts and Notebooks which implements a partial Python DBAPI (PEP-0249) interface.

~~~python
import opteryx
conn = opteryx.connect()
cur = conn.cursor()
cur.execute('SELECT * FROM $planets')
rows = cur.fetchall()
~~~

## Command Line Interface

Opteryx Command Line Interface (CLI) provides a terminal-based interactive shell for running queries. The CLI is a Python script usually run by invoking Python, like this:

~~~bash
python -m opteryx "SELECT * FROM \$planets"
~~~

Note that CLI will have character escaping requirements, such as a backslash before dollar signs.

Abridged usage guidance is available below:

~~~
Usage: python -m opteryx [OPTIONS] [SQL] 

--ast --no-ast    Display the AST for the query. [default: no-ast]
--help            Show the full help details.          
~~~

To see the full help and usage details for the CLI use the `--help` option:

~~~bash
python -m opteryx --help
~~~