# Security policy

## Imagecraft and images

Imagecraft is a tool that generates system images. Images are typically composed of
Ubuntu software and application code, and without regular maintenance and updates they
can become vulnerable.

An image's author or maintainer is the sole party responsible for its security. Image
authors should be diligent and keep the software inside their images up-to-date with the
latest releases, security patches, and security measures.

Any vulnerabilities found in an image should be reported to the image's author or
maintainer.

## Build isolation

In typical operation, Imagecraft makes use of tools like [LXD] and [Multipass] to create
isolated build environments. Imagecraft itself provides no extra security, relying on
these tools to provide secure sandboxing. The security of these build environments
are the responsibility of these tools and should be reported to their respective
project maintainers.

Additionally, [destructive] builds are designed to give full access to the running host
and are not isolated in any way.

## Supported versions

Imagecraft is still in development and has no long-term support releases. As such,
only the latest released version is considered supported.

## Reporting a vulnerability

To report a security issue, file a [Private Security Report] with a description of the
issue, the steps you took to create the issue, affected versions, and, if known,
mitigations for the issue.

The [Ubuntu Security disclosure and embargo policy] contains more information about
what you can expect when you contact us and what we expect from you.

[destructive]: https://documentation.ubuntu.com/imagecraft/en/stable/reference/commands/pack/#pack
[Private Security Report]: https://github.com/canonical/imagecraft/security/advisories/new
[LXD]: https://canonical.com/lxd
[Multipass]: https://canonical.com/multipass
[Ubuntu Security disclosure and embargo policy]: https://ubuntu.com/security/disclosure-policy
