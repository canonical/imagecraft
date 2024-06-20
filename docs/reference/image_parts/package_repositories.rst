.. _package_repositories:

Package Repositories
====================

When building an image, configuration is needed at different stages to define from where to get packages. The top-level ``package-repositories`` keyword enable defining what :ref:`apt` and :ref:`PPA` (Personal Package Archive) repositories should be used during the image build and in the resulting image.


Defining the configuration used to build the image
--------------------------------------------------

.. code-block:: yaml
    
    package-repositories:
    - type: apt
        components: [main, restricted]
        url: http://archive.ubuntu.com/ubuntu/
        flavor: ubuntu
        pocket: proposed
        used-for: build


.. _apt:

apt repositories
----------------

The following properties are supported for apt repositories:

- :ref:`type`: (required) The type of package-repository, only ``apt`` is currently supported.
- :ref:`components`: Components are a list of apt sources, such as ``main``, ``universe``, and ``restricted``.
- :ref:`url`: The mirror URL for apt sources.
- :ref:`flavor`: The flavor of Ubuntu to build.
- :ref:`pocket`: (required) The pocket to get packages from.
- :ref:`used-for`: (required) This keyword indicates when this configuration should be used.


.. _type:

``type``
~~~~~~~~

**Type:** enum[string]

**Required**: Yes

**Description:** Specifies type of package-repository

**Notes:** Must be `apt`

**Examples:**
  - type: apt

.. _components:

``components``
~~~~~~~~~~~~~~

**Type:** list[string]

**Required**: No

**Description:** Apt repository components to enable: e.g. ``main``, ``multiverse``, ``unstable``

**Examples:**
  - components: [main]
  - components: [main, multiverse, universe, restricted]

.. _url:

``url``
~~~~~~~

**Type:** string

**Required**: No

**Description:** Repository URL.

**Examples:**
    - url: http://archive.canonical.com/ubuntu
    - url: https://apt-repo.com/stuff

.. _flavor:

``flavor``
~~~~~~~~~~

**Type:** string

**Required**: No

**Description:** The flavor of Ubuntu to build.

**Format:** `<ppa-owner>/<ppa-name>`

**Examples:**
  - ppa: snappy-devs/snapcraft-daily


.. _pocket:

``pocket``
~~~~~~~~~~

**Type:** enum[string]

**Required**: Yes

**Description:** Specifies the pocket to get packages from.

**Supported values:** 
  - ``release``
  - ``updates``
  - ``proposed``
  - ``security``

**Examples:**
  - pocket: updates

.. _used-for:

``used-for``
~~~~~~~~~~~~

**Type:** enum[string]

**Required**: Yes

**Description:** Specifies when the configuration should be used.

**Supported values:** 
  - ``build``
  - ``run``
  - ``always``

**Examples:**
  - used-for: build


.. _PPA:

PPA
---

The following properties are supported for Personal Package Archives:

- :ref:`type`: (required) The type of package-repository, only ``apt`` is currently supported.
- :ref:`ppa_key`: (required) The name of the PPA in the format ``<ppa-owner>/<ppa-name>``.
- :ref:`auth`: Authentication for private PPAs in the format ``user:password``.
- :ref:`key-id`: The fingerprint of the GPG signing key for this PPA.
- :ref:`used-for`: (required) This keyword indicates when this configuration should be used.

.. _ppa_key:

``ppa``
~~~~~~~

**Type:** string

**Required**: Yes

**Description:** PPA shortcut string

**Format:** ``<ppa-owner>/<ppa-name>``

**Examples:**
  - ppa: snappy-devs/snapcraft-daily
  - ppa: mozillateam/firefox-next


.. _auth:

``auth``
~~~~~~~~

**Type:** string

**Required**: No

**Description:** Authentication for private PPAs in the format ``user:password``.

**Format:** ``<user>:<password>``

**Examples:**
  - auth: "username:password"

.. warning::
   If you use this key, either make sure your configuration file is not exposed, or the actual value of the key is only injected at runtime to avoid storing/versioning secrets.


.. _key-id:

``key-id``
~~~~~~~~~~


**Type:** string

**Required**: No

**Description:** The fingerprint of the GPG signing key for this PPA. Public PPAs have this information available from the Launchpad API, so it can be retrieved automatically. For Private PPAs this must be specified.

**Format:** 40 characters long string

**Examples:**
  - key-id: ABC5112AB4104F975AB8A53FD4C0B668FD4C9139

Examples
--------

.. code-block:: yaml
    
    package-repositories:
    - type: apt
      components: [main, restricted]
      url: http://archive.ubuntu.com/ubuntu/
      flavor: ubuntu
      pocket: proposed
      used-for: build
    - type: apt
      components: [main, multiverse]
      used-for: run
    - type: apt
      ppa: canonical-foundations/ubuntu-image
      used-for: build
    - type: apt
      ppa: canonical-foundations/ubuntu-image-private-test
      auth: "user:password"
      key-id: "ABC5112AB4104F975AB8A53FD4C0B668FD4C9139"
      used-for: run
