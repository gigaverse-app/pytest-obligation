from sqlite_host import sqlite_worker_killer

from pytest_obligation import Host, configure

configure(Host(production_packages=frozenset({"checkout"}), worker_killer=sqlite_worker_killer))
