import copy
import datetime
import unittest
from unittest import mock
from unittest.mock import Mock, MagicMock
from freezegun import freeze_time

from airflow.models import TaskInstance
from airflow.models import Connection
from airflow.settings import Session
from airflow.utils import timezone

from sentry_sdk import configure_scope

from sentry_airflow.hooks.sentry_hook import SentryHook, get_task_instance

EXECUTION_DATE = timezone.utcnow()
DAG_ID = "test_dag"
TASK_ID = "test_task"
OPERATOR = "test_operator"
STATE = "success"
TEST_SCOPE = {
    "dag_id": DAG_ID,
    "task_id": TASK_ID,
    "execution_date": EXECUTION_DATE,
    "ds": EXECUTION_DATE.strftime("%Y-%m-%d"),
    "operator": OPERATOR,
}
TASK_REPR = "Upstream Task: {}.{}, Execution: {}, State:[{}], Operation: {}".format(
    DAG_ID, TASK_ID, EXECUTION_DATE, STATE, OPERATOR
)
CRUMB_DATE = datetime.datetime(2019, 5, 15)
CRUMB = {
    "timestamp": CRUMB_DATE,
    "type": "default",
    "category": "upstream_tasks",
    "message": TASK_REPR,
    "level": "info",
}


class MockQuery:
    """
    Mock Query for when session is called.
    """

    def __init__(self, task_instance):
        task_instance.state = STATE
        self.arr = [task_instance]

    def filter(self, *args, **kwargs):
        return self

    def all(self):
        return self.arr

    def first(self):
        return self.arr[0]

    def delete(self):
        pass


class TestSentryHook(unittest.TestCase):
    @mock.patch("sentry_airflow.hooks.sentry_hook.SentryHook.get_connection")
    def setUp(self, mock_get_connection):
        self.assertEqual(TaskInstance._sentry_integration_, True)
        mock_get_connection.return_value = Connection(host="https://foo@sentry.io/123")
        self.sentry_hook = SentryHook("sentry_default")
        self.assertEqual(TaskInstance._sentry_integration_, True)
        self.dag = Mock(dag_id=DAG_ID)
        self.task = Mock(dag=self.dag, dag_id=DAG_ID, task_id=TASK_ID)
        self.task.__class__.__name__ = OPERATOR
        self.task.get_flat_relatives = MagicMock(return_value=[self.task])

        self.session = Session()
        self.ti = TaskInstance(self.task, execution_date=EXECUTION_DATE)
        self.session.query = MagicMock(return_value=MockQuery(self.ti))

    def test_add_sentry(self):
        """
        Test adding tags.
        """

        # Already setup TaskInstance
        with configure_scope() as scope:
            for key, value in scope._tags.items():
                self.assertEqual(TEST_SCOPE[key], value)

    def test_get_task_instance(self):
        """
        Test adding tags.
        """
        ti = get_task_instance(self.task, EXECUTION_DATE, self.session)
        self.assertEqual(ti, self.ti)

    @freeze_time(CRUMB_DATE.isoformat())
    def test_pre_execute(self):
        """
        Test adding breadcrumbs.
        """
        task_copy = copy.copy(self.task)
        task_copy.pre_execute(self.ti, context=None)
        self.task.get_flat_relatives.assert_called_once()

        with configure_scope() as scope:
            test_crumb = scope._breadcrumbs.pop()
            print(test_crumb)
            self.assertEqual(CRUMB, test_crumb)
