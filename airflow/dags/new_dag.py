"""
### DAG documntation
This is a simple ETL data pipeline example which extract rates data from API
 and load it into postgresql.
"""

from airflow import DAG
from airflow.operators.bash_operator import BashOperator
from airflow.utils.dates import days_ago

default_args = {
    "owner": "airflow",
    'start_date': days_ago(1)
}

with DAG(dag_id="yandex-new-dag", schedule_interval = "*/5 * * * *",
    default_args=default_args, tags=["yandex","test"], catchup=False) as dag:
        
    dag.doc_md = __doc__

    hello_bash_task = BashOperator(task_id = 'bash_task',
                    bash_command = "echo 'Hello, World!'")

    hello_bash_task