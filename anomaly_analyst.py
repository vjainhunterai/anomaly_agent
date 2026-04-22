from typing import TypedDict, List
from datetime import datetime
import time
import json
import re
import os
from pathlib import Path

from openpyxl.worksheet.print_settings import PRINT_AREA_RE
from sqlalchemy import create_engine, text
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_ollama import ChatOllama
from sqlalchemy.dialects.mssql.information_schema import columns

# set api key
os.environ[
    "OPENAI_API_KEY"] = "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"
os.environ["NO_PROXY"] = "172.31.27.7"
os.environ["no_proxy"] = "172.31.27.7"

DB_URI = "mysql+pymysql://kishore:Gpohealth!#!@dev-db-test.c969yoyq9cyy.us-east-1.rds.amazonaws.com:3306/joblog_metadata"

engine = create_engine(DB_URI)

llm = ChatOpenAI(model="gpt-4.1-mini")

MEMORY_FILE = "memory.json"
table_name = "duplicate_ap_invoice"

BASE_DIR = Path(__file__).resolve().parent
UNDERSTANDING_PROMPT = (
        BASE_DIR / "prompts" / "understanding_prompt.txt"
).read_text()

FORMAT_PROMPT = (
        BASE_DIR / "prompts" / "anomaly_format_prompt.txt"
).read_text()

ANOMALY_PROMPT = (
        BASE_DIR / "prompts" / "anomaly_prompt.txt"
).read_text()

ANOMALY_CHAT_PROMPT = (
        BASE_DIR / "prompts" / "anomaly_chat_prompt.txt"
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

def fetch_data():
    query = """
    select * from anomaly.duplicate_ap_invoice
    """

    with engine.connect() as conn:
        result = conn.execute(text(query))
        return [dict(row) for row in result.mappings()]

def get_metadata_from_db(table_name):
    query = """
    SELECT column_name, comments from table_column_info
    WHERE table_name = :table_name
    """

    column = []

    with engine.connect() as conn:
        result = conn.execute(text(query), {"table_name": table_name})

    for row in result.mappings():
        column.append({
            "name": row["column_name"],
            "description": row["comments"]
        })

    return {
        "table_name": table_name,
        "table_description": "Accounts Payable duplicate invoice dataset",
        "columns": column
    }

def format_metadata(metadata):
    text = f"""
TABLE INFORMATION:

Table name: {metadata['table_name']}
 
Table Description:
{metadata['table_description']}

COLUMN DEFINITIONS:
"""
    for col in metadata["columns"]:
        text += f"\n{col['name']}: {col['description']}"

    return text.strip()

def load_memory():
    if not os.path.exists(MEMORY_FILE):
        return []
    with open(MEMORY_FILE, "r") as f:
        return json.loads()

def save_memory(data):
    memory = load_memory()
    memory.append(data)
    memory = memory[-20:]

    with open(MEMORY_FILE, "w") as f:
        json.dumps(memory,f, indent=2)

def get_memory_context():
    memory = load_memory()
    return json.dumps(memory[-5:], indent=2)

def chunk_data(data, size=200):
    for i in range(0, len(data), size):
        yield data[i:i+size]

def fetch_node(state):
    data = fetch_data()
    metadata = get_metadata_from_db(table_name)
    column_info = format_metadata(metadata)


    return {"data": data,
            "column_info": column_info
            }
def understanding_node(state):
    #data_sample = state["data"][:200]

    prompt = UNDERSTANDING_PROMPT.format(
        data = json.dumps(state["data"][:200], indent=2, default=str),
        column_info = state["column_info"]
    )

    response = llm.invoke(prompt)

    #print("understanding:",response.content)

    #return {"understanding": response.content}
    return{
        "data":state["data"],
        "column_info":state["column_info"],
        "understanding":response.content
    }

def anomaly_node(state):
    all_anomalies = []

    memory = get_memory_context()

    for chunk in chunk_data(state["data"], 200):

        prompt = ANOMALY_PROMPT.format(
            data=json.dumps(chunk, indent=2, default=str),
            understanding=state["understanding"],
            memory=memory,
            column_info=state["column_info"]
        )

        response = llm.invoke(prompt)

        print("anomalies:", response.content)

        try:
            anomalies = json.loads(response.content)

            if isinstance(anomalies, dict):
                anomalies = [anomalies]
            clean_anomalies = []

            for a in anomalies:
                if isinstance(a, str):
                    a=json.loads(a)
                clean_anomalies.append(a)

            all_anomalies.extend(clean_anomalies)

        except:
            continue

    print("$$$$$",type(all_anomalies))
    unique = {a["invoice_id"]: a for a in all_anomalies}
    new_state = dict(state)
    new_state["anomalies"] = list(unique.values())

    #return {"anomalies": list(unique.values())}
    return new_state

def format_node(state):
    prompt = FORMAT_PROMPT.format(
        anomalies=json.dumps(state["anomalies"], indent=2, default=str)
    )

    response = llm.invoke(prompt)

    return {"final_output": response.content}

def memory_node(state):
    save_memory(
        {
            "understanding": state["understanding"],
            "anomalies": state["anomalies"]
        }
    )

    return state


def build_graph():
    graph = StateGraph(dict)

    graph.add_node("fetch", fetch_node)
    graph.add_node("understanding", understanding_node)
    graph.add_node("detect", anomaly_node)
    graph.add_node("format", format_node)
    graph.add_node("memory", memory_node)

    graph.set_entry_point("fetch")
    graph.add_edge("fetch","understanding")
    graph.add_edge("understanding", "detect")
    graph.add_edge("detect", "format")
    graph.add_edge("format", "memory")

    return graph.compile()

def chat_agent(question, state):
    prompt = ANOMALY_CHAT_PROMPT.format(
        question=question,
        anomalies=json.dumps(state["anomalies"], indent=2),
        understanding=state["understanding"],
        column_info=state["column_info"]
    )

    response = llm.invoke(prompt)
    return response.content


def run_anomaly_analyst():
    app = build_graph()

    state = app.invoke({})

    print("\n========= FINAL OUTPUT =========\n")
    print(state["final_output"])

    while True:
        q = input("Ask (exit to quit): ")
        if q.lower() == "exit":
            break

        ans = chat_agent(q, state)
        print("\n Answer:", ans)

if __name__ == "__main__":
    run_anomaly_analyst()