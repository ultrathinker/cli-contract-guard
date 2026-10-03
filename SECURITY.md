# Security Policy

## Reporting a vulnerability

Please report security issues through GitHub Private Vulnerability Reporting: open the
**Security** tab of this repository and choose **Report a vulnerability**. Do not open a
public issue for a suspected vulnerability.

## Supported versions

Only the latest release is supported.

## Scope

This plugin runs entirely on your machine, makes no network requests, and needs no accounts or services. Its scripts only read the contract and snapshot files you point them at and print a result; they never run your binary. Relevant reports are about a script reading or writing unexpected files, or handling the repository contents it analyses unsafely.
