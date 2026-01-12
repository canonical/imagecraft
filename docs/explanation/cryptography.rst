.. _explanation-cryptographic-technology:

Cryptographic technology in Imagecraft
======================================

Imagecraft uses cryptographic technologies to fetch arbitrary files over the internet,
communicate with local processes, and store credentials. It does not directly implement
its own cryptography, but it does depend on external libraries to do so.

Imagecraft is built on `Craft Application`_ and derives much of its functionality from
it, so much of Imagecraft's cryptographic functionality is described in `Cryptographic
technology in Craft Application`_.

.. _Craft Application: https://canonical-craft-application.readthedocs-hosted.com/latest/
.. _Cryptographic technology in Craft Application: https://canonical-craft-application.readthedocs-hosted.com/en/latest/explanation/cryptography
