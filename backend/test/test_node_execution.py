from __future__ import annotations

import os
import unittest
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.auth import create_access_token
from app.core.database import get_db
from app.main import app
from app.models import Base
from app.models.executions import Execution
from app.models.nodes_executions import NodeExecution
from app.models.user import User
from app.models.workflows import Workflow
from app.tasks import execute_workflow as execute_workflow_tasks
from test.asgi_client import ASGITestClient


def _auth_headers(user_id: UUID) -> dict[str, str]:
    token = create_access_token({"sub": str(user_id)})
    return {"authorization": f"Bearer {token}"}


class NodeExecutionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            self.fail("DATABASE_URL is required to run tests")

        self.schema_name = f"node_test_{uuid4().hex}"
        self.admin_engine = create_async_engine(database_url, future=True)
        async with self.admin_engine.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{self.schema_name}"'))

        self.engine = create_async_engine(
            database_url,
            future=True,
            connect_args={"server_settings": {"search_path": self.schema_name}},
        )
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)
        self._original_task_session_factory = execute_workflow_tasks._create_task_session_factory

        def override_task_session_factory():
            return self.session_factory

        execute_workflow_tasks._create_task_session_factory = override_task_session_factory

        async def override_get_db():
            async with self.session_factory() as session:
                yield session

        app.dependency_overrides[get_db] = override_get_db
        self.client = ASGITestClient(app)

    async def asyncTearDown(self) -> None:
        app.dependency_overrides.clear()
        execute_workflow_tasks._create_task_session_factory = self._original_task_session_factory
        await self.engine.dispose()
        async with self.admin_engine.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{self.schema_name}" CASCADE'))
        await self.admin_engine.dispose()

    async def _create_user(self, email: str) -> User:
        async with self.session_factory() as session:
            user = User(email=email, username=email.split("@")[0], hashed_password="pw")
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user

    async def _create_workflow(self, user_id: UUID) -> Workflow:
        async with self.session_factory() as session:
            wf = Workflow(
                user_id=user_id,
                name="Test WF",
                definition={
                    "nodes": [
                        {
                            "id": "node_1",
                            "type": "datetime_format",
                            "config": {"format": "YYYY-MM-DD"},
                        }
                    ],
                    "edges": [],
                },
            )
            session.add(wf)
            await session.commit()
            await session.refresh(wf)
            return wf

    async def test_execute_node_creates_correct_records(self) -> None:
        user = await self._create_user("test@example.com")
        wf = await self._create_workflow(user.id)
        node_id = "node_1"

        status_code, payload = await self.client.post(
            f"/workflows/{wf.id}/nodes/{node_id}/execute",
            json_body={"input_data": {"date": "2024-01-01"}},
            headers=_auth_headers(user.id),
        )

        self.assertEqual(status_code, 202)
        execution_id = UUID(payload["execution_id"])
        self.assertEqual(payload["triggered_by"], "datetime_format")

        # Verify DB records
        async with self.session_factory() as session:
            execution = await session.get(Execution, execution_id)
            self.assertIsNotNone(execution)
            self.assertEqual(execution.triggered_by, "datetime_format")

            node_exec_query = await session.execute(
                select(NodeExecution).where(NodeExecution.execution_id == execution_id)
            )
            node_execs = node_exec_query.scalars().all()
            self.assertEqual(len(node_execs), 1)
            self.assertEqual(node_execs[0].node_id, node_id)
            self.assertEqual(node_execs[0].node_type, "datetime_format")
            self.assertEqual(node_execs[0].input_data, {"date": "2024-01-01"})
