"""
### DAG documntation
This is a simple ETL data pipeline example which extract rates data from API
 and load it into postgresql.
"""

from airflow import DAG
from airflow.operators.python_operator import PythonOperator
from airflow.operators.bash_operator import BashOperator
from airflow.operators.postgres_operator import PostgresOperator
from airflow.sensors.sql_sensor import SqlSensor
from airflow.sensors.python import PythonSensor
from airflow.models import Variable
from airflow.utils.dates import days_ago
from airflow.hooks.base import BaseHook
from airflow.exceptions import AirflowSensorTimeout

import requests
import decimal
import psycopg2
from time import localtime, strftime
from datetime import datetime

default_args = {
    "owner": "airflow",
    'start_date': days_ago(1)
}


# Variable в Airflow
variables = Variable.set(key="currency_load_variables",
                         value={"table_name": "rates",
                          "rate_base": "BTC", 
                          "rate_target": "USD",
                          "connection_name":"pg_conn",
                          "url_base":"https://api.exchangerate.host/",
                          "connection_name": "my_db_conn"},
                         serialize_json=True)
dag_variables = Variable.get("currency_load_variables", deserialize_json=True)

url_base = 'https://api.exchangerate.host/'

table_name = 'rates'
rate_base = 'BTC'
rate_target = 'USD'

pg_hostname = 'host.docker.internal'
pg_port = '5430'
pg_username = 'postgres'
pg_pass = 'password'
pg_db = 'test'


def get_rates_rows_cnt():
    pg_conn = get_conn_credentials(dag_variables.get('connection_name'))
    pg_hostname, pg_port, pg_username, pg_pass, pg_db = pg_conn.host, pg_conn.port, pg_conn.login, pg_conn.password, pg_conn.schema
    conn = psycopg2.connect(host=pg_hostname, port=pg_port, user=pg_username, password=pg_pass, database=pg_db)
    
    cursor = conn.cursor()
    cursor.execute(f"SELECT count(*) FROM {dag_variables.get('table_name')}")
    rates_cnt_rows = cursor.fetchall()[0][0]
    print(rates_cnt_rows)
    Variable.set("rates_rows_cnt", rates_cnt_rows)

    cursor.close()
    conn.close()

"""
Save rates in pustgresql
"""
def insert_data(**kwargs):
    task_instance = kwargs['task_instance']
    results = task_instance.xcom_pull(key='results', task_ids='import_rates')
    
    print("rate_date: ", results["rate_date"])
    print("value_: ", results["value_"])
    
    ingest_datetime = strftime("%Y-%m-%d %H:%M:%S", localtime())
    
    pg_conn = get_conn_credentials(dag_variables.get('connection_name'))
    pg_hostname, pg_port, pg_username, pg_pass, pg_db = pg_conn.host, pg_conn.port, pg_conn.login, pg_conn.password, pg_conn.schema
    conn = psycopg2.connect(host=pg_hostname, port=pg_port, user=pg_username, password=pg_pass, database=pg_db)
    
    cursor = conn.cursor()
    cursor.execute(f"INSERT INTO {dag_variables.get('table_name')} (ingest_datetime, rate_date, rate_base, rate_target, value_ ) valueS('{ingest_datetime}','{results['rate_date']}', '{dag_variables.get('rate_base')}', '{dag_variables.get('rate_target')}', '{results['value_']}');")
    conn.commit()

    cursor.close()
    conn.close()
    
"""
Run uploading code from exchangerate.host API
"""
def import_codes(**kwargs):
# Parameters
    hist_date = "latest"
    url = dag_variables.get('url_base') + hist_date
    ingest_datetime = strftime("%Y-%m-%d %H:%M:%S", localtime())
    
    try:
        response = requests.get(url,
            params={'base': dag_variables.get('rate_base')})
    except Exception as err:
        print(f'Error occured: {err}')
        return
    data = response.json()
    rate_date = data['date']
    value_ = str(decimal.Decimal(data['rates']['USD']))[:20]
    
    ti = kwargs['ti']
    ti.xcom_push(key='results', value={"rate_date":rate_date, "value_":value_, "ingest_datetime":ingest_datetime })

def get_conn_credentials(conn_id) -> BaseHook.get_connection:
    """
    Function returns dictionary with connection credentials

    :param conn_id: str with airflow connection id
    :return: Connection
    """
    conn = BaseHook.get_connection(conn_id)
    return conn

def check_rates_cnt_change():
    pg_conn = get_conn_credentials(dag_variables.get('connection_name'))
    pg_hostname, pg_port, pg_username, pg_pass, pg_db = pg_conn.host, pg_conn.port, pg_conn.login, pg_conn.password, pg_conn.schema
    conn = psycopg2.connect(host=pg_hostname, port=pg_port, user=pg_username, password=pg_pass, database=pg_db)
    
    cursor = conn.cursor()
    cursor.execute(f"SELECT count(*) FROM {dag_variables.get('table_name')}")
    temp_rates_cnt_rows = cursor.fetchall()[0][0]
    print(Variable.get("rates_rows_cnt"), temp_rates_cnt_rows)

    cursor.close()
    conn.close()

    if temp_rates_cnt_rows > int(Variable.get("rates_rows_cnt")):
        return True
    else:
        return False

def _failure_callback(context):
    if isinstance(context['exception'], AirflowSensorTimeout):
        print(context)
        print("Sensor timed out")

"""
Identify Airflow DAG
"""
with DAG(dag_id="yandex-rates-test", schedule_interval = "*/5 * * * *",
    default_args=default_args, tags=["yandex","test"], catchup=False
) as dag:
    dag.doc_md = __doc__
    
    hello_bash_task = BashOperator(task_id = 'bash_task',
                 bash_command = "echo 'Hello, World!'")

    get_rates_rows_cnt_task = PythonOperator(
                task_id = "get_rates_rows_cnt",
                python_callable = get_rates_rows_cnt)

    import_rates_from_api = PythonOperator(
                task_id = "import_rates",
                python_callable = import_codes)
    
    # insert_rates_to_pg = PythonOperator(
    #             task_id="insert_data",
    #             python_callable=insert_data)

    python_sensor = PythonSensor(task_id='python_sensor',
                                 poke_interval=60,
                                 timeout=10,
                                 retries=2,
                                 mode="poke",
                                 python_callable = check_rates_cnt_change,
                                 on_failure_callback= _failure_callback,
                                 soft_fail = True)

    goodbye_bash_task = BashOperator(task_id = 'goodbye_bash_task',
                bash_command = "echo 'Goodbye, World!'")

    # sql_sensor = SqlSensor(
    #     mode = 'poke',
    #     task_id='sql_sensor_check',
    #     poke_interval=60,
    #     timeout=120,
    #     soft_fail=False,
    #     retries=2,
    #     sql=f"select * from rates",
    #     conn_id='my_db_conn',
    # dag=dag)

    # create_new_table = PostgresOperator(
    #     task_id='create_new_table',
    #     postgres_conn_id='my_db_conn',
    #     sql="""CREATE TABLE dashboard (
    #                 id DATE NOT NULL,
    #                 name TEXT NOT NULL,
    #                 PRIMARY KEY (id)
    #             );""")

get_rates_rows_cnt_task >> hello_bash_task >> import_rates_from_api >> python_sensor >> goodbye_bash_task
    
    #  >> get_rates_rows_cnt_task >> import_rates_from_api >> insert_rates_to_pg >> python_sensor >> goodbye_bash_task