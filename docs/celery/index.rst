============
Using Celery
============

.. _Celery: https://docs.celeryproject.org/en/stable/getting-started/first-steps-with-celery.html
.. _integrates: https://docs.celeryproject.org/en/latest/django/first-steps-with-django.html
.. _scheduler: https://docs.celeryproject.org/en/stable/userguide/periodic-tasks.html
.. _`Celery Beat`: https://docs.celeryproject.org/en/stable/userguide/periodic-tasks.html
.. _`configure Celery for your Django project`: https://docs.celeryproject.org/en/latest/django/first-steps-with-django.html

Polaris comes with CLI commands to run alongside the web server, and these commands perform functions necessary for running a fully functional implementation of the SEPs supported by Polaris. The SDF runs it's Polaris reference implementation using these commands, but Polaris users can invoke the same functionality by using Celery_, a task queue that integrates_ well with Django.

Those familiar with Celery are encouraged to add Polaris' tasks to the queue's scheduler_ instead of running the CLI commands from separate processes. You'll need to `configure Celery for your Django project`_ and ensure Polaris' tasks are collected. See Celery's documentation for specifics, but one line is particularly important:
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
