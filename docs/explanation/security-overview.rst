.. _security-overview:

Security overview
=================

Overview of security aspects of Imagecraft.


Privileged execution
--------------------

``imagecraft`` may require **elevated permissions** to properly run (when using the
destructive mode). It is recommended to use a dedicated building machine. Make sure
``imagecraft`` is installed from a trusted source, and the provided configuration is
trusted.


Cryptography
------------

``imagecraft`` is a wrapper around several tools and mainly ``ubuntu-image``. The tool
itself does not use cryptographic technologies. Refer to the `ubuntu-image security
overview`_ for details on cryptographic technologies used in ``ubuntu-image``.


Miscellaneous
~~~~~~~~~~~~~

- Secrets (passwords and hashes) can be present in the configuration files provided to
  ``imagecraft`` to build images. Specifically, in the ``ubuntu-bootstrap`` plugin
  configuration:

  * In the ``extra-ppas`` customisation section, authentication tokens
    (``user:password``) can be defined to access private PPAs. These values are used to
    write the ``apt`` configuration without any treatment.
  * In the ``manual`` customisation section, user accounts can be defined with plain
    text or hashed passwords. These values are directly passed to the ``chpassword``
    utility without any treatment.

- These configuration files for secrets should then be securely stored, and if secrets
  are used, they should ideally be injected at runtime.


.. LINKS

.. _ubuntu-image security overview: https://canonical-subiquity.readthedocs-hosted.com/en/latest/explanation/ubuntu-image-security-overview.html
