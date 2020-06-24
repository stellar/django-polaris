======
SEP-31
======


Configuration
=============

Add the SEP to ``ACTIVE_SEPS`` in in your settings file.
::

    ACTIVE_SEPS = ["sep-1", "sep-31", ...]

Integrations
============

SEP-31 Endpoints
^^^^^^^^^^^^^^^^

.. autofunction:: polaris.integrations.SendIntegration.info

.. autofunction:: polaris.integrations.SendIntegration.process_send_request

.. autofunction:: polaris.integrations.SendIntegration.process_update_request

.. autofunction:: polaris.integrations.SendIntegration.valid_sending_anchor

Payment Rails
^^^^^^^^^^^^^

.. autofunction:: polaris.integrations.RailsIntegration.execute_outgoing_transaction

.. autofunction:: polaris.integrations.RailsIntegration.poll_outgoing_transactions


Running the Service
===================
