---
title: pytest-obligation documentation
description: Test background work against crashes, retries, and duplicate delivery with executable conformance checks.
---

# pytest-obligation

Test background work against crashes, retries, and duplicate delivery with executable conformance checks.

[Get started](../package/docs/adopting.md){ .md-button .md-button--primary }
[Source on GitHub](https://github.com/gigaverse-app/pytest-obligation){ .md-button }

## Exercise the failures normal tests miss

Use pytest-obligation when your application's retry or recovery behavior needs
an executable contract. Bind the harness to observable application outcomes,
then exercise crashes, repeated delivery, and recovery against those outcomes.

- [Adopt the harness](../package/docs/adopting.md): connect a real application and declare the proof boundary.
- [Use the pytest plugin](../package/docs/pytest-plugin.md): collect and run the checks in your suite.
- [Understand crash histories](../package/docs/how-it-works.md): follow the failures and recovery steps being exercised.
- [Interpret a green result](../package/docs/what-a-green-result-means.md): separate verified, unassessed, and unsupported guarantees.
- [Avoid false greens](../package/docs/false-greens.md): check the controls that make a passing result meaningful.
- [Choose an integration](../package/docs/integrations.md): find the appropriate runtime and storage examples.

## Use the tools together

[Choose the tool for your problem](ecosystem.md). Each project works on its own;
combine them when you need both faster feedback and evidence that the required
work still happened.

## Versions and support

`latest` follows the main branch. Release-specific documentation is available
through Read the Docs when that release contains the site configuration.
Use [GitHub issues](https://github.com/gigaverse-app/pytest-obligation/issues) for a minimal
reproducer or a missing explanation. [Contributions](../CONTRIBUTING.md) are welcome.
