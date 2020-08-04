from celery import shared_task


@shared_task()
def check_trustlines():
    from polaris.management.commands.check_trustlines import Command

    Command.check_trustlines()


@shared_task()
def execute_outgoing_transactions():
    from polaris.management.commands.execute_outgoing_transactions import Command

    Command.execute_outgoing_transactions()


@shared_task()
def poll_outgoing_transactions():
    from polaris.management.commands.poll_outgoing_transactions import Command

    Command.poll_outgoing_transactions()


@shared_task()
def poll_pending_deposits():
    from polaris.management.commands.poll_pending_deposits import Command

    Command.execute_deposits()
