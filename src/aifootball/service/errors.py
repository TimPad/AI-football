class DomainError(Exception):
    def __init__(self, code, message, fields=None, status=422, current_revision=None):
        self.code, self.message = code, message
        self.fields, self.status = fields or {}, status
        self.current_revision = current_revision


class RevisionConflict(DomainError):
    def __init__(self, revision):
        super().__init__('revision_conflict', 'Матч изменён в другом окне. Сверьте изменения.',
                         status=409, current_revision=revision)


def error_body(error):
    return {'error': {'code': error.code, 'message': error.message, 'fields': error.fields,
                      'current_revision': error.current_revision}}
