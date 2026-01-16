from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.deliverable import Deliverable
from app.models.project_template import ProjectTemplate
from app.models.project_template_version import ProjectTemplateVersion
from app.models.project_template_node import ProjectTemplateNode
from app.models.project_template_edge import ProjectTemplateEdge
from app.models.task import Task, TaskStatus, WorkKind


class BootstrapError(ValueError):
    pass


@dataclass(frozen=True)
class BootstrapResult:
    template_version_id: UUID
    created_tasks: int
    created_dependencies: int


class DeliverableBootstrapService:
    """
    Разворачивает активную версию шаблона проекта в реальные задачи по deliverable.
    Делает это атомарно (в транзакции вызывающего кода).
    """

    def __init__(self, db: Session):
        self.db = db

    def bootstrap(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        deliverable_id: UUID,
        actor_user_id: UUID,
    ) -> BootstrapResult:
        # 1) Проверяем deliverable
        d: Deliverable | None = self.db.get(Deliverable, deliverable_id)
        if not d:
            raise BootstrapError("Deliverable not found")
        if d.org_id != org_id or d.project_id != project_id:
            raise BootstrapError("org_id/project_id mismatch for deliverable")

        # Защита от повторного bootstrap
        if d.template_version_id is not None:
            raise BootstrapError("Deliverable already bootstrapped (template_version_id is set)")

        existing_tasks = (
            self.db.query(Task)
            .filter(Task.deliverable_id == deliverable_id)
            .limit(1)
            .count()
        )
        if existing_tasks:
            raise BootstrapError("Deliverable already has tasks; bootstrap is not allowed")

        # 2) Получаем активную версию шаблона для проекта
        pt: ProjectTemplate | None = (
            self.db.query(ProjectTemplate)
            .filter(ProjectTemplate.project_id == project_id)
            .first()
        )
        if not pt or pt.org_id != org_id:
            raise BootstrapError("Project template not found for this project/org")
        if not pt.active_template_version_id:
            raise BootstrapError("Project has no active template version")

        tv: ProjectTemplateVersion | None = self.db.get(ProjectTemplateVersion, pt.active_template_version_id)
        if not tv or tv.org_id != org_id or tv.project_id != project_id:
            raise BootstrapError("Active template version not found or mismatch")

        # 3) Загружаем nodes/edges шаблона
        nodes: list[ProjectTemplateNode] = (
            self.db.query(ProjectTemplateNode)
            .filter(ProjectTemplateNode.template_version_id == tv.id)
            .all()
        )
        if not nodes:
            raise BootstrapError("Template version has no nodes")

        edges: list[ProjectTemplateEdge] = (
            self.db.query(ProjectTemplateEdge)
            .filter(ProjectTemplateEdge.template_version_id == tv.id)
            .all()
        )

        node_by_code = {n.code: n for n in nodes}

        # 4) Создаём Task для каждого node. Сначала без parent_task_id, потом проставим.
        task_by_code: dict[str, Task] = {}

        # Небольшая проверка: parent_code должен существовать (если задан)
        for n in nodes:
            if n.parent_code and n.parent_code not in node_by_code:
                raise BootstrapError(f"Template node '{n.code}' references missing parent_code '{n.parent_code}'")

        for n in nodes:
            t = Task(
                org_id=org_id,
                project_id=project_id,
                created_by=actor_user_id,
                title=n.title,
                description=n.description,
                priority=n.priority,
                # По финальной модели: задачи создаются в blocked и переходят в available,
                # когда зависимости/хо... (см. ARCHITECTURE.md)
                status=TaskStatus.blocked.value,
                kind=n.kind,
                work_kind=WorkKind.work,  # ⬅️ страховка: bootstrap всегда создаёт обычные work-задачи
                other_kind_label=None,
                deliverable_id=deliverable_id,
                is_milestone=bool(n.is_milestone),
                parent_task_id=None,  # проставим ниже
            )
            self.db.add(t)
            task_by_code[n.code] = t

        # flush нужен, чтобы получить UUID задач
        self.db.flush()

        # 5) Проставляем parent_task_id по parent_code
        for n in nodes:
            if n.parent_code:
                child = task_by_code[n.code]
                parent = task_by_code[n.parent_code]
                child.parent_task_id = parent.id

        # 6) Создаём зависимости task_dependencies через mapping code -> task_id
        #    Храним именно UUID реальных задач.
        created_deps = 0
        for e in edges:
            if e.predecessor_code not in task_by_code:
                raise BootstrapError(f"Edge predecessor_code not found in nodes: {e.predecessor_code}")
            if e.successor_code not in task_by_code:
                raise BootstrapError(f"Edge successor_code not found in nodes: {e.successor_code}")
            pred_id = task_by_code[e.predecessor_code].id
            succ_id = task_by_code[e.successor_code].id

            if pred_id == succ_id:
                raise BootstrapError("Template edge cannot be self-referential")

            # Вставляем напрямую в task_dependencies (как у тебя уже сделано в API)
            self.db.execute(
                text("""
                    INSERT INTO task_dependencies (org_id, project_id, predecessor_id, successor_id, created_by, created_at)
                    VALUES (:org_id, :project_id, :pred, :succ, :created_by, now())
                """),
                {
                    "org_id": str(org_id),
                    "project_id": str(project_id),
                    "pred": str(pred_id),
                    "succ": str(succ_id),
                    "created_by": str(actor_user_id),
                },
            )
            created_deps += 1

        # 7) Фиксируем, по какой версии чертежа развернули deliverable
        d.template_version_id = tv.id
        self.db.add(d)

        return BootstrapResult(
            template_version_id=tv.id,
            created_tasks=len(nodes),
            created_dependencies=created_deps,
        )
