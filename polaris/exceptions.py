class TransactionSubmissionError(Exception):
    pass


class TransactionSubmissionPending(TransactionSubmissionError):
    pass


class TransactionSubmissionBlocked(TransactionSubmissionError):
    pass


class TransactionSubmissionFailed(TransactionSubmissionError):
    pass
