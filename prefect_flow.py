import subprocess
from prefect import flow, task

@task
def load_data():
    subprocess.run(["python", "reload_data_3_from_stage.py"], check=True)

@task
def build_marts():
    subprocess.run(["python", "build_marts.py"], check=True)

@flow
def warehouse_pipeline():
    load_data()
    build_marts()

if __name__ == "__main__":
    warehouse_pipeline()
