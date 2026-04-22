import json
import os
import re
import time
import platform as pf
from datetime import datetime
from typing import TypedDict, Optional, List
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
import subprocess
import pandas as pd
from openai import base_url, api_key
from paramiko.agent import Agent
from sqlalchemy import create_engine, text
import openpyxl
import pymysql
from pathlib import Path
from langchain_ollama import ChatOllama
import xlrd
from tenacity import stop_after_attempt

#from adminfee_processing_agent_reference import build_graph
from trigger_anamoly_dag import trigger_airflow_dag

# set api key
os.environ[
    "OPENAI_API_KEY"] = "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"
os.environ["NO_PROXY"] = "172.31.27.7"
os.environ["no_proxy"] = "172.31.27.7"

DB_URI = "mysql+pymysql://kishore:Gpohealth!#!@dev-db-test.c969yoyq9cyy.us-east-1.rds.amazonaws.com:3306/joblog_metadata"

engine = create_engine(DB_URI)


REMOTE_AIRFLOW_CMD = "/home/ubuntu/run_airflow.sh dags trigger execute_adminFee_Data_Pipeline_v1"
AIRFLOW_CMD = [
    "/home/ubuntu/run_airflow.sh",
    "dags",
    "trigger",
    "execute_adminfee_data_pipeline_v1"
]
UBUNTU_HOST = "ubuntu@172.31.25.132"
SSH_KEY_PATH = "C:\\Users\\kkishore\\Desktop\\Cust_t0004 1.pem"

llm = ChatOpenAI(model="gpt-4.1-mini")
TABLE_NAME = 'anomaly_metadata'

BASE_DIR = Path(__file__).resolve().parent
DATE_MESSAGE = (
        BASE_DIR / "prompts" / "date_extract_prompt.txt"
).read_text()


# llm = ChatOllama(
#     model = "llama3.1:8b",
#     base_url = "http://172.31.27.7:11434",
#     temperature = 0,
#     num_predict=200,
#     top_k=10,
#     top_p=0.8,
#     repeat_penalty=1.1,0
#     timeout = 60
# )

class AgentState(TypedDict):
    user_input: str
    #llm_response: str
    start_date: Optional[str]
    end_date: Optional[str]
    valid: bool
    exit: bool

def greeting_node(state: AgentState):
    print("\n Hello Welcome to Anomaly Detection agent.")
    print("Please provide date range (eg., 2024-12-25 to 2025-12-25)")
    print("type 'exit' anytime to quit\n")

    return state


def input_node(state: AgentState):
    user_input = input("Enter date range(or 'exit'):")

    if user_input.lower() in ["exit","quit"]:
        state["exit"] = True
        return state
    state["user_input"] = user_input
    state["exit"] = False
    return state
def extract_node(state: AgentState):
    formatted_prompt = DATE_MESSAGE.format(input = state["user_input"])
    response = llm.invoke(formatted_prompt)
    response2 = response.content.replace("`","").replace("json","").strip()
    print("response_content= ",response2)
    data = json.loads(response2)
    print("json_data= ",data)

    state["start_date"]=data.get("start_date")
    state["end_date"] = data.get("end_date")

    #state["llm_response"]=response.content
    return state
# def clean_dates(text):
#     text = text.replace("\\n","\n").replace("\r"," ").strip()
#     print(text)
#     start_match = re.search(r"start_date:\s*(\d{4}-\d{2}-\d{2})", text, re.IGNORECASE | re.DOTALL)
#     end_match = re.search(f"end_date:\s*(\d{4}-\d{2}-\d{2})", text, re.IGNORECASE | re.DOTALL)
#     print("$$$$",end_match)
#
#     start_date = start_match.group(1) if start_match else None
#     print("##",start_date)
#     end_date = end_match.group(1) if end_match else None
#     print("##", end_date)
#
#     return start_date, end_date
#
# def clean_node(state: AgentState):
#     print("--------------------------------")
#     start,end = clean_dates(state["llm_response"])
#     print(start,end)
#     state["start_date"] = start
#     state["end_date"] = end
#     return state

def validation_node(state: AgentState):
    try:
        if not state["start_date"] or not state["end_date"]:
            raise ValueError("Missing dates")
        start = datetime.strptime(state["start_date"], "%Y-%m-%d")
        print("-->",start)
        end = datetime.strptime(state["end_date"], "%Y-%m-%d")
        print("-->", end)

        if start > end:
            raise ValueError("Start" > "End")
        state["valid"] = True

    except:
        print("\n Invalid date range. Please enter valid dates(e.g., 2024-12-23, 2025-12-23)\n")
        state["valid"] = False

    return state


def update_metadata_node(state: AgentState):

    trunc_query = f"TRUNCATE TABLE {TABLE_NAME}"
    insrt_query = f"""
    INSERT INTO {TABLE_NAME}(start_date, end_date)
    VALUES(:start_date, :end_date)
    """

    with engine.connect() as conn:
        conn.execute(text(trunc_query))

        conn.execute(text(insrt_query), {"start_date": state["start_date"],
                                         "end_date": state["end_date"]})

        conn.commit()

    print("metadata table updated successfully")

    return state

def trigger_airflow_node(state: AgentState):
    print("Triggering anomaly DAG.........")
    run_id = f"anomaly_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    trigger_airflow_dag(run_id)

    return state

def exit_node(state: AgentState):
    print("\n Exiting Anomaly Agent. Have a great day!\n")
    return state

def check_exit(state: AgentState):
    if state.get("exit"):
        return "exit"
    return "extract"

def check_next(state: AgentState):
    if state.get("exit"):
        return "exit"
    if state["valid"]:
        return "update_metadata"

    return "input"



def graph_build():
    graph = StateGraph(AgentState)

    graph.add_node("greet", greeting_node)
    graph.add_node("input", input_node)
    graph.add_node("extract", extract_node)
    #graph.add_node("clean", clean_node)
    graph.add_node("validation", validation_node)
    graph.add_node("update_metadata", update_metadata_node)
    graph.add_node("trigger_dag", trigger_airflow_node)
    graph.add_node("exit", exit_node)

    graph.set_entry_point("greet")
    graph.add_edge("greet", "input")
    graph.add_conditional_edges("input", check_exit)
    #graph.add_edge("extract", "clean")
    graph.add_edge("extract", "validation")
    graph.add_conditional_edges("validation", check_next)

    graph.add_edge("update_metadata", "trigger_dag")
    graph.add_edge("exit", END)

    return graph.compile()

def run_processing_anomaly():
    app = graph_build()
    app.invoke({})


if __name__ == "__main__":
    run_processing_anomaly()



