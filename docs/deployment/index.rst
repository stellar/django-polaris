=================
Deploying Polaris
=================

Implementing SEP 6, 24, or 31 requires more than a web server. Anchors must also stream incoming transactions to their asset's distribution accounts, check for incoming deposits to their off-chain accounts, confirm off-chain transfers, and more.

To support these requirements, Polaris deployments must also include additional services that can be configured to run in a variety of deployment configurations.

Running Polaris with CLI Commands
---------------------------------

The SDF currently deploys Polaris using its CLI commands. Each command either periodically checks external state or constantly streams events from an external data source.

watch_transactions
^^^^^^^^^^^^^^^^^^

This process streams transactions to and from each anchored asset's distribution account. Outgoing transactions are filtered out, and incoming transactions are matched with pending SEP 6, 24, or 31 transactions in the database using the `memo` field. Matched transactions have their statuses updated to ``pending_receiver`` for SEP-31 and ``pending_anchor`` for SEP-6 and 24.

execute_outgoing_transactions
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

This process periodically queries for transactions that are ready to be executed off-chain and calls Polaris' ``RailsIntegration.execute_outgoing_transaction`` integration function for each one. "Ready" transactions are those in ``pending_receiver`` or ``pending_anchor`` statuses, among other conditions. Anchor are expected to update the ``Transaction.status`` to ``completed`` or ``pending_external`` if initiating the transfer was successful.

poll_outgoing_transactions
^^^^^^^^^^^^^^^^^^^^^^^^^^

Polaris periodically queries for transactions in ``pending_external`` and passes them to the ``RailsIntegration.poll_outgoing_transactions``. The anchor is expected to update the transactions' status depending on if the transfer has been successful or not.

poll_pending_deposits
^^^^^^^^^^^^^^^^^^^^^

Polaris periodically queries for transactions in ``pending_user_transfer_start`` and ``pending_sender`` and passes them to the ``RailsIntegration.poll_pending_deposits`` integration function. The anchor is expected to update the transactions' status depending on the if the funds have become available in the anchor's off-chain account.

check_trustlines
^^^^^^^^^^^^^^^^

And finally, Polaris periodically checks for transactions whose accounts don't have trustlines for the asset the account is requesting using the ``pending_trust`` status. Polaris will update ``Transaction.status`` for each transaction that has a trustline to the relevant asset.

If you choose to deploy Polaris using this strategy, ensure the processes are managed and kept persistent using a process-control system like ``supervisorctl``.

Running Polaris with a Job Queue
--------------------------------

.. _Celery: https://docs.celeryproject.org/en/stable/getting-started/first-steps-with-celery.html

Instead of running the CLI commands with the ``--loop`` option, anchors can configure job schedulers to run the above commands at any frequency or interval. There are software platforms such as Jenkins and CircleCI that can run these jobs, or anchors can configure their Polaris deployments with a their own job queue using Celery_, a task queue that integrates well with Django.

Celery
^^^^^^

.. _scheduler: https://docs.celeryproject.org/en/stable/userguide/periodic-tasks.html
.. _`Celery Beat`: https://docs.celeryproject.org/en/stable/userguide/periodic-tasks.html
.. _`configure Celery for your Django project`: https://docs.celeryproject.org/en/latest/django/first-steps-with-django.html

Using Celery, anchors can schedule the functions described in the previous section to run using a cluster of worker nodes that read from a job queue.

Anchors can do so by adding Polaris' Celery tasks to the queue's periodic task scheduler_. You'll need to `configure Celery for your Django project`_ and ensure Polaris' tasks are collected. See Celery's documentation for specifics, but one line is particularly important:
::

    from celery import Celery

    app = Celery('myapp')
    ...
    app.autodiscover_tasks()

``app.autodiscover_tasks()`` looks at the ``INSTALLED_APPS`` list and imports any celery tasks defined within an app's ``tasks.py`` file. Obviously, ``polaris`` must be listed in ``INSTALLED_APPS`` for this to work.

Polaris offers tasks that can be scheduled using `Celery Beat`_ for every CLI command:

- ``polaris.tasks.poll_pending_deposits``
- ``polaris.tasks.poll_outgoing_transactions``
- ``polaris.tasks.execute_outgoing_transactions``
- ``polaris.tasks.check_trustlines``

The one CLI command that doesn't have a task is ``watch_transactions``. This is due to the fact that the other processes periodically connect to external entities, while ``watch_transactions`` is constantly streaming transactions from Stellar. Since its always running, it doesn't make sense to try and schedule it with Celery. Instead, ``watch_transactions`` should still be run as a separate process.

So, all Polaris deployments will always have at least two processes running: the web server and ``watch_transactions``. The other three pieces of functionality can be invoked periodically using a job scheduler or from their own CLI command.

However, Polaris can also be configured schedule a calls to ``RailsIntegration.execute_outgoing_transaction()`` from ``watch_transactions``. This would remove the need to schedule jobs running the ``execute_outgoing_transactions`` CLI command periodically and may be ideal if the number of transactions that need to be executed off-chain is large, since you can distribute the workload across many worker nodes. To do so, simply pass the following options to the ``watch_transactions`` CLI command:
::

    $ python manage.py watch_transactions --execute-transactions  --use-celery

This tells ``watch_transactions`` to schedule a celery task for each transaction that matches one in our database. ``execute_outgoing_transaction()`` will be called for every valid transaction
passed.

Its worth noting that the use of ``--use-celery`` is invalid without ``--execute-transactions``. If ``--use-celery`` is omitted, ``watch_transactions`` will call ``execute_outgoing_transaction()`` synchronously.
