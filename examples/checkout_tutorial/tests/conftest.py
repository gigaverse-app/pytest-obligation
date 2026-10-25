from sqlite_host import sqlite_worker_killer

from pytest_obligation import Host, configure

# The host: which packages are production code, and how to kill a worker right after each commit.
configure(Host(production_packages=frozenset({"checkout"}), worker_killer=sqlite_worker_killer))
