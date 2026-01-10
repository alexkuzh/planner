# app/services/fix_invariants.py
from app.models.task import Task, WorkKind, FixSource


class FixInvariantViolation(ValueError):
    pass


def validate_fix_task(task: Task) -> None:
    if task.work_kind == WorkKind.fix:
        # I5: fix-task requires fix_source / fix_severity
        if task.fix_source is None:
            raise FixInvariantViolation("fix-task requires fix_source")
        if task.fix_severity is None:
            raise FixInvariantViolation("fix-task requires fix_severity")

        # I6: context must exist
        has_origin = task.origin_task_id is not None
        has_qc = task.qc_inspection_id is not None
        has_deliverable = task.deliverable_id is not None

        if not (has_origin or has_qc or has_deliverable):
            raise FixInvariantViolation(
                "fix-task requires context (origin_task_id or qc_inspection_id or deliverable_id)"
            )

        # I6: source must match context
        if task.fix_source == FixSource.qc_reject and not has_qc:
            raise FixInvariantViolation("qc_reject fix-task requires qc_inspection_id")

        if task.fix_source == FixSource.worker_initiative and not (has_origin or has_deliverable):
            raise FixInvariantViolation("worker_initiative fix-task requires origin_task_id or deliverable_id")

    else:
        # I5: non-fix task must not have fix_* fields
        if task.fix_source is not None or task.fix_severity is not None:
            raise FixInvariantViolation("non-fix task must not have fix_source/fix_severity")
